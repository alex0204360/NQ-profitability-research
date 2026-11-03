"""Render verified aggregate comparison for the frozen-entry bracket experiment."""
from __future__ import annotations

import html
import json
from pathlib import Path

from tools.mnq_oracle_prepare import sha256

RUN = Path("/workspace/mnq-private-results/cloud_campaign03")
OUTPUT = Path("/workspace/outputs/mnq_cloud_campaign03.html")


def build():
    manifest = json.loads((RUN / "manifest.json").read_text())
    if not manifest.get("completed"):
        raise ValueError("Incomplete bracket campaign")
    for name, digest in manifest["files_sha256"].items():
        if sha256(RUN / name) != digest:
            raise ValueError("Changed bracket artifact: " + name)
    result = json.loads((RUN / "results.json").read_text())
    if result["fit_count"] != 0 or len(result["evaluations"]) != 24:
        raise ValueError("Unexpected campaign budget")
    rows = []
    for cell in result["evaluations"]:
        m = cell["metrics"]
        rows.append((cell["window"], cell["rule"], cell["delay"], cell["cost"],
                     m["trades"], m["net"], m["expectancy"], m["max_drawdown_bar_close"],
                     cell.get("session_bootstrap", {}).get("lower_2_5_percentile_usd_per_trade")))
    def dollars(value):
        return "—" if value is None else f"${value:,.2f}"
    body = "\n".join("<tr>" + "".join(f"<td>{html.escape(str(x))}</td>" for x in
        (window, rule, delay, cost, trades, dollars(net), dollars(mean), dollars(dd), dollars(lower))) + "</tr>"
        for window, rule, delay, cost, trades, net, mean, dd, lower in rows)
    page = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MNQ bracket-exit campaign</title>
<style>body{font:16px system-ui;max-width:1100px;margin:3rem auto;padding:0 1rem;color:#17212c;background:#f8fafc}h1{font-size:2rem}.status{background:#fee2e2;border-left:5px solid #b91c1c;padding:1rem}table{border-collapse:collapse;width:100%;background:white}th,td{padding:.55rem;border-bottom:1px solid #ccd4dd;text-align:right}th:first-child,td:first-child{text-align:left}th{background:#e8eef4}.scroll{overflow-x:auto}small{color:#465466}</style>
<main><h1>Can a causal bracket improve the frozen $8 gate?</h1><p class="status"><strong>No. Reject the bracket exit.</strong> It lost more than the fixed ten-bar control under immediate and delayed stressed fills on the 14-session development window. No strategy is ready for live use.</p>
<p>The $8 entries, model, readiness and costs were unchanged. The alternative exit used a one-ATR stop, 1.5-ATR target and 30-bar cap, with conservative gap and ambiguous-bar handling. The identical signal streams were tested with $4, $6 and $10 modeled round-trip friction and zero/one-bar signal delay.</p>
<div class="scroll"><table><thead><tr><th>Window</th><th>Exit</th><th>Delay</th><th>Cost</th><th>Trades</th><th>Net</th><th>Net/trade</th><th>Bar-close drawdown</th><th>Bootstrap lower net/trade</th></tr></thead><tbody>""" + body + """</tbody></table></div>
<p><small>October 13–29 has 14 observed sessions; the newer upload has two. Both were already inspected before this experiment. Bootstrap bounds are descriptive, especially with two sessions. Neither the Yahoo file's exact contract/roll metadata nor actual order fills have been independently verified.</small></p>
<h2>What the result means</h2><p>Earlier positive $8 totals did not repeat reliably under delay and stress. The bracket rule increased trade count and worsened net performance and drawdown. Previous action-value and learned-exit extensions also failed their registered screens. No new policy was selected. The remaining path is a new audited feed, a frozen policy and risk limit, untouched forward observations, and measured real-time paper operation. Raw 2025 remains sealed; no orders were placed.</p></main></html>"""
    OUTPUT.write_text(page, encoding="utf-8")
    knowledge = {"status": "not_ready", "selected_candidate": None,
                 "results_sha256": sha256(RUN / "results.json"),
                 "rows": [{"window": w, "rule": r, "delay": d, "cost": c,
                           "trades": t, "net_usd": n, "expectancy_usd": mean,
                           "bar_close_drawdown_usd": dd, "bootstrap_lower_usd": lo}
                          for w, r, d, c, t, n, mean, dd, lo in rows],
                 "confirmation": "not_run", "paper_operation": "not_run",
                 "sealed_2025_access": False, "orders_submitted": 0}
    (OUTPUT.parent / "mnq_cloud_campaign03_knowledge.json").write_text(json.dumps(knowledge, indent=2) + "\n")
    return OUTPUT


if __name__ == "__main__":
    print(build())
