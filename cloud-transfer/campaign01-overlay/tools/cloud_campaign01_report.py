"""Rebuild the public summary from the sealed local development result."""
from __future__ import annotations

import html
import json
from pathlib import Path

from tools.mnq_oracle_prepare import sha256

ROOT = Path("/workspace")
RUN = ROOT / "mnq-private-results/cloud_campaign01_retry2"
BASE = ROOT / "mnq-private-results/fresh02"
OUTPUT = ROOT / "outputs/mnq_cloud_campaign01.html"


def verified(directory: Path) -> dict:
    manifest = json.loads((directory / "manifest.json").read_text())
    if not manifest.get("completed"):
        raise ValueError("Incomplete run: " + str(directory))
    for name, digest in manifest["files_sha256"].items():
        if sha256(directory / name) != digest:
            raise ValueError("Artifact hash changed: " + name)
    return json.loads((directory / "results.json").read_text())


def build() -> Path:
    result = verified(RUN)
    baseline = verified(BASE)
    rows = []
    for candidate in result["attempts"]:
        for cell in candidate["evaluations"]:
            m = cell["metrics"]
            rows.append((candidate["candidate"], cell["delay"], cell["cost"], m["trades"],
                         m["net"], m["expectancy"], m["max_drawdown_bar_close"],
                         cell.get("session_bootstrap", {}).get("lower_2_5_percentile_usd_per_trade")))
    for cell in baseline["results"]:
        if cell["gate"] == 8:
            m = cell["metrics"]
            rows.append(("unchanged_$8_gate", cell["delay"], cell["cost"], m["trades"],
                         m["net"], m["expectancy"], m["max_drawdown_bar_close"],
                         cell.get("session_bootstrap", {}).get("lower_2_5_percentile_usd_per_trade")))
    if len(rows) != 18:
        raise ValueError("Expected two students and six baseline cells")
    def money(value):
        return "—" if value is None else f"${value:,.2f}"
    body = "\n".join("<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in
        (name, delay, cost, trades, money(net), money(mean), money(drawdown), money(lower))) + "</tr>"
        for name, delay, cost, trades, net, mean, drawdown, lower in rows)
    document = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MNQ cloud campaign 01</title>
<style>body{font:16px system-ui;max-width:1100px;margin:3rem auto;padding:0 1rem;color:#17212c;background:#f8fafc}h1{font-size:2rem} .status{background:#fee2e2;border-left:5px solid #b91c1c;padding:1rem}table{border-collapse:collapse;width:100%;background:white}th,td{padding:.55rem;border-bottom:1px solid #ccd4dd;text-align:right}th:first-child,td:first-child{text-align:left}th{background:#e8eef4} .scroll{overflow-x:auto}small{color:#465466}code{background:#e8eef4;padding:.1rem .25rem}</style>
<main><h1>MNQ: two execution-aware value students</h1><p class="status"><strong>Not ready for paper promotion or live trading.</strong> Both students lost money under stressed modeled costs. The $8 reference also fails a one-bar delay. No untouched confirmation or real-time paper operation has occurred.</p>
<p>Two models were registered before these student replays: ridge and extra trees. They use the same 18 causal features and all matured prior opportunities, including losing examples. Each predicts ten-bar gross value for next-open and one-bar-delayed entries; it trades only if both predicted directions clear $6 stressed round-trip cost. The unchanged $8 reference is shown for comparison.</p>
<h2>Modeled one-contract results</h2><div class="scroll"><table><thead><tr><th>Policy</th><th>Signal delay (bars)</th><th>Cost</th><th>Trades</th><th>Net</th><th>Net/trade</th><th>Bar-close drawdown</th><th>Session bootstrap lower net/trade</th></tr></thead><tbody>""" + body + """</tbody></table></div>
<p><small>Costs: base $4, stress $6, extreme $10 round trip. Delay 1 means the signal is placed one bar later, then filled at the following open. Drawdown is a modeled bar-close equity measure; intrabar risk may be worse. Bootstrap resamples whole sessions and is descriptive on this already inspected period.</small></p>
<h2>Decision and evidence</h2><p>Ridge: reject. Extra trees: reject. Neither meets the registered stressed profitability or uncertainty screens. The $8 gate remains a comparison baseline; it is not qualified. No candidate was selected from this campaign.</p>
<h2>Readiness limits</h2><ul><li>October 13–29, 2026 was already inspected development data, not untouched confirmation.</li><li>The original overlap audit found two conflicting source candles; this evaluation uses the upload alone.</li><li>Contract, roll, timestamp convention and realized fills remain independently unverified.</li><li>The user requested no maximum drawdown, so the goal's agreed risk-limit gate remains open.</li><li>2025 raw data remains sealed. No broker connection or live orders.</li></ul>
<p>Reproduce from <code>/workspace/mnq-oracle-code</code> with <code>python -c 'from tools.cloud_campaign01 import run; run("/workspace/mnq-private-results/NEW_EMPTY_RUN")'</code>, then <code>python -m tools.cloud_campaign01_report</code>. Use the validated Python environment. Saved model bundles, forecasts, trade and event journals, protocol and SHA-256 manifest remain in private local results. A research/paper decision API is available separately; API responses are proposals, not evidence of profit.</p></main></html>"""
    OUTPUT.write_text(document, encoding="utf-8")
    knowledge = {"status": "not_ready", "selected_candidate": None, "campaign": "CLOUD_CAMPAIGN01",
                 "research_result_sha256": sha256(RUN / "results.json"), "baseline_result_sha256": sha256(BASE / "results.json"),
                 "rows": [{"policy": n, "delay": d, "cost": c, "trades": t, "net_usd": net,
                           "expectancy_usd": mean, "drawdown_usd": dd, "bootstrap_lower_usd": lo}
                          for n, d, c, t, net, mean, dd, lo in rows],
                 "confirmation": "not_run", "paper_operation": "not_run", "sealed_2025_access": False}
    (OUTPUT.parent / "mnq_cloud_campaign01_knowledge.json").write_text(json.dumps(knowledge, indent=2) + "\n")
    return OUTPUT


if __name__ == "__main__":
    print(build())
