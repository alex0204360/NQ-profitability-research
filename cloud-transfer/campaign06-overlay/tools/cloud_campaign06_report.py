"""Aggregate dashboard and private chart for the fixed human-style MNQ campaign."""
from __future__ import annotations

import html
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from tools.cloud_campaign06 import OUT, PLAN, load_upload, state_and_setups
from tools.mnq_oracle_prepare import sha256
from tools.opportunity_research import read_records, verify_manifest

ROOT = Path("/workspace")
PUBLIC = ROOT / "outputs/mnq_human_chart_dashboard.html"
PRIVATE = ROOT / "outputs/mnq_human_chart_dashboard_PRIVATE.html"
CHART = ROOT / "outputs/mnq_human_chart_PRIVATE.png"
SUMMARY = ROOT / "outputs/mnq_human_chart_summary.json"


def aggregate() -> dict:
    hashes: dict[str, str] = {}
    verify_manifest(OUT, hashes)
    result = json.loads((OUT / "results.json").read_text())
    if result["status"] != "complete_development" or sha256(PLAN) != json.loads((OUT / "source_hashes.json").read_text())[PLAN.name]:
        raise ValueError("Incomplete or changed chart campaign")
    windows = []
    for window in result["evaluations"]:
        rows = []
        for entry in window["evaluations"]:
            metrics = entry["metrics"]
            rows.append({"candidate": entry["candidate"], "delay": entry["delay"], "cost": entry["cost"],
                         "trades": metrics["trades"], "net": metrics["net"],
                         "max_drawdown_bar_close": metrics["max_drawdown_bar_close"],
                         "gap_unresolved_trades": metrics["gap_unresolved_trades"],
                         "gap_exit_net_usd": entry["gap_exit_net_usd"],
                         "bootstrap_lower_usd_per_trade": entry.get("session_bootstrap", {}).get("lower_2_5_percentile_usd_per_trade"),
                         "active_sessions": entry.get("session_bootstrap", {}).get("active_sessions")})
        windows.append({"id": window["window"], "observed_sessions": window["observed_sessions"],
                        "ready_bars": window["ready_bars"], "raw_setup_counts": window["raw_setup_counts"],
                        "signals": window["signals"], "evaluations": rows})
    return {"status": "complete_exploratory_development", "calibration": result["calibration"],
            "windows": windows, "primary": "gated_fixed10", "selected_for_live": False,
            "source_verified": False, "sealed_2025_access": False, "broker_orders": 0,
            "method": "Confirmed horizontal support/resistance and two-confirmed-pivot trendline retests; Beta(2,2) training-only win probability with payoff-aware lower-bound gate; causal next-open replay."}


def render(report: dict, *, private: bool = False) -> str:
    esc = lambda value: html.escape(str(value))
    def money(value: float) -> str:
        sign = "-" if value < 0 else "+" if value > 0 else ""
        return f"{sign}${abs(value):,.2f}"
    by_window = {window["id"]: window for window in report["windows"]}
    def result(window_id: str, candidate: str, delay: int, cost: str = "stress") -> dict:
        return next(row for row in by_window[window_id]["evaluations"]
                    if row["candidate"] == candidate and row["delay"] == delay and row["cost"] == cost)
    qualified = sum(bool(row["allowed"]) for row in report["calibration"].values())
    gated_net = sum(result(window["id"], "gated_fixed10", 0)["net"] for window in report["windows"])
    october_raw = result("upload_oct13_29", "raw_fixed10", 0)["net"]
    newer_raw = result("upload_oct30_nov02", "raw_fixed10", 0)["net"]
    calibration_rows = []
    for name, row in report["calibration"].items():
        breakeven = "n/a" if row["empirical_breakeven_probability"] is None else f'{row["empirical_breakeven_probability"]:.1%}'
        mean = "n/a" if row["mean_robust_stress_net_usd"] is None else money(row["mean_robust_stress_net_usd"])
        calibration_rows.append(f'<tr><td>{esc(name)}</td><td>{row["examples"]}</td><td>{row["wins"]}</td>'
                                f'<td>{row["posterior_win_probability"]:.1%}</td><td>{row["lower_10pct_win_probability"]:.1%}</td>'
                                f'<td>{breakeven}</td><td>{mean}</td><td>{"allow" if row["allowed"] else "abstain"}</td></tr>')
    table_rows = []
    for window in report["windows"]:
        for candidate in ("gated_fixed10", "raw_fixed10", "gated_atr_bracket"):
            immediate = next(row for row in window["evaluations"] if row["candidate"] == candidate and row["delay"] == 0 and row["cost"] == "stress")
            delayed = next(row for row in window["evaluations"] if row["candidate"] == candidate and row["delay"] == 1 and row["cost"] == "stress")
            lower = immediate["bootstrap_lower_usd_per_trade"]
            table_rows.append(f'<tr><td>{esc(window["id"])}</td><td>{window["observed_sessions"]}</td>'
                              f'<td>{esc(candidate)}</td><td>{immediate["trades"]}</td>'
                              f'<td>{money(immediate["net"])}</td><td>{money(delayed["net"])}</td>'
                              f'<td>{"n/a" if lower is None else money(lower)}</td>'
                              f'<td>{immediate["gap_unresolved_trades"]}</td></tr>')
    chart_html = ('<h2>Actual chart trace · private local data</h2><p>The raw short setup retested confirmed resistance after a completed candle. '
                  'Its next-open ten-bar trade lost $95 under stressed costs. The probability gate correctly marked this setup as unqualified; '
                  'the plot shows levels available at each minute, not future levels drawn backward.</p>'
                  '<img class="chart" src="mnq_human_chart_PRIVATE.png" alt="MNQ price with causal confirmed support, resistance, trendlines, and one losing raw trade">') if private else ''
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MNQ chart-reading research dashboard</title><style>
:root{{color-scheme:dark;font-family:Inter,ui-sans-serif,system-ui,sans-serif}}
body{{margin:0;background:#0b1220;color:#eaf2ff}}main{{max-width:1200px;margin:auto;padding:30px 22px 70px}}
h1{{font-size:clamp(2rem,4vw,3.2rem)}}h2{{margin-top:35px}}p{{color:#bdd0e8;line-height:1.6;max-width:970px}}
.eyebrow{{color:#75caff;text-transform:uppercase;letter-spacing:.12em;font-weight:700;font-size:.8rem}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin:20px 0}}
.card{{background:#15243b;border:1px solid #2e4767;border-radius:14px;padding:17px}}
.card strong{{font-size:1.7rem;display:block}}.card span{{font-size:.9rem;color:#a9bfdc}}
.warning{{padding:16px;background:#30231d;border-left:4px solid #ffb35c;border-radius:8px;color:#ffe1bd}}
.flow{{display:flex;flex-wrap:wrap;gap:10px;margin:20px 0}}.step{{flex:1;min-width:180px;background:#15243b;border:1px solid #2e4767;padding:14px;border-radius:12px}}
.step b{{display:block;color:#75caff}}.step small{{color:#b9cce4;line-height:1.5}}
.tablewrap{{overflow:auto;border:1px solid #2e4767;border-radius:12px}}table{{border-collapse:collapse;width:100%;font-size:.88rem}}
th,td{{text-align:left;padding:10px 12px;border-bottom:1px solid #29405e;white-space:nowrap}}th{{background:#1b2e49;color:#d1e7ff}}
tr:hover{{background:#17273f}}.chart{{max-width:100%;border-radius:12px;border:1px solid #2e4767}}
.small{{font-size:.88rem;color:#9db1ce}}a{{color:#82d6ff}}</style></head><body><main>
<div class="eyebrow">Fixed chart policy · November 3, 2026</div><h1>Can support, resistance, and trendlines improve MNQ trades?</h1>
<p>This experiment translates familiar chart reading into rules you can inspect: confirmed support/resistance, a trendline through two confirmed pivots, a retest candle, and a payoff-aware win-probability gate learned only from earlier sessions. Every entry is placed at the next observed open.</p>
<div class="grid"><div class="card"><strong>{qualified}</strong><span>Probability-qualified setups</span></div>
<div class="card"><strong>{money(gated_net)}</strong><span>Primary gated net · no trades</span></div>
<div class="card"><strong>{money(october_raw)}</strong><span>Ungated October 13–29 stress net</span></div>
<div class="card"><strong>{money(newer_raw)}</strong><span>Ungated newer two-session stress net</span></div></div>
<div class="warning"><b>Live-trading status: blocked.</b> The probability gate abstained everywhere; the ungated rule lost across the longer 14-session upload. The newer positive two-session result is too short to qualify. Contract/roll identity remains unverified, and no broker orders were sent.</div>
<h2>How the chart rule thinks</h2><div class="flow">
<div class="step"><b>1 · Plot completed candles</b><small>Build EMA trend, ATR, and nearest confirmed support/resistance. Confirm a pivot only after two later candles close.</small></div>
<div class="step"><b>2 · Wait for a retest</b><small>Price touches a horizontal level or projected two-pivot trendline within 0.25 ATR, then closes back in the trend direction.</small></div>
<div class="step"><b>3 · Price the risk</b><small>Use earlier matured examples to estimate win probability, mean win, mean loss, and the breakeven probability after stressed costs and fill delay.</small></div>
<div class="step"><b>4 · Enter or abstain</b><small>Trade only if the conservative probability bound beats breakeven and historical mean net is positive. Here, every setup abstained.</small></div></div>
<h2>What earlier examples taught the probability gate</h2><div class="tablewrap"><table><thead><tr><th>Setup</th><th>Examples</th><th>Wins</th><th>Posterior P(win)</th><th>Conservative P(win)</th><th>Breakeven P</th><th>Mean robust net</th><th>Decision</th></tr></thead><tbody>{''.join(calibration_rows)}</tbody></table></div>
<p class="small">Robust net uses the worse of immediate and one-bar-delayed fills at a fixed ten-bar exit, after $6 stressed round-trip cost. The conservative probability is the 10th percentile of a Beta(2,2) posterior. Small samples and unequal win/loss sizes matter.</p>
<h2>Replay across fixed development windows</h2><div class="tablewrap"><table><thead><tr><th>Source window</th><th>Sessions</th><th>Policy</th><th>Trades</th><th>Immediate stress net</th><th>Delayed stress net</th><th>Bootstrap lower expectancy</th><th>Gap exits</th></tr></thead><tbody>{''.join(table_rows)}</tbody></table></div>
<p>The raw setup is a descriptive control with no probability gate. The gated ATR bracket is a registered secondary exit sensitivity; it also abstained because no entry passed. All source windows were already inspected in prior research, so none is fresh confirmation. The unchanged $8 gate made +$196.50 immediate / -$1,250 delayed on the 14-session October upload; this human-style raw rule was worse there.</p>
{chart_html}
<h2>What this says about predicting a chart</h2><p>A trendline is a summary of past prices, not a physical path the market must follow. A support touch can precede either a bounce or a break. Historical future bars can teach the probabilities of those outcomes; they cannot reveal which one a live chart will take. This run made that uncertainty explicit and abstained when the conservative probability did not beat the observed payoff threshold.</p>
<p class="small">Reproducible aggregate: <code>mnq_human_chart_summary.json</code>. Private candles and trade journals are not embedded in the published dashboard. Raw 2025 remained sealed.</p>
</main></body></html>'''


def make_private_chart() -> None:
    os.environ.setdefault("MPLCONFIGDIR", "/workspace/.matplotlib")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    bars, _ = load_upload(ROOT / "mnq-private-results/fresh01", blocked=True)
    _, _, _, levels = state_and_setups(bars)
    start, end = pd.Timestamp("2026-10-13T15:00:00Z"), pd.Timestamp("2026-10-13T16:20:00Z")
    mask = ((bars.timestamp >= start) & (bars.timestamp <= end)).to_numpy()
    if mask.sum() < 40:
        raise ValueError("Insufficient contiguous chart context")
    indices = np.flatnonzero(mask)
    times = bars.timestamp.iloc[indices].dt.tz_convert("America/New_York")
    fig, ax = plt.subplots(figsize=(13, 6), facecolor="#0b1220")
    ax.set_facecolor("#0b1220")
    ax.plot(times, bars.close.iloc[indices], color="#ecf4ff", linewidth=1.8, label="Completed close")
    for key, color, label in (("horizontal_support", "#35c9a2", "Confirmed support"),
                              ("horizontal_resistance", "#ffb454", "Confirmed resistance"),
                              ("trendline_support", "#4f9dff", "Projected rising line"),
                              ("trendline_resistance", "#ed78a1", "Projected falling line")):
        values = np.asarray(levels[key])[indices]
        ax.plot(times, values, color=color, alpha=.8, linewidth=1.2, label=label)
    trades = read_records(OUT / "upload_oct13_29_raw_fixed10_delay0_stress_trades_PRIVATE.jsonl.gz")
    chosen = next(trade for trade in trades if trade["signal_time"] == "2026-10-13T15:45:00+00:00")
    signal_time = pd.Timestamp(chosen["signal_time"]).tz_convert("America/New_York")
    exit_time = pd.Timestamp(chosen["exit_bar_time"]).tz_convert("America/New_York")
    ax.axvline(signal_time, color="#ff6b6b", linestyle="--", linewidth=1.5)
    ax.axvline(exit_time, color="#ff6b6b", linestyle=":", linewidth=1.5)
    ax.scatter([signal_time], [bars.close.iloc[chosen["signal_index"]]], color="#ff6b6b", s=70, zorder=5)
    sign = "-" if chosen["net"] < 0 else "+" if chosen["net"] > 0 else ""
    ax.annotate(f'Raw short retest\n{sign}${abs(chosen["net"]):.2f} stress',
                (signal_time, bars.close.iloc[chosen["signal_index"]]), xytext=(10, 20),
                textcoords="offset points", color="#ffd4d4", fontsize=10)
    ax.set_title("MNQ October 13, 2026 · causal chart levels · 11:00–12:20 New York time",
                 color="#eaf2ff", fontsize=15, pad=14)
    ax.set_ylabel("Index points", color="#bdd0e8")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=times.dt.tz))
    ax.tick_params(colors="#bdd0e8")
    ax.grid(color="#31445e", alpha=.45)
    ax.legend(facecolor="#15243b", edgecolor="#31445e", labelcolor="#eaf2ff", loc="best")
    fig.tight_layout()
    fig.savefig(CHART, dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)


def run() -> dict:
    report = aggregate()
    SUMMARY.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    PUBLIC.write_text(render(report), encoding="utf-8")
    make_private_chart()
    PRIVATE.write_text(render(report, private=True), encoding="utf-8")
    return report


if __name__ == "__main__":
    run()
