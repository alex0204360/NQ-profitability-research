"""One frozen confluence test: $8 gate plus recent causal chart retest."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from tools.causal_execution import replay_causal
from tools.cloud_campaign06 import load_upload, state_and_setups
from tools.fresh_transfer_test import delayed_signal, lower_bound, session_days
from tools.mnq_oracle_prepare import sha256
from tools.mnq_oracle_research import save_json
from tools.opportunity_research import COSTS, read_records, verify_manifest, write_records

ROOT = Path("/workspace")
CODE = Path(__file__).resolve().parents[1]
PLAN = CODE / "docs/CLOUD_CAMPAIGN07.json"
PRIOR = ROOT / "mnq-private-results"
OUT = PRIOR / "cloud_campaign07"


def recent_confluence(gate: np.ndarray, setups: np.ndarray, segments: np.ndarray) -> tuple[np.ndarray, list[str]]:
    """Retain gate direction only when same-side setup fired in last three contiguous bars."""
    if gate.shape != (len(setups),) or setups.shape != (len(gate), 2, 2) or segments.shape != gate.shape:
        raise ValueError("Aligned gate, chart setup, and segments required")
    if not np.isin(gate, [-1, 0, 1]).all():
        raise ValueError("Invalid frozen gate action")
    filtered = np.zeros(len(gate), dtype=int)
    reasons = ["gate_abstained"] * len(gate)
    for i in np.flatnonzero(gate):
        side_index = 0 if gate[i] == 1 else 1
        found = [j for j in range(max(0, i - 2), i + 1)
                 if segments[j] == segments[i] and setups[j, :, side_index].any()]
        if found:
            filtered[i] = gate[i]
            reasons[i] = "recent_same_side_completed_chart_retest"
        else:
            reasons[i] = "no_recent_same_side_chart_retest"
    return filtered, reasons


def frozen_gate(name: str, bars: pd.DataFrame, ready: np.ndarray) -> np.ndarray:
    gate = np.zeros(len(bars), dtype=int)
    if name == "upload_oct13_29":
        rows = read_records(PRIOR / "fresh02/forecasts_PRIVATE.jsonl.gz")
        for row in rows:
            i = row["index"]
            if i >= len(bars) or pd.Timestamp(row["available_at"]) != bars.timestamp.iloc[i] + pd.Timedelta(minutes=1):
                raise ValueError("Frozen October gate forecast misaligned")
            if bool(row["ready"]) != bool(ready[i]):
                raise ValueError("Frozen October gate readiness differs")
            value = row["prediction_usd"]
            if ready[i] and value is not None and abs(value) > 8:
                gate[i] = int(np.sign(value))
    elif name == "upload_oct30_nov02":
        rows = read_records(PRIOR / "cloud_fresh03_lineage/unchanged_8_gate_decisions_PRIVATE.jsonl.gz")
        for row in rows:
            i = row["index"]
            if i >= len(bars) or pd.Timestamp(row["available_at"]) != bars.timestamp.iloc[i] + pd.Timedelta(minutes=1):
                raise ValueError("Frozen newer gate decision misaligned")
            if bool(row["ready"]) != bool(ready[i]):
                raise ValueError("Frozen newer gate readiness differs")
            gate[i] = int(row["action"])
    else:
        raise ValueError("Unknown fixed gate window")
    if np.any(gate[~ready]):
        raise ValueError("Unready frozen gate action")
    return gate


def frozen_baseline_metrics(name: str, delay: int, cost_name: str) -> dict:
    if name == "upload_oct13_29":
        rows = json.loads((PRIOR / "fresh02/results.json").read_text())["results"]
        return next(row["metrics"] for row in rows if row["gate"] == 8 and row["delay"] == delay and row["cost"] == cost_name)
    rows = json.loads((PRIOR / "cloud_fresh03_lineage/results.json").read_text())["evaluations"]
    return next(row["metrics"] for row in rows if row["policy"] == "unchanged_8_gate" and row["delay"] == delay and row["cost"] == cost_name)


def run(out: Path = OUT) -> dict:
    out = Path(out)
    if out.exists():
        raise ValueError("Campaign07 output exists; use a new immutable directory")
    plan = json.loads(PLAN.read_text())
    out.mkdir(parents=True)
    save_json(out / "protocol.json", plan)
    save_json(out / "source_hashes.json", {p.name: sha256(p) for p in
              (PLAN, Path(__file__), CODE / "tools/human_chart_policy.py",
               CODE / "tools/cloud_campaign06.py", CODE / "tools/causal_execution.py")})
    report = {"status": "running", "windows": [], "sealed_2025_access": False, "broker_orders": 0}
    try:
        hashes: dict[str, str] = {}
        verify_manifest(PRIOR / "fresh02", hashes)
        verify_manifest(PRIOR / "cloud_fresh03_lineage", hashes)
        for spec in plan["windows"]:
            name = spec["id"]
            directory = PRIOR / ("fresh01" if name == "upload_oct13_29" else "cloud_fresh03_lineage")
            bars, audit = load_upload(directory, blocked=name == "upload_oct13_29")
            states, ready, setups, _ = state_and_setups(bars)
            start, end = pd.Timestamp(spec["start"]), pd.Timestamp(spec["end_exclusive"])
            eval_mask = ((bars.timestamp >= start) & (bars.timestamp < end)).to_numpy()
            gate = frozen_gate(name, bars, ready)
            gate[~eval_mask] = 0
            filtered, reasons = recent_confluence(gate, setups, bars.segment.to_numpy())
            write_records(out / f"{name}_decisions_PRIVATE.jsonl.gz", (
                {"index": int(i), "available_at": (bars.timestamp.iloc[i] + pd.Timedelta(minutes=1)).isoformat(),
                 "gate_action": int(gate[i]), "confluence_action": int(filtered[i]),
                 "reason": reasons[i], "live_authorized": False}
                for i in np.flatnonzero(eval_mask)))
            days = sorted(set(session_days(bars.loc[eval_mask, "timestamp"])))
            window = {"id": name, "source_audit": audit, "observed_sessions": len(days),
                      "gate_signals": int(np.count_nonzero(gate)),
                      "confluence_signals": int(np.count_nonzero(filtered)),
                      "evaluations": []}
            for candidate, signal in (("unchanged_8_gate", gate), ("chart_confluence", filtered)):
                for delay in (0, 1):
                    actions = delayed_signal(signal, ready, bars.timestamp) if delay else signal
                    for cost_name, cost in COSTS.items():
                        metrics, trades, events = replay_causal(bars, actions, states.atr14.to_numpy(float),
                                                                start, end, "time10", cost)
                        if abs(metrics["net"] - sum(trade["net"] for trade in trades)) > 1e-8:
                            raise ValueError("Confluence ledger mismatch")
                        if candidate == "unchanged_8_gate":
                            frozen = frozen_baseline_metrics(name, delay, cost_name)
                            if metrics["trades"] != frozen["trades"] or abs(metrics["net"] - frozen["net"]) > 1e-8:
                                raise ValueError("Baseline replay differs from frozen $8 gate")
                        key = f"{name}_{candidate}_delay{delay}_{cost_name}"
                        write_records(out / (key + "_trades_PRIVATE.jsonl.gz"), trades)
                        write_records(out / (key + "_events_PRIVATE.jsonl.gz"), events)
                        gap = [trade for trade in trades if trade["reason"] == "unresolved_gap_next_observed_open"]
                        row = {"candidate": candidate, "delay": delay, "cost": cost_name,
                               "metrics": metrics, "gap_exit_net_usd": float(sum(trade["net"] for trade in gap))}
                        if cost_name == "stress":
                            row["session_bootstrap"] = lower_bound(trades, days)
                        window["evaluations"].append(row)
            report["windows"].append(window)
            save_json(out / "results.json", report)
        report["status"] = "complete_development"
        save_json(out / "results.json", report)
        save_json(out / "manifest.json", {"completed": True,
                  "files_sha256": {p.name: sha256(p) for p in out.iterdir() if p.is_file() and p.name != "manifest.json"}})
        return report
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        save_json(out / "results.json", report)
        raise


if __name__ == "__main__":
    run()
