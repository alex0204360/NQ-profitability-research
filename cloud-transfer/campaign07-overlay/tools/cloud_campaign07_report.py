"""Compare the frozen $8 baseline, chart confluence, and earlier MNQ candidates."""
from __future__ import annotations

import html
import json
from pathlib import Path

from tools.mnq_oracle_prepare import sha256
from tools.opportunity_research import verify_manifest

ROOT = Path("/workspace")
PRIOR = ROOT / "mnq-private-results"
OUT = ROOT / "outputs"
PAGE = OUT / "mnq_gate8_comparison.html"
SUMMARY = OUT / "mnq_gate8_comparison.json"


def metrics(rows: list[dict], delay: int, *, cost: str = "stress", **match) -> dict:
    row = next(row for row in rows if row["delay"] == delay and row["cost"] == cost
               and all(row.get(key) == value for key, value in match.items()))
    result = {"trades": row["metrics"]["trades"], "net": row["metrics"]["net"],
              "drawdown": row["metrics"]["max_drawdown_bar_close"],
              "gap_exits": row["metrics"]["gap_unresolved_trades"]}
    bootstrap = row.get("session_bootstrap", {})
    result["active_sessions"] = bootstrap.get("active_sessions")
    result["lower_expectancy"] = bootstrap.get("lower_2_5_percentile_usd_per_trade")
    return result


def add_candidate(output: list[dict], label: str, origin: str, entries: list[dict],
                  extra: dict | None = None, **lookup) -> None:
    immediate = metrics(entries, 0, **lookup)
    delayed = metrics(entries, 1, **lookup)
    output.append({"label": label, "origin": origin, "immediate": immediate,
                   "delayed": delayed, **(extra or {})})


def aggregate() -> dict:
    hashes: dict[str, str] = {}
    for name in ("cloud_campaign07", "cloud_campaign06", "cloud_campaign01_retry2",
                 "cloud_campaign02", "cloud_campaign03", "cloud_fresh03_lineage", "fresh02"):
        verify_manifest(PRIOR / name, hashes)
    seventh = json.loads((PRIOR / "cloud_campaign07/results.json").read_text())
    sixth = json.loads((PRIOR / "cloud_campaign06/results.json").read_text())
    first = json.loads((PRIOR / "cloud_campaign01_retry2/results.json").read_text())
    second = json.loads((PRIOR / "cloud_campaign02/results.json").read_text())
    third = json.loads((PRIOR / "cloud_campaign03/results.json").read_text())
    newer = json.loads((PRIOR / "cloud_fresh03_lineage/results.json").read_text())
    if seventh["status"] != "complete_development" or sha256(ROOT / "mnq-oracle-code/docs/CLOUD_CAMPAIGN07.json") != json.loads((PRIOR / "cloud_campaign07/source_hashes.json").read_text())["CLOUD_CAMPAIGN07.json"]:
        raise ValueError("Confluence campaign changed or incomplete")
    windows = []
    for window in seventh["windows"]:
        identifier = window["id"]
        human = next(row for row in sixth["evaluations"] if row["window"] == identifier)
        rows = []
        add_candidate(rows, "Unchanged $8 gate", "frozen baseline", window["evaluations"], candidate="unchanged_8_gate")
        add_candidate(rows, "$8 + chart confluence", "fixed candidate", window["evaluations"], candidate="chart_confluence")
        add_candidate(rows, "Human chart retests, raw", "ungated control", human["evaluations"], candidate="raw_fixed10")
        if identifier == "upload_oct13_29":
            for attempt, label in (("extra_trees_dual_delay", "Tree action-value student"),
                                   ("ridge_dual_delay", "Ridge action-value student")):
                source = next(a["evaluations"] for a in first["attempts"] if a["candidate"] == attempt)
                add_candidate(rows, label, "prior student", source)
            add_candidate(rows, "Multi-horizon exit student", "prior student", second["evaluations"], window="fresh02_oct13_29")
            add_candidate(rows, "$8 + ATR bracket exit", "prior exit control", third["evaluations"], window="fresh02_oct13_29", rule="atr1_target1.5_time30")
        else:
            add_candidate(rows, "Tree action-value student", "gap-dependent prior student", newer["evaluations"], policy="extra_trees_dual_delay")
            add_candidate(rows, "Multi-horizon exit student", "gap-dependent prior student", second["evaluations"], window="fresh03_oct30_nov02")
        windows.append({"id": identifier, "observed_sessions": window["observed_sessions"],
                        "gate_signals": window["gate_signals"],
                        "confluence_signals": window["confluence_signals"],
                        "rows": rows})
    return {"status": "exploratory_comparison", "windows": windows,
            "conclusion": "The $8 gate is the highest reported stressed immediate net among the shown October 13–29 strategies, but lost $1,250 with one-bar delay and is not live-qualified. The chart confluence made money on only two filled trades per window and does not beat the baseline's total immediate net. Newer high student nets depend on unresolved gap fills.",
            "gap_sensitivity": {"newer_tree_immediate_reported_net": 1091.0,
                                "newer_tree_gap_trade_net": 2647.0,
                                "newer_tree_net_without_gap_trade": -1556.0,
                                "newer_exit_student_immediate_reported_net": 1379.0,
                                "newer_exit_student_gap_trade_net": 2921.0,
                                "newer_exit_student_net_without_gap_trades": -1542.0},
            "limitations": ["Already inspected 2026 development windows", "Unknown exact Yahoo contract/roll and minute convention",
                            "No finite live loss budget", "No untouched confirmation or continuously audited paper feed"],
            "live_authorized": False, "broker_orders": 0, "sealed_2025_access": False}


def render(data: dict) -> str:
    esc = lambda x: html.escape(str(x))
    def money(value: float) -> str:
        sign = "-" if value < 0 else "+" if value > 0 else ""
        return f"{sign}${abs(value):,.2f}"
    tables = []
    for window in data["windows"]:
        rows = []
        for entry in window["rows"]:
            immediate, delayed = entry["immediate"], entry["delayed"]
            rows.append(f'<tr><td>{esc(entry["label"])}</td><td>{immediate["trades"]}</td>'
                        f'<td>{money(immediate["net"])}</td><td>{money(delayed["net"])}</td>'
                        f'<td>{money(immediate["drawdown"])}</td><td>{immediate["gap_exits"]}</td>'
                        f'<td>{esc(entry["origin"])}</td></tr>')
        title = "October 13–29 · 14 sessions" if window["id"] == "upload_oct13_29" else "October 30–November 2 · 2 sessions"
        tables.append(f'<h2>{title}</h2><p class="funnel"><b>{window["gate_signals"]}</b> $8-gate signals '
                      f'→ <b>{window["confluence_signals"]}</b> same-direction chart confirmations '
                      f'→ <b>{next(r for r in window["rows"] if r["label"] == "$8 + chart confluence")["immediate"]["trades"]}</b> filled confluence trades.</p>'
                      f'<div class="tablewrap"><table><thead><tr><th>Policy</th><th>Trades</th><th>Immediate stress net</th>'
                      f'<th>Delayed stress net</th><th>Immediate drawdown</th><th>Gap exits</th><th>Role</th></tr></thead>'
                      f'<tbody>{"".join(rows)}</tbody></table></div>')
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MNQ $8 gate comparison</title><style>
:root{{color-scheme:dark;font-family:Inter,ui-sans-serif,system-ui,sans-serif}}
body{{margin:0;background:#0b1220;color:#eaf2ff}}main{{max-width:1160px;margin:auto;padding:30px 22px 70px}}
h1{{font-size:clamp(2rem,4vw,3.2rem)}}h2{{margin-top:35px}}p{{line-height:1.6;color:#bdd0e8;max-width:940px}}
.eyebrow{{color:#78cfff;text-transform:uppercase;letter-spacing:.12em;font-weight:700;font-size:.8rem}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin:20px 0}}
.card{{background:#15243b;border:1px solid #2e4767;border-radius:14px;padding:17px}}
.card strong{{font-size:1.65rem;display:block}}.card span{{color:#a8bfdc;font-size:.9rem}}
.warning{{background:#30231d;border-left:4px solid #ffb35c;padding:16px;border-radius:8px;color:#ffe1bd}}
.tablewrap{{overflow:auto;border:1px solid #2e4767;border-radius:12px}}table{{width:100%;border-collapse:collapse;font-size:.86rem}}
th,td{{text-align:left;padding:10px 12px;border-bottom:1px solid #29405e;white-space:nowrap}}th{{background:#1b2e49;color:#d1e7ff}}
tr:hover{{background:#17273f}}.funnel{{background:#15243b;border:1px solid #2e4767;padding:13px;border-radius:10px}}.funnel b{{color:#79d2ff}}
.small{{font-size:.88rem;color:#9db1ce}}a{{color:#82d6ff}}</style></head><body><main>
<div class="eyebrow">Frozen model comparison · November 3, 2026</div><h1>Is the $8 gate still the best MNQ candidate?</h1>
<p><b>For the 14-session October immediate-fill result, yes among these tested policies.</b> It earned +$196.50 after stressed costs. But a one-bar delay turned that into -$1,250, so it is not a live strategy. A chart-confirmation filter made the delayed result positive only by reducing participation to two filled trades.</p>
<div class="grid"><div class="card"><strong>+$196.50</strong><span>$8 gate · 14-session immediate stress</span></div>
<div class="card"><strong>-$1,250.00</strong><span>$8 gate · one-bar delayed stress</span></div>
<div class="card"><strong>+$91 / +$50</strong><span>Confluence immediate / delayed · two trades</span></div>
<div class="card"><strong>0</strong><span>Live-qualified candidates</span></div></div>
<div class="warning"><b>No live qualification.</b> The $8 gate fails delay robustness. Chart confluence has just two trades in each opened window, while the larger newer student profits relied on unverifiable gap exits. No broker orders were submitted.</div>
{''.join(tables)}
<h2>Why a larger newer result is not the answer</h2><p>The newer tree student reported +$1,091 immediately, but one +$2,647 trade exited at the next observed open after nine missing minutes. Removing that unverifiable trade as a sensitivity calculation leaves -$1,556. The newer multi-horizon student reported +$1,379, including +$2,921 across four gap exits; removing them leaves -$1,542. Removing trades after seeing outcomes is not a tradable rule.</p>
<h2>What the confluence test taught us</h2><p>Requiring agreement between a numerical forecast and a human-style level retest reduced the earlier window from 455 $8 signals to six confirmations and two filled trades. Those two earned +$91 immediately and +$50 delayed, but came from only two active sessions. In the newer window, two filled trades came from one active session. The fixed qualification screen requires at least 50 trades, ten active sessions, positive stressed and extreme outcomes under both fills, and an untouched source-audited confirmation period. None of these policies passed it. Changing the three-bar agreement window after seeing these outcomes would make the comparison misleading.</p>
<p class="small">All figures use one MNQ contract and the existing causal next-open replay on already inspected 2026 Yahoo-labeled sources. Exact contract/roll and minute convention are unverified. The aggregate JSON is <code>mnq_gate8_comparison.json</code>; private price bars and row-level journals are excluded.</p>
</main></body></html>'''


def run() -> dict:
    data = aggregate()
    OUT.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
    PAGE.write_text(render(data), encoding="utf-8")
    return data


if __name__ == "__main__":
    run()
