"""Render the verified multi-horizon development campaign as aggregate HTML."""
from __future__ import annotations

import html
import json
from pathlib import Path

from tools.mnq_oracle_prepare import sha256

RUN = Path("/workspace/mnq-private-results/cloud_campaign02")
OUTPUT = Path("/workspace/outputs/mnq_cloud_campaign02.html")


def build():
    manifest = json.loads((RUN / "manifest.json").read_text())
    if not manifest.get("completed"):
        raise ValueError("Incomplete campaign")
    for name, digest in manifest["files_sha256"].items():
        if sha256(RUN / name) != digest:
            raise ValueError("Changed campaign artifact: " + name)
    result = json.loads((RUN / "results.json").read_text())
    if result["fit_count"] != 1 or len(result["evaluations"]) != 18:
        raise ValueError("Unexpected campaign budget")
    rows = []
    for cell in result["evaluations"]:
        m = cell["metrics"]
        rows.append((cell["window"], cell["delay"], cell["cost"], m["trades"], m["net"],
                     m["expectancy"], m["max_drawdown_bar_close"],
                     cell.get("session_bootstrap", {}).get("lower_2_5_percentile_usd_per_trade")))
    def money(value):
        return "—" if value is None else f"${value:,.2f}"
    body = "\n".join("<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in
        (window, delay, cost, trades, money(net), money(mean), money(drawdown), money(lower))) + "</tr>"
        for window, delay, cost, trades, net, mean, drawdown, lower in rows)
    page = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MNQ exit-learning campaign</title>
<style>body{font:16px system-ui;max-width:1100px;margin:3rem auto;padding:0 1rem;color:#17212c;background:#f8fafc}h1{font-size:2rem}.status{background:#fee2e2;border-left:5px solid #b91c1c;padding:1rem}table{border-collapse:collapse;width:100%;background:white}th,td{padding:.55rem;border-bottom:1px solid #ccd4dd;text-align:right}th:first-child,td:first-child{text-align:left}th{background:#e8eef4}.scroll{overflow-x:auto}small{color:#465466}</style>
<main><h1>Learning entries and exits from hindsight outcomes</h1><p class="status"><strong>Not ready: reject this student.</strong> It lost on the 14-session development window under both immediate and delayed stressed fills. A two-session gain on the newer upload reversed under delay.</p>
<p>One registered extra-trees model learned expected gross MNQ value for four holding windows (3, 5, 10 and 20 bars) and two entry delays. Hindsight future prices supplied training targets only. The live-style inputs are 18 causal game-state features available at the decision close. The rule chooses an action only when both predicted fill timings clear modeled $6 stressed round-trip costs.</p>
<div class="scroll"><table><thead><tr><th>Development window</th><th>Delay</th><th>Cost</th><th>Trades</th><th>Net</th><th>Net/trade</th><th>Bar-close drawdown</th><th>Session bootstrap lower net/trade</th></tr></thead><tbody>""" + body + """</tbody></table></div>
<p><small>All three periods were already inspected before this campaign. The newest upload contains two sessions and an unresolved source overlap. Model predictions and a causal replay are research estimates, not realized fills or returns. The teacher's perfect exit is hindsight-only and cannot run live.</small></p>
<h2>Why the policy failed</h2><p>It chose the 20-bar exit for 4,320 of 4,322 active signals in the 14-session window, then lost $4,385.50 under stressed immediate fills. Its positive newer two-session result depended on five exceptional trades and became a $1,349.50 delayed loss. The unchanged $8 gate remains the comparison baseline, not a live qualification.</p>
<h2>Readiness</h2><p>No candidate is selected. There is no untouched confirmation, real-time paper record, verified contract and roll source, or agreed numerical drawdown limit. The research API exposes action values and reasons but submits no orders. Raw 2025 data remains sealed.</p></main></html>"""
    OUTPUT.write_text(page, encoding="utf-8")
    knowledge = {"status": "not_ready", "selected_candidate": None,
                 "results_sha256": sha256(RUN / "results.json"),
                 "rows": [{"window": w, "delay": d, "cost": c, "trades": t,
                           "net_usd": n, "expectancy_usd": mean,
                           "bar_close_drawdown_usd": dd, "bootstrap_lower_usd": lo}
                          for w, d, c, t, n, mean, dd, lo in rows],
                 "confirmation": "not_run", "paper_operation": "not_run",
                 "sealed_2025_access": False, "orders_submitted": 0}
    (OUTPUT.parent / "mnq_cloud_campaign02_knowledge.json").write_text(json.dumps(knowledge, indent=2) + "\n")
    return OUTPUT


if __name__ == "__main__":
    print(build())
