"""Build an aggregate HTML dashboard from verified fresh03 private artifacts."""
from __future__ import annotations

import html
import json
from pathlib import Path

from tools.mnq_oracle_prepare import sha256

ROOT = Path("/workspace")
RUN = ROOT / "mnq-private-results/cloud_fresh03_lineage"
OUTPUT = ROOT / "outputs/mnq_fresh03.html"


def build():
    manifest = json.loads((RUN / "manifest.json").read_text())
    if not manifest.get("completed"):
        raise ValueError("Incomplete fresh03 run")
    for name, digest in manifest["files_sha256"].items():
        if sha256(RUN / name) != digest:
            raise ValueError("Changed fresh03 artifact: " + name)
    result = json.loads((RUN / "results.json").read_text())
    if result["status"] != "complete_diagnostic_not_confirmation" or len(result["evaluations"]) != 18:
        raise ValueError("Unexpected diagnostic status or evaluation count")
    rows = []
    for cell in result["evaluations"]:
        metric = cell["metrics"]
        lower = cell.get("session_bootstrap", {}).get("lower_2_5_percentile_usd_per_trade")
        rows.append((cell["policy"], cell["delay"], cell["cost"], metric["trades"],
                     metric["net"], metric["expectancy"], metric["max_drawdown_bar_close"], lower))
    def fmt(value):
        return "—" if value is None else f"${value:,.2f}"
    table = "\n".join("<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in
        (name, delay, cost, trades, fmt(net), fmt(mean), fmt(drawdown), fmt(lower))) + "</tr>"
        for name, delay, cost, trades, net, mean, drawdown, lower in rows)
    page = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MNQ Fresh03 diagnostic</title>
<style>body{font:16px system-ui;max-width:1100px;margin:3rem auto;padding:0 1rem;color:#17212c;background:#f8fafc}h1{font-size:2rem}.status{background:#fee2e2;border-left:5px solid #b91c1c;padding:1rem}table{border-collapse:collapse;width:100%;background:white}th,td{padding:.55rem;border-bottom:1px solid #ccd4dd;text-align:right}th:first-child,td:first-child{text-align:left}th{background:#e8eef4}.scroll{overflow-x:auto}small{color:#465466}</style>
<main><h1>MNQ November upload diagnostic</h1><p class="status"><strong>Not ready.</strong> Two observed sessions are insufficient for repeatability, and the source contract and roll metadata are unverified. No candidate was selected or paper-traded.</p>
<p>The uploaded 2026 CSV was evaluated alone, with its October 28–29 bars used only as warmup. Two of 3,226 rows overlapping the earlier upload disagree, so the two sources were never spliced. All policies and execution assumptions were frozen before this diagnostic: unchanged $8 gate, two previously rejected value students, $4/$6/$10 modeled round-trip costs, immediate and one-bar-delayed signals, and fixed ten-bar exits.</p>
<div class="scroll"><table><thead><tr><th>Policy</th><th>Signal delay</th><th>Cost</th><th>Trades</th><th>Net</th><th>Net/trade</th><th>Bar-close drawdown</th><th>Session bootstrap lower net/trade</th></tr></thead><tbody>""" + table + """</tbody></table></div>
<p><small>The session bootstrap has only two observed sessions and does not support a robust confidence claim. Bar-close drawdown can miss intrabar risk. The October 13–29 development results remain part of the evidence: the $8 gate lost $1,250 with delayed stressed fills there, and both new students failed their registered screens.</small></p>
<h2>Decision and limits</h2><p>Keep the $8 gate as a comparison baseline. Reject ridge. Reject extra trees: its immediate gain turned into a delayed loss. No numerical drawdown limit was agreed, so the risk gate remains open. The filename claims Yahoo MNQ, but the exact contract, timestamp convention, and roll rule were not supplied. This is a retrospective upload, not real-time paper operation or untouched confirmation. Raw 2025 remains sealed; no orders were submitted.</p></main></html>"""
    OUTPUT.write_text(page, encoding="utf-8")
    knowledge = {"status": "not_ready", "selection": None, "observed_sessions": result["observed_sessions"],
                 "source_sha256": json.loads((RUN / "protocol.json").read_text())["source_sha256"],
                 "results_sha256": sha256(RUN / "results.json"), "evaluations": [
                     {"policy": name, "delay": delay, "cost": cost, "trades": trades,
                      "net_usd": net, "expectancy_usd": mean, "bar_close_drawdown_usd": drawdown,
                      "bootstrap_lower_usd": lower} for name, delay, cost, trades, net, mean, drawdown, lower in rows],
                 "confirmation": "not_run", "prospective_paper": "not_run", "sealed_2025_access": False}
    (OUTPUT.parent / "mnq_fresh03_knowledge.json").write_text(json.dumps(knowledge, indent=2) + "\n")
    return OUTPUT


if __name__ == "__main__":
    print(build())
