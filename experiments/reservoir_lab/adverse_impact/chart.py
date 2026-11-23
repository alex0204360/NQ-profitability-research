"""Render the adverse-impact replay as one offline HTML document."""

import json
from pathlib import Path


VIEWER = Path(__file__).resolve().parents[2] / "path_order" / "workbench" / "viewer.html"

MODE_CONTROLS = """  <div class="group">
    <select id="mode" aria-label="Replay mode">
      <option value="original">Original</option>
      <option value="fixed_volume">Fixed entries · Volume hold</option>
      <option value="fixed_price">Fixed entries · Price hold</option>
      <option value="full_volume">Full replay · Volume hold</option>
      <option value="full_price">Full replay · Price hold</option>
    </select>
  </div>
"""

EXTREME_CONTROLS = """<div class="toolbar impact-cases" aria-label="Trade impact examples">
  <button id="improvement" type="button" aria-pressed="false">Largest improvement</button>
  <button id="damaged_winner" type="button" aria-pressed="false">Most damaged winner</button>
</div>
<div id="comparison" hidden aria-live="polite"></div>
"""

IMPACT_LEGEND = """<span class="forecast">━ Original Forecast (pts)</span>
  <span class="hold">━ Hold value (pts) · experimental</span>
  <span>┄ Entry thresholds (±1.5)</span>
  <span id="comparison-legend" hidden><span class="original-exit">◆ Original exit</span> · <span class="hold">◆ Edited exit</span></span>"""

IMPACT_CSS = """
.hold { color:#ddb1ff }
.original-exit { color:#8fb8ff }
.impact-cases { gap:6px }
#comparison { padding:9px 13px; border-bottom:1px solid var(--line); line-height:1.5 }
#mode { max-width:100% }
"""

IMPACT_SCRIPT = r"""
const cases = ["improvement","damaged_winner"];
const holdColor = "#ddb1ff";
let activeCase = null;
let holdSamples = new Map();

function prepareHold() {
  holdSamples = new Map();
  if (mode === "original") return;
  const samples = current()?.layers?.[mode]?.hold || [];
  const positions = trades();
  let tradeIndex = 0;
  bars().forEach((bar,index) => {
    const minute = bar[0];
    while (tradeIndex < positions.length && positions[tradeIndex].exit <= minute) tradeIndex++;
    const trade = positions[tradeIndex];
    if (trade && trade.entry <= minute && Number.isFinite(samples[index])) {
      holdSamples.set(minute,{value:samples[index],owner:tradeIndex});
    }
  });
}

function scorePath(visible, yAt, sample, color) {
  ctx.strokeStyle = color;
  ctx.beginPath();
  let previous = null, owner = null;
  for (const bar of visible) {
    const reading = sample(bar);
    if (!reading) {
      previous = null;
      continue;
    }
    const x = xAt(bar[0]), y = yAt(reading.value);
    if (previous === bar[0]-1 && reading.owner === owner) ctx.lineTo(x,y);
    else {
      ctx.moveTo(x,y);
      ctx.lineTo(x+Math.max(.8,(plot.right-plot.left)/(windowRight-windowLeft)*.18),y);
    }
    previous = bar[0];
    owner = reading.owner;
  }
  ctx.stroke();
}

function updateComparison() {
  const comparison = $("comparison");
  const chosen = extremes[activeCase];
  comparison.hidden = $("comparison-legend").hidden = !chosen;
  for (const id of cases) {
    $(id).disabled = !extremes[id];
    $(id).setAttribute("aria-pressed",String(activeCase === id));
  }
  if (!chosen) {
    comparison.replaceChildren();
    return;
  }
  const side = chosen.side === "long" ? "Long" : "Short";
  comparison.innerHTML = `<strong>${side} at ${time(chosen.entry)} ET</strong> ·
    <span class="original-exit">Original exit ${time(chosen.original_exit)} ET (${currency.format(chosen.original_net)})</span> ·
    <span class="hold">Edited exit ${time(chosen.edited_exit)} ET (${currency.format(chosen.edited_net)})</span> ·
    <strong class="${chosen.delta < 0 ? "neg" : "pos"}">${currency.format(chosen.delta)} net change</strong>`;
}

function jumpToCase(id) {
  const chosen = extremes[id];
  if (!chosen) return;
  const index = sessions.findIndex(session => session.date === chosen.date);
  if (index < 0) return;
  mode = "fixed_volume";
  changeSession(index);
  activeCase = id;
  const edited = trades().findIndex(trade => trade.entry === chosen.entry && trade.exit === chosen.edited_exit &&
    trade.side === chosen.side && Math.abs(trade.net-chosen.edited_net)<.005);
  if (edited >= 0) selectTrade(edited);
  const last = Math.max(chosen.original_exit,chosen.edited_exit);
  setWindow(chosen.entry-10,last+12);
  updateComparison();
  draw();
}

function impactExitMarkers(yAt) {
  const chosen = extremes[activeCase];
  if (!chosen) return;
  const series = [
    {minute:chosen.original_exit, name:"Original exit", color:colors.blue, layer:"original"},
    {minute:chosen.edited_exit, name:"Edited exit", color:holdColor, layer:"fixed_volume"},
  ];
  for (const {minute,name,color,layer} of series) {
    if (minute < windowLeft || minute > windowRight) continue;
    const trade = current()?.layers?.[layer]?.trades.find(trade =>
      trade.entry === chosen.entry && trade.exit === minute && trade.side === chosen.side);
    const fill = trade?.xp ?? bars().find(bar => bar[0] === minute)?.[1];
    if (!Number.isFinite(fill)) continue;
    const x = xAt(minute);
    const fillY = yAt(fill);
    const offset = layer === "original" ? -23 : -39;
    const y = clamp(fillY+offset,plot.top+39,plot.split-8);
    line(x,fillY,x,y,color,[3,2]);
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.moveTo(x,y-5);
    ctx.lineTo(x+5,y);
    ctx.lineTo(x,y+5);
    ctx.lineTo(x-5,y);
    ctx.fill();
    const right = x+100 > plot.right;
    const textX = right ? x-9 : x+9;
    ctx.strokeStyle = "#0d1621";
    ctx.textAlign = right ? "right" : "left";
    ctx.lineWidth = 4;
    ctx.strokeText(name,textX,y+4);
    ctx.lineWidth = 1;
    label(name,textX,y+4,color,right ? "right" : "left");
  }
}
"""

FORECAST_PANEL = r"""
function forecastPanel(visible) {
  const amplitudes = visible.flatMap(bar => [bar[6],holdSamples.get(bar[0])?.value])
    .filter(Number.isFinite).map(value => Math.abs(value)*1.12);
  const limit = Math.max(2,...amplitudes);
  const yAt = value => plot.forecastTop + (limit-value)/(2*limit)*(plot.bottom-plot.forecastTop);
  label("FORECAST AND HOLD (PTS)",plot.left,plot.split+14);
  const thresholdLabelGap = yAt(0)-yAt(1.5);
  for (const level of [1.5,0,-1.5]) {
    const y = yAt(level);
    line(plot.left,y,plot.right,y,level ? "#52617a" : "#657994",level ? [4,4] : []);
    if (level ? thresholdLabelGap >= 8 : thresholdLabelGap < 8 || thresholdLabelGap >= 13) {
      label(level > 0 ? "+1.5" : level === 0 ? "0" : "−1.5",plot.right+7,y+4);
    }
  }
  scorePath(visible,yAt,bar => Number.isFinite(bar[6]) ? {value:bar[6]} : null,colors.blue);
  scorePath(visible,yAt,bar => holdSamples.get(bar[0]),holdColor);
  return yAt;
}

"""


def render(sessions, extremes, target, model="adverse_impact"):
    """Write a portable document using the existing Reservoir replay canvas and ledger."""
    title = "Reservoir Failed Recovery" if model == "failed_recovery" else "Reservoir Adverse Impact"
    mechanism = ("A growing adverse move sets a price memory. After a halfway recovery, a break through the remembered close produces one exit pulse."
                 if model == "failed_recovery" else "A growing adverse move leaves a pending shock. The next bar's recovery pays it down; unrecovered points reduce hold value.")
    source = VIEWER.read_text(encoding="utf-8")

    def replace(old, new):
        nonlocal source
        if source.count(old) != 1:
            raise ValueError(f"Expected one replay template anchor: {old!r}")
        source = source.replace(old, new, 1)

    def replace_section(first, after, content):
        start = source.index(first)
        end = source.index(after, start + len(first))
        replace(source[start:end], content)

    replace("<title>MNQ · Reservoir Replay</title>", f"<title>MNQ · {title}</title>")
    replace("<h1>MNQ Reservoir Replay</h1>", f"<h1>{title}</h1>")
    replace("</style>", IMPACT_CSS + "</style>")
    replace_section('  <div class="group" aria-label="Replay variant">',
                    '  <div class="group zoom"', MODE_CONTROLS)
    replace('<div class="legend">', EXTREME_CONTROLS + '<div class="legend">')
    replace_section('  <span class="forecast">━ Forecast (pts)', '\n</div>', '  ' + IMPACT_LEGEND)
    replace("</details>", "<p>" + mechanism + "</p>" + """<p>The original forecast is unchanged across modes. The edited hold value appears only at completed bars while a position is open. Hold value is an experimental four-minute score relative to the held side. Positive favors continuing either a long or a short. Zero or negative requests an exit at the next open. The 0 line is the hold exit threshold. The dashed ±1.5 lines are the original entry thresholds.</p></details>""")
    replace('const sessions = JSON.parse($("replay-data").textContent).sessions;',
            'const {sessions,extremes} = JSON.parse($("replay-data").textContent);')
    replace('let mode = "base";', 'let mode = "fixed_volume";')
    replace('const reasons = {signal:', 'const reasons = {hold:"Hold exit",signal:')
    replace('return current()?.[mode] || [];', 'return current()?.layers?.[mode]?.trades || [];')
    replace('function current() {', IMPACT_SCRIPT + '\nfunction current() {')
    replace('  sessionIndex = index;', '  activeCase = null;\n  sessionIndex = index;')
    replace('  mode = next;', '  activeCase = null;\n  mode = next;')
    replace_section('  $("base").setAttribute', '  const net =',
                    '  $("mode").value = mode;\n  prepareHold();\n  updateComparison();\n')
    replace('Forecast <b>${points(bar[6])}</b>',
            'Original forecast <b>${points(bar[6])}</b> &nbsp; Hold <b>${points(holdSamples.get(bar[0])?.value)}</b>')
    replace_section("function forecastPanel", "function glyph", FORECAST_PANEL)
    replace_section("  const lock = current()?.lock;", "  const candleWidth", "")
    replace("  tradeMarkers(yAt);", "  tradeMarkers(yAt);\n  impactExitMarkers(yAt);")
    replace('    const tag = clamp(x-19', '''    const hold = holdSamples.get(hoverBar[0]);
    if (hold) {
      ctx.fillStyle = holdColor;
      ctx.beginPath();
      ctx.arc(x,forecastY(hold.value),3,0,2*Math.PI);
      ctx.fill();
    }
    const tag = clamp(x-19''')
    replace_section('$("base").onclick', '$("out").onclick',
                    '$("mode").onchange = event => changeMode(event.target.value);\n'
                    'for (const id of cases) $(id).onclick = () => jumpToCase(id);\n')
    replace("__REPLAY_DATA__", json.dumps(
        {"sessions": sessions, "extremes": extremes}, separators=(",", ":"), allow_nan=False
    ).replace("<", r"\u003c"))
    Path(target).write_text(source, encoding="utf-8")
