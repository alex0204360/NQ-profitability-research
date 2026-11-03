"""Fixed chart-reading MNQ campaign: causal levels, trendlines, and probability gate."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from tools.causal_execution import replay_causal
from tools.cloud_robust_teacher import robust_teacher
from tools.fresh_transfer_test import delayed_signal, lower_bound, session_days
from tools.human_chart_policy import calibrate, chart_setups, signals
from tools.mnq_oracle_prepare import causal_features, load_candles, sha256
from tools.mnq_oracle_research import PART_HASHES, save_json
from tools.opportunity_research import COSTS, write_records
from tools.physics_state import physics_features
from tools.shared_game_state import build_market_states

ROOT = Path("/workspace")
CODE = Path(__file__).resolve().parents[1]
PLAN = CODE / "docs/CLOUD_CAMPAIGN06.json"
PRIOR = ROOT / "mnq-private-results"
DATA = ROOT / "mnq-private-data"
OUT = PRIOR / "cloud_campaign06"


def load_original() -> tuple[pd.DataFrame, dict]:
    parts = [DATA / f"MNQ_Yahoo_1m_20260913_20261012_part{i:02d}.csv" for i in range(1, 7)]
    if any(sha256(part) != expected for part, expected in zip(parts, PART_HASHES)):
        raise ValueError("Original source hash mismatch")
    return load_candles(parts)


def state_and_setups(bars: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray, np.ndarray, dict]:
    states = build_market_states(bars)
    ready = (states.ready & causal_features(bars).feature_ready &
             physics_features(bars, states).physics_ready).to_numpy(bool)
    setup, levels = chart_setups(bars, states, ready)
    return states, ready, setup, levels


def load_upload(directory: Path, *, blocked: bool = False) -> tuple[pd.DataFrame, dict]:
    directory = directory.resolve()
    manifest = json.loads((directory / "manifest.json").read_text())
    if blocked:
        if manifest.get("status") != "blocked_data_integrity":
            raise ValueError("Expected overlap-conflicted upload status")
    elif manifest.get("completed") is not True:
        raise ValueError("Incomplete frozen upload")
    file = directory / "normalized_PRIVATE.csv"
    if sha256(file) != manifest["files_sha256"][file.name]:
        raise ValueError("Upload-only source hash mismatch")
    return load_candles([file])


def run(out: Path = OUT) -> dict:
    out = Path(out)
    if out.exists():
        raise ValueError("Campaign06 run exists; use a new immutable output directory")
    plan = json.loads(PLAN.read_text())
    out.mkdir(parents=True)
    save_json(out / "protocol.json", plan)
    save_json(out / "source_hashes.json", {p.name: sha256(p) for p in
              (PLAN, Path(__file__), CODE / "tools/human_chart_policy.py",
               CODE / "tools/causal_execution.py", CODE / "tools/shared_game_state.py")})
    report = {"status": "running", "calibration": None, "evaluations": [],
              "sealed_2025_access": False, "broker_orders": 0}
    try:
        original, original_audit = load_original()
        states, ready, setup, _ = state_and_setups(original)
        maturity = pd.Timestamp(plan["training"]["maturity_cutoff_exclusive"])
        net, valid, _ = robust_teacher(original, maturity)
        robust = np.min(net, axis=2)
        training = (original.timestamp < maturity).to_numpy() & ready
        calibration = calibrate(setup, robust, valid, training)
        report["calibration"] = calibration
        save_json(out / "calibration.json", calibration)
        save_json(out / "training_summary.json", {"source_audit": original_audit,
                  "mature_ready_rows": int((training & valid).sum()),
                  "setup_training_counts": {key: value["examples"] for key, value in calibration.items()}})
        windows = [
            ("original_oct01_12", original, original_audit, states, ready, setup),
        ]
        for name, directory, blocked in (
            ("upload_oct13_29", PRIOR / "fresh01", True),
            ("upload_oct30_nov02", PRIOR / "cloud_fresh03_lineage", False),
        ):
            bars, audit = load_upload(directory, blocked=blocked)
            new_states, new_ready, new_setup, _ = state_and_setups(bars)
            windows.append((name, bars, audit, new_states, new_ready, new_setup))
        expected = {row["id"]: row for row in plan["evaluation_windows"]}
        for window, bars, audit, state, usable, setups in windows:
            spec = expected[window]
            start, end = pd.Timestamp(spec["start"]), pd.Timestamp(spec["end_exclusive"])
            eval_mask = ((bars.timestamp >= start) & (bars.timestamp < end)).to_numpy()
            if not eval_mask.any():
                raise ValueError("Empty fixed evaluation window: " + window)
            raw, raw_reasons = signals(setups, calibration, gated=False)
            gated, reasons = signals(setups, calibration, gated=True)
            raw[~eval_mask] = 0
            gated[~eval_mask] = 0
            atr = state.atr14.to_numpy(float)
            days = sorted(set(session_days(bars.loc[eval_mask, "timestamp"])))
            result = {"window": window, "source_audit": audit,
                      "observed_sessions": len(days), "ready_bars": int((usable & eval_mask).sum()),
                      "raw_setup_counts": {"horizontal_long": int(setups[eval_mask, 0, 0].sum()),
                                           "horizontal_short": int(setups[eval_mask, 0, 1].sum()),
                                           "trendline_long": int(setups[eval_mask, 1, 0].sum()),
                                           "trendline_short": int(setups[eval_mask, 1, 1].sum())},
                      "signals": {"raw": int(np.count_nonzero(raw)), "gated": int(np.count_nonzero(gated))},
                      "evaluations": []}
            write_records(out / f"{window}_decisions_PRIVATE.jsonl.gz", (
                {"index": int(i), "available_at": (bars.timestamp.iloc[i] + pd.Timedelta(minutes=1)).isoformat(),
                 "raw_action": int(raw[i]), "raw_reason": raw_reasons[i],
                 "gated_action": int(gated[i]), "gated_reason": reasons[i],
                 "ready": bool(usable[i]), "live_authorized": False}
                for i in np.flatnonzero(eval_mask)))
            for candidate, base_signal, rule in (
                ("raw_fixed10", raw, "time10"),
                ("gated_fixed10", gated, "time10"),
                ("gated_atr_bracket", gated, "atr1_target1.5_time30"),
            ):
                for delay in (0, 1):
                    action = delayed_signal(base_signal, usable, bars.timestamp) if delay else base_signal
                    for cost_name, cost in COSTS.items():
                        metrics, trades, events = replay_causal(bars, action, atr, start, end, rule, cost)
                        if abs(metrics["net"] - sum(trade["net"] for trade in trades)) > 1e-8:
                            raise ValueError("Trade ledger accounting mismatch")
                        key = f"{window}_{candidate}_delay{delay}_{cost_name}"
                        write_records(out / (key + "_trades_PRIVATE.jsonl.gz"), trades)
                        write_records(out / (key + "_events_PRIVATE.jsonl.gz"), events)
                        gap = [trade for trade in trades if trade["reason"] == "unresolved_gap_next_observed_open"]
                        row = {"candidate": candidate, "delay": delay, "cost": cost_name,
                               "metrics": metrics, "gap_exit_net_usd": float(sum(trade["net"] for trade in gap))}
                        if cost_name == "stress":
                            row["session_bootstrap"] = lower_bound(trades, days)
                        result["evaluations"].append(row)
            report["evaluations"].append(result)
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
