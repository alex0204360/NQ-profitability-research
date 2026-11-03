"""Fixed MNQ signal-persistence and drift/diffusion development campaign."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from tools.causal_execution import replay_causal
from tools.cloud_campaign01 import targets
from tools.cloud_campaign06 import load_upload, state_and_setups
from tools.cloud_campaign07 import frozen_baseline_metrics, frozen_gate
from tools.fresh_transfer_test import delayed_signal, lower_bound, session_days
from tools.mnq_oracle_prepare import sha256
from tools.mnq_oracle_research import save_json
from tools.opportunity_research import COSTS, verify_manifest, write_records
from tools.physics_signal import diffusion_probability, filtered_signals

ROOT = Path("/workspace")
CODE = Path(__file__).resolve().parents[1]
PLAN = CODE / "docs/CLOUD_CAMPAIGN08.json"
PRIOR = ROOT / "mnq-private-results"
OUT = PRIOR / "cloud_campaign08"


def calibration_diagnostic(bars: pd.DataFrame, gate: np.ndarray, probability: np.ndarray,
                           start: pd.Timestamp, end: pd.Timestamp) -> dict:
    gross, valid = targets(bars, end)
    mask = ((bars.timestamp >= start) & (bars.timestamp < end)).to_numpy()
    mask &= (gate != 0) & valid & np.isfinite(probability)
    if not mask.any():
        return {"count": 0, "brier": None, "base_rate_brier": None, "observed_positive_rate": None,
                "mean_predicted_probability": None, "bins": []}
    actual = (gate[mask] * gross[mask, 0] - 6 > 0).astype(float)
    predicted = probability[mask]
    bins = []
    for j in range(5):
        subset = (predicted >= j / 5) & (predicted < (j + 1) / 5 if j < 4 else predicted <= 1)
        bins.append({"lower": j / 5, "upper": (j + 1) / 5, "count": int(subset.sum()),
                     "mean_predicted": float(predicted[subset].mean()) if subset.any() else None,
                     "observed_positive_rate": float(actual[subset].mean()) if subset.any() else None})
    prevalence = float(actual.mean())
    return {"count": int(mask.sum()), "brier": float(np.square(predicted - actual).mean()),
            "base_rate_brier": float(np.square(prevalence - actual).mean()),
            "observed_positive_rate": prevalence,
            "mean_predicted_probability": float(predicted.mean()), "bins": bins}


def run(out: Path = OUT) -> dict:
    out = Path(out)
    if out.exists():
        raise ValueError("Campaign08 output exists; use a new immutable directory")
    plan = json.loads(PLAN.read_text())
    out.mkdir(parents=True)
    save_json(out / "protocol.json", plan)
    save_json(out / "source_hashes.json", {p.name: sha256(p) for p in
              (PLAN, Path(__file__), CODE / "tools/physics_signal.py",
               CODE / "tools/cloud_campaign07.py", CODE / "tools/causal_execution.py")})
    report = {"status": "running", "windows": [], "sealed_2025_access": False, "broker_orders": 0}
    try:
        hashes: dict[str, str] = {}
        verify_manifest(PRIOR / "fresh02", hashes)
        verify_manifest(PRIOR / "cloud_fresh03_lineage", hashes)
        for spec in plan["evaluation_windows"]:
            name = spec["id"]
            directory = PRIOR / ("fresh01" if name == "upload_oct13_29" else "cloud_fresh03_lineage")
            bars, audit = load_upload(directory, blocked=name == "upload_oct13_29")
            states, ready, _setups, _levels = state_and_setups(bars)
            start, end = pd.Timestamp(spec["start"]), pd.Timestamp(spec["end_exclusive"])
            eval_mask = ((bars.timestamp >= start) & (bars.timestamp < end)).to_numpy()
            gate = frozen_gate(name, bars, ready)
            gate[~eval_mask] = 0
            probability, drift, sigma = diffusion_probability(bars, gate)
            candidates = filtered_signals(gate, probability, bars.segment.to_numpy())
            diagnostic = calibration_diagnostic(bars, gate, probability, start, end)
            write_records(out / f"{name}_decisions_PRIVATE.jsonl.gz", (
                {"index": int(i), "available_at": (bars.timestamp.iloc[i] + pd.Timedelta(minutes=1)).isoformat(),
                 "gate_action": int(gate[i]), "diffusion_probability": float(probability[i]) if np.isfinite(probability[i]) else None,
                 "past_drift_points_per_min": float(drift[i]) if np.isfinite(drift[i]) else None,
                 "past_sigma_points_per_min": float(sigma[i]) if np.isfinite(sigma[i]) else None,
                 "candidate_actions": {key: int(signal[i]) for key, signal in candidates.items()},
                 "live_authorized": False} for i in np.flatnonzero(eval_mask)))
            days = sorted(set(session_days(bars.loc[eval_mask, "timestamp"])))
            window = {"id": name, "source_audit": audit, "observed_sessions": len(days),
                      "gate_signals": int(np.count_nonzero(gate)),
                      "signal_counts": {key: int(np.count_nonzero(value)) for key, value in candidates.items()},
                      "probability_diagnostic": diagnostic, "evaluations": []}
            for candidate, signal in candidates.items():
                for delay in (0, 1):
                    action = delayed_signal(signal, ready, bars.timestamp) if delay else signal
                    for cost_name, cost in COSTS.items():
                        metrics, trades, events = replay_causal(bars, action, states.atr14.to_numpy(float),
                                                                start, end, "time10", cost)
                        if abs(metrics["net"] - sum(trade["net"] for trade in trades)) > 1e-8:
                            raise ValueError("Physics-filter ledger mismatch")
                        if candidate == "unchanged_8_gate":
                            frozen = frozen_baseline_metrics(name, delay, cost_name)
                            if metrics["trades"] != frozen["trades"] or abs(metrics["net"] - frozen["net"]) > 1e-8:
                                raise ValueError("Baseline differs from frozen $8 gate")
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
