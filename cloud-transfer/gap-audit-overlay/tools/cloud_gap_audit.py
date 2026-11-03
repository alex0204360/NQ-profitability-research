"""Forensic gap and concentration audit of frozen MNQ trade journals."""
from __future__ import annotations

import html
import json
import statistics
from pathlib import Path

import pandas as pd

from tools.mnq_oracle_prepare import sha256
from tools.opportunity_research import read_records

ROOT = Path("/workspace")
PRIVATE = ROOT / "mnq-private-results"
OUT = ROOT / "outputs"
CASES = (
    ("Earlier $8 baseline", "fresh02", "gate8_delay0_stress"),
    ("Earlier $8 delayed", "fresh02", "gate8_delay1_stress"),
    ("Newer $8 baseline", "cloud_fresh03_lineage", "unchanged_8_gate_delay0_stress"),
    ("Newer $8 delayed", "cloud_fresh03_lineage", "unchanged_8_gate_delay1_stress"),
    ("Newer tree immediate", "cloud_fresh03_lineage", "extra_trees_dual_delay_delay0_stress"),
    ("Newer tree delayed", "cloud_fresh03_lineage", "extra_trees_dual_delay_delay1_stress"),
    ("Newer exit student immediate", "cloud_campaign02", "fresh03_oct30_nov02_delay0_stress"),
    ("Newer exit student delayed", "cloud_campaign02", "fresh03_oct30_nov02_delay1_stress"),
)


def verify_run(directory):
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest.get("completed") is not True:
        raise ValueError("Incomplete frozen run")
    for name, digest in manifest["files_sha256"].items():
        if sha256(directory / name) != digest:
            raise ValueError("Altered frozen artifact: " + name)


def summarize(trades):
    nets = [float(row["net"]) for row in trades]
    gap = [row for row in trades if "gap" in row["reason"]]
    return {"trades": len(trades), "reported_net_usd": sum(nets),
            "gap_trades": len(gap), "gap_trade_net_usd": sum(row["net"] for row in gap),
            "net_excluding_gap_trades_usd": sum(row["net"] for row in trades if "gap" not in row["reason"]),
            "top_one_trade_usd": max(nets) if nets else None,
            "top_five_trades_usd": sum(sorted(nets)[-5:]),
            "median_trade_usd": statistics.median(nets) if nets else None}


def build():
    for run in {case[1] for case in CASES}:
        verify_run(PRIVATE / run)
    entries = []
    for label, run, key in CASES:
        trades = read_records(PRIVATE / run / (key + "_trades_PRIVATE.jsonl.gz"))
        row = summarize(trades)
        row.update(label=label, run=run, journal=key)
        entries.append(row)
    source = pd.read_csv(PRIVATE / "cloud_fresh03_lineage/normalized_PRIVATE.csv")
    times = pd.to_datetime(source.timestamp_utc, utc=True)
    at = pd.Timestamp("2026-10-30T19:03:00Z")
    previous = times[times < at].iloc[-1]
    if at - previous != pd.Timedelta(minutes=10):
        raise ValueError("Expected nine missing minutes before gap exit")
    report = {"classification": "forensic_sensitivity_not_a_tradable_filter",
              "source_gap": {"previous_bar_start": previous.isoformat(),
                             "next_observed_bar_start": at.isoformat(),
                             "missing_minutes": 9},
              "cases": entries, "sealed_2025_access": False,
              "interpretation": "Removing a gap trade is a sensitivity calculation, not an entry rule. A future qualification gate must require zero unresolved-gap fills or independently verified executable prices."}
    (OUT / "mnq_gap_audit.json").write_text(json.dumps(report, indent=2) + "\n")
    def money(value):
        return "—" if value is None else f"${value:,.2f}"
    body = "\n".join("<tr>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in
        (row["label"], row["trades"], money(row["reported_net_usd"]), row["gap_trades"],
         money(row["gap_trade_net_usd"]), money(row["net_excluding_gap_trades_usd"]),
         money(row["top_five_trades_usd"]), money(row["median_trade_usd"]))) + "</tr>"
        for row in entries)
    page = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MNQ gap sensitivity</title>
<style>body{font:16px system-ui;max-width:1100px;margin:3rem auto;padding:0 1rem;color:#17212c;background:#f8fafc}h1{font-size:2rem}.status{background:#fee2e2;border-left:5px solid #b91c1c;padding:1rem}table{border-collapse:collapse;width:100%;background:white}th,td{padding:.55rem;border-bottom:1px solid #ccd4dd;text-align:right}th:first-child,td:first-child{text-align:left}th{background:#e8eef4}.scroll{overflow-x:auto}small{color:#465466}</style>
<main><h1>MNQ profit concentration and missing-bar sensitivity</h1><p class="status"><strong>The newer tree gain is not robust.</strong> One +$2,647 trade was booked at the next observed open after nine missing minute bars. Without that single trade, the tree's +$1,091 stressed immediate total becomes -$1,556. This is sensitivity accounting, not a strategy that could have known to skip the trade.</p>
<p>The source jumps from the October 30 18:53 UTC bar to 19:03 UTC. The execution replay labels the close as an unresolved gap at the next observed open. That price is not an independently verified fill. The new exit student's two-session positive total also includes gap trades.</p>
<div class="scroll"><table><thead><tr><th>Case</th><th>Trades</th><th>Reported stressed net</th><th>Gap trades</th><th>Gap-trade net</th><th>Net excluding gap trades</th><th>Top five trades</th><th>Median trade</th></tr></thead><tbody>""" + body + """</tbody></table></div>
<p><small>Removing trades after observing outcomes is not an executable policy. This audit tests sensitivity and source quality. Any future qualification must require zero unresolved-gap fills or verified executable prices, plus untouched forward data, measured costs, sufficient sessions and an agreed risk limit. Raw 2025 remains sealed; no orders were placed.</small></p></main></html>"""
    (OUT / "mnq_gap_audit.html").write_text(page, encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps({"cases": len(build()["cases"])}))
