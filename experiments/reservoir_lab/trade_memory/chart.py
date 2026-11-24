"""Render the trade-memory replay as a self-contained offline chart."""

import json
from pathlib import Path

from experiments.reservoir_lab.adverse_impact.chart import EXTREME_CONTROLS, FORECAST_PANEL, IMPACT_CSS, IMPACT_SCRIPT, VIEWER


POLICIES = {
    "original": ("Original reservoir", "Original forecast drives entries and exits."),
    "continuous": ("Prior failed-recovery", "Failed-recovery exit memory rolls continuously on completed bars."),
    "local": ("Entry-local exit memory", "Failed-recovery exit memory starts fresh at each entry fill."),
    "fresh": ("Fresh-evidence re-entry", "Exit memory rolls continuously. Same-side re-entry requires fresh evidence."),
    "fixed_local": ("Fixed original entries · Local exit", "Matched original entries with exit memory reset on fill."),
    "both": ("Both changes", "Exit memory starts fresh at each entry fill. Same-side re-entry requires fresh evidence."),
}

MODE_CONTROLS = """  <div class="group">
    <select id="mode" aria-label="Replay mode"></select>
  </div>
"""

LEGEND = """  <span class="forecast">━ Original Forecast (pts)</span>
  <span class="hold">━ Hold value (pts) · experimental four-minute score</span>
  <span>┄ Entry thresholds (±1.5)</span>
  <span id="comparison-legend" hidden><span class="original-exit">◆ Original exit</span> · <span class="hold">◆ Edited exit</span></span>
  <span class="memory" id="reset-legend" hidden>┆ Exit memory reset</span>"""

STYLE = """
.hold { color:#ddb1ff }
.memory { color:#8fdcff }
#mode { max-width:100% }
#policy { border-bottom:1px solid var(--line); line-height:1.5 }
"""

POLICY_SCRIPT = r"""
function updatePolicy() {
  $("mode").value = mode;
  $("policy").textContent = policies[mode][1];
  $("reset-legend").hidden = !resetsAtEntry();
}
function resetsAtEntry() {
  return mode === "local" || mode === "both" || mode === "fixed_local";
}
function memoryResetMarkers() {
  if (!resetsAtEntry()) return;
  for (const trade of trades()) {
    if (trade.entry < windowLeft || trade.entry > windowRight) continue;
    const x = xAt(trade.entry);
    line(x,plot.top,x,plot.top+17,"#8fdcff",[3,2]);
  }
}
"""


def render(sessions, extremes, target):
    """Write the five replay layers using the original chart and shared hold traces."""
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

    hold_script = IMPACT_SCRIPT.replace('"fixed_volume"', '"fixed_local"')
    replace("<title>MNQ · Reservoir Replay</title>", "<title>MNQ · Reservoir Trade Memory</title>")
    replace("<h1>MNQ Reservoir Replay</h1>", "<h1>Reservoir Trade Memory</h1>")
    replace("</style>", IMPACT_CSS + STYLE + "</style>")
    replace_section('  <div class="group" aria-label="Replay variant">',
                    '  <div class="group zoom"', MODE_CONTROLS)
    replace('<div class="legend">', EXTREME_CONTROLS + '<p class="hint" id="policy" aria-live="polite"></p>\n<div class="legend">')
    replace_section('  <span class="forecast">━ Forecast (pts)', '\n</div>', LEGEND)
    replace("</details>", """<p>The original forecast stays the same across all five modes. Hold values appear at completed bars while a trade is open. Positive values favor continuing either a long or a short. Zero or negative values request an exit at the next open. Entry-local exit memory starts over at the entry fill. The fresh-evidence policy applies to entries and leaves the original forecast intact.</p></details>""")
    replace('const sessions = JSON.parse($("replay-data").textContent).sessions;',
            'const {sessions,policies,extremes} = JSON.parse($("replay-data").textContent);')
    replace('let mode = "base";', 'let mode = "both";')
    replace('const reasons = {signal:', 'const reasons = {hold:"Hold exit",signal:')
    replace('return current()?.[mode] || [];', 'return current()?.layers?.[mode]?.trades || [];')
    replace('  sessionIndex = index;', '  activeCase = null;\n  sessionIndex = index;')
    replace('  mode = next;', '  activeCase = null;\n  mode = next;')
    replace('function current() {', hold_script + POLICY_SCRIPT + '\nfunction current() {')
    replace_section('  $("base").setAttribute', '  const net =', '  updatePolicy();\n  prepareHold();\n  updateComparison();\n')
    replace('Forecast <b>${points(bar[6])}</b>',
            'Original forecast <b>${points(bar[6])}</b> &nbsp; Hold <b>${points(holdSamples.get(bar[0])?.value)}</b>')
    replace_section("function forecastPanel", "function glyph", FORECAST_PANEL)
    replace_section("  const lock = current()?.lock;", "  const candleWidth", "")
    replace("  tradeMarkers(yAt);", "  tradeMarkers(yAt);\n  memoryResetMarkers();\n  impactExitMarkers(yAt);")
    replace('    const tag = clamp(x-19', '''    const hold = holdSamples.get(hoverBar[0]);
    if (hold) {
      ctx.fillStyle = holdColor;
      ctx.beginPath();
      ctx.arc(x,forecastY(hold.value),3,0,2*Math.PI);
      ctx.fill();
    }
    const tag = clamp(x-19''')
    replace_section('$("base").onclick', '$("out").onclick',
                    'for (const [key,[name]] of Object.entries(policies)) $("mode").add(new Option(name,key));\n'
                    '$("mode").onchange = event => changeMode(event.target.value);\n'
                    'for (const id of cases) $(id).onclick = () => jumpToCase(id);\n')
    replace("__REPLAY_DATA__", json.dumps(
        {"sessions": sessions, "policies": POLICIES, "extremes": extremes}, separators=(",", ":"), allow_nan=False
    ).replace("<", r"\u003c"))
    Path(target).write_text(source, encoding="utf-8")
