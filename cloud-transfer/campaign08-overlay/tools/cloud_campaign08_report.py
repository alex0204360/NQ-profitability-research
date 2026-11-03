"""Aggregate calibration, economics, and account-risk dashboard for campaign08."""
from __future__ import annotations

import html
import json
from pathlib import Path

from tools.mnq_oracle_prepare import sha256
from tools.opportunity_research import verify_manifest

ROOT = Path("/workspace")
PRIOR = ROOT / "mnq-private-results/cloud_campaign08"
PLAN = ROOT / "mnq-oracle-code/docs/CLOUD_CAMPAIGN08.json"
OUT = ROOT / "outputs"
PAGE = OUT / "mnq_physics_filter_dashboard.html"
SUMMARY = OUT / "mnq_physics_filter_summary.json"
ACCOUNT_USD = 25000.
REFERENCE_DRAWDOWN_USD = 1500.


def aggregate() -> dict:
    hashes: dict[str, str] = {}
    verify_manifest(PRIOR, hashes)
    sources = json.loads((PRIOR / "source_hashes.json").read_text())
    if sha256(PLAN) != sources[PLAN.name]:
        raise ValueError("Frozen physics plan changed")
    result = json.loads((PRIOR / "results.json").read_text())
    if result["status"] != "complete_development" or len(result["windows"]) != 2:
        raise ValueError("Incomplete fixed physics campaign")
    windows = []
    for window in result["windows"]:
        entries = []
        for candidate in ("unchanged_8_gate", "persistent_2bar", "diffusion_p60", "persistent_and_diffusion"):
            for delay in (0, 1):
                rows = [row for row in window["evaluations"] if row["candidate"] == candidate and row["delay"] == delay]
                if len(rows) != 3:
                    raise ValueError("Incomplete cost matrix")
                cost = {row["cost"]: row for row in rows}
                stress = cost["stress"]
                drawdown = stress["metrics"]["max_drawdown_bar_close"]
                entries.append({"candidate": candidate, "delay": delay,
                                "trades": stress["metrics"]["trades"],
                                "base_net": cost["base"]["metrics"]["net"],
                                "stress_net": stress["metrics"]["net"],
                                "extreme_net": cost["extreme"]["metrics"]["net"],
                                "stress_drawdown_usd": drawdown,
                                "stress_drawdown_pct_account": 100 * drawdown / ACCOUNT_USD,
                                "exceeds_1500_reference": drawdown > REFERENCE_DRAWDOWN_USD,
                                "gap_exits": stress["metrics"]["gap_unresolved_trades"],
                                "active_sessions": stress["session_bootstrap"]["active_sessions"],
                                "bootstrap_lower_usd_per_trade": stress["session_bootstrap"]["lower_2_5_percentile_usd_per_trade"]})
        windows.append({"id": window["id"], "observed_sessions": window["observed_sessions"],
                        "signal_counts": window["signal_counts"],
                        "probability_diagnostic": window["probability_diagnostic"],
                        "entries": entries})
    return {"status": "rejected_development", "windows": windows,
            "account_reference": {"starting_equity_usd": ACCOUNT_USD,
                                  "maximum_drawdown_reference_usd": REFERENCE_DRAWDOWN_USD,
                                  "reference_pct_equity": 100 * REFERENCE_DRAWDOWN_USD / ACCOUNT_USD,
                                  "firm_rule_verified": False},
            "result": "The past-only normal drift/diffusion probabilities were overconfident and less calibrated than a constant base-rate forecast; persistence and diffusion filters lost more than the unchanged $8 gate on the 14-session window. No candidate promoted.",
            "limitations": ["Pre-registered before the user supplied the $1,500 account drawdown reference",
                            "Bar-close research drawdown is not a verified firm's trailing-drawdown rule",
                            "Already opened Yahoo-labeled development data with unverified contract/roll/timestamp identity",
                            "No untouched confirmation or live feed"],
            "live_authorized": False, "broker_orders": 0, "sealed_2025_access": False}


def render(data: dict) -> str:
    esc = lambda value: html.escape(str(value))
    def money(value: float) -> str:
        sign = "-" if value < 0 else "+" if value > 0 else ""
        return f"{sign}${abs(value):,.2f}"
    earlier = data["windows"][0]
    combined_immediate = next(e for e in earlier["entries"] if e["candidate"] == "persistent_and_diffusion" and e["delay"] == 0)
    combined_delayed = next(e for e in earlier["entries"] if e["candidate"] == "persistent_and_diffusion" and e["delay"] == 1)
    earlier_calibration = earlier["probability_diagnostic"]
    high_bin = earlier_calibration["bins"][-1]
    tables = []
    for window in data["windows"]:
        title = "October 13–29 · 14 sessions" if window["id"] == "upload_oct13_29" else "October 30–November 2 · 2 sessions"
        rows = []
        for candidate in ("unchanged_8_gate", "persistent_2bar", "diffusion_p60", "persistent_and_diffusion"):
            immediate = next(e for e in window["entries"] if e["candidate"] == candidate and e["delay"] == 0)
            delayed = next(e for e in window["entries"] if e["candidate"] == candidate and e["delay"] == 1)
            rows.append(f'<tr><td>{esc(candidate)}</td><td>{immediate["trades"]}</td>'
                        f'<td>{money(immediate["stress_net"])}</td><td>{money(delayed["stress_net"])}</td>'
                        f'<td>{money(immediate["stress_drawdown_usd"])}</td>'
                        f'<td>{"over $1,500" if immediate["exceeds_1500_reference"] else "under $1,500"}</td>'
                        f'<td>{immediate["active_sessions"]}</td></tr>')
        diagnostic = window["probability_diagnostic"]
        calibration_rows = []
        for bin_ in diagnostic["bins"]:
            if not bin_["count"]:
                continue
            predicted = bin_["mean_predicted"]
            observed = bin_["observed_positive_rate"]
            calibration_rows.append(f'<tr><td>{bin_["lower"]:.0%}–{bin_["upper"]:.0%}</td><td>{bin_["count"]}</td>'
                                    f'<td>{predicted:.1%}<div class="bar prediction" style="width:{predicted*100:.1f}%"></div></td>'
                                    f'<td>{observed:.1%}<div class="bar observed" style="width:{observed*100:.1f}%"></div></td></tr>')
        tables.append(f'<h2>{title}</h2><p>Frozen $8 signals: {window["signal_counts"]["unchanged_8_gate"]}; '
                      f'two-bar persistent: {window["signal_counts"]["persistent_2bar"]}; '
                      f'diffusion p&gt;60%: {window["signal_counts"]["diffusion_p60"]}; '
                      f'both: {window["signal_counts"]["persistent_and_diffusion"]}.</p>'
                      f'<div class="tablewrap"><table><thead><tr><th>Fixed policy</th><th>Trades</th><th>Immediate stress net</th>'
                      f'<th>Delayed stress net</th><th>Immediate drawdown</th><th>$1,500 reference</th>'
                      f'<th>Active sessions</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
                      f'<p>The diffusion model predicted {diagnostic["mean_predicted_probability"]:.1%} positive outcomes on average; '
                      f'{diagnostic["observed_positive_rate"]:.1%} occurred. Its Brier error was '
                      f'{diagnostic["brier"]:.3f} versus {diagnostic["base_rate_brier"]:.3f} for a constant observed base-rate forecast.</p>'
                      f'<div class="tablewrap"><table><thead><tr><th>Predicted bin</th><th>Gate signals</th>'
                      f'<th>Mean modeled probability</th><th>Observed positive rate</th></tr></thead>'
                      f'<tbody>{"".join(calibration_rows)}</tbody></table></div>')
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MNQ drift-diffusion filter experiment</title><style>
:root{{color-scheme:dark;font-family:Inter,ui-sans-serif,system-ui,sans-serif}}
body{{margin:0;background:#0b1220;color:#eaf2ff}}main{{max-width:1160px;margin:auto;padding:30px 22px 70px}}
h1{{font-size:clamp(2rem,4vw,3.2rem)}}h2{{margin-top:36px}}p{{line-height:1.6;color:#bdd0e8;max-width:960px}}
.eyebrow{{color:#78cfff;text-transform:uppercase;letter-spacing:.12em;font-weight:700;font-size:.8rem}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin:20px 0}}
.card{{background:#15243b;border:1px solid #2e4767;border-radius:14px;padding:17px}}
.card strong{{font-size:1.55rem;display:block}}.card span{{color:#a8bfdc;font-size:.9rem}}
.warning{{background:#30231d;border-left:4px solid #ffb35c;padding:16px;border-radius:8px;color:#ffe1bd}}
.tablewrap{{overflow:auto;border:1px solid #2e4767;border-radius:12px}}table{{width:100%;border-collapse:collapse;font-size:.86rem}}
th,td{{text-align:left;padding:10px 12px;border-bottom:1px solid #29405e;white-space:nowrap}}th{{background:#1b2e49;color:#d1e7ff}}
tr:hover{{background:#17273f}}.bar{{height:5px;border-radius:3px;margin-top:3px}}.prediction{{background:#75caff}}.observed{{background:#ffb35c}}
.small{{font-size:.88rem;color:#9db1ce}}</style></head><body><main>
<div class="eyebrow">Math and physics hypothesis · November 3, 2026</div><h1>Did persistence and drift–diffusion improve the $8 gate?</h1>
<p><b>No.</b> A two-bar signal debounce and a past-only normal drift–diffusion estimate were fixed before scoring. The model estimated the probability that ten minutes of price movement would clear $6 stressed MNQ costs. That estimate was poorly calibrated, and the filtered trading results were worse than the unchanged gate on the longer window.</p>
<div class="grid"><div class="card"><strong>{money(combined_immediate["stress_net"])}</strong><span>Combined filter · 14-session immediate stress</span></div>
<div class="card"><strong>{money(combined_delayed["stress_net"])}</strong><span>Combined filter · delayed stress</span></div>
<div class="card"><strong>{earlier_calibration["brier"]:.3f} vs {earlier_calibration["base_rate_brier"]:.3f}</strong><span>Physics versus base-rate Brier error</span></div>
<div class="card"><strong>{data["account_reference"]["reference_pct_equity"]:.0f}%</strong><span>$1,500 of $25,000 account reference</span></div></div>
<div class="warning"><b>Rejected for trading.</b> The combined filter lost money under both fill timings and its 14-session bar-close drawdown exceeded the $1,500 reference. A firm's actual trailing-drawdown rules have not been verified. No broker orders were sent.</div>
<h2>The hypothesis</h2><p>Persistence asks whether the frozen $8 direction survives two consecutive completed bars. Diffusion estimates the last 31 one-minute price changes, then projects a ten-minute normal distribution while adding uncertainty in the estimated drift. It keeps a gate signal only when the modeled chance of exceeding three index points in that direction is above 60%. This is a falsifiable approximation, not a physical law governing markets.</p>
{''.join(tables)}
<h2>What failed</h2><p>High modeled probability did not imply a high observed win rate on the longer window. In its 80–100% probability bin, the mean forecast was {high_bin["mean_predicted"]:.1%}, while only {high_bin["observed_positive_rate"]:.1%} of matured gate opportunities cleared stressed costs. The 60% filter therefore selected the wrong opportunities; persistence also amplified losses. Adjusting that cutoff or reversing the signal now would optimize an already opened sample.</p>
<p class="small">Risk figures use research bar-close drawdown on one MNQ contract, not a verified firm's liquidation rule. Both source windows were previously inspected Yahoo-labeled data with unknown exact contract/roll and minute convention. Aggregate JSON: <code>mnq_physics_filter_summary.json</code>. No raw 2025 data or live orders were used.</p>
</main></body></html>'''


def run() -> dict:
    data = aggregate()
    OUT.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
    PAGE.write_text(render(data), encoding="utf-8")
    return data


if __name__ == "__main__":
    run()
