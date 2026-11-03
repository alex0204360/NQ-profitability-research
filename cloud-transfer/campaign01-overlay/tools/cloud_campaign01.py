"""Two frozen, execution-aware MNQ value fits on prior 2026 observations.

The October 13–29 upload is already opened development evidence, never confirmation.
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from tools.causal_execution import replay_causal
from tools.fresh_transfer_test import delayed_signal, lower_bound, session_days
from tools.mnq_oracle_prepare import load_candles, sha256
from tools.mnq_oracle_research import load_inputs, save_json
from tools.opportunity_research import COSTS, FEATURES, read_records, verify_manifest, write_records
from tools.physics_state import physics_features
from tools.shared_game_state import build_market_states

ROOT = Path("/workspace")
CODE = Path(__file__).resolve().parents[1]
PLAN = CODE / "docs/CLOUD_CAMPAIGN01.json"
DATA = ROOT / "mnq-private-data"
PRIOR = ROOT / "mnq-private-results"
OUT = PRIOR / "cloud_campaign01"


def targets(bars: pd.DataFrame, cutoff: pd.Timestamp) -> tuple[np.ndarray, np.ndarray]:
    """Both ten-bar outcomes must mature before cutoff in one contiguous segment."""
    out = np.zeros((len(bars), 2), dtype=float)
    valid = np.zeros(len(bars), dtype=bool)
    segment = bars.segment.to_numpy()
    price_open = bars.open.to_numpy(float)
    price_close = bars.close.to_numpy(float)
    times = bars.timestamp
    for i in range(len(bars) - 11):
        if segment[i] != segment[i + 11] or times.iloc[i + 11] + pd.Timedelta(minutes=1) >= cutoff:
            continue
        out[i] = ((price_close[i + 10] - price_open[i + 1]) * 2,
                  (price_close[i + 11] - price_open[i + 2]) * 2)
        valid[i] = True
    return out, valid


def actions(prediction: np.ndarray, ready: np.ndarray) -> np.ndarray:
    if prediction.ndim != 2 or prediction.shape[1] != 2 or len(prediction) != len(ready):
        raise ValueError("Two aligned value predictions required")
    if not np.isfinite(prediction[ready]).all():
        raise ValueError("Nonfinite ready prediction")
    return np.where(ready & (prediction.min(axis=1) > 6), 1,
                    np.where(ready & (prediction.max(axis=1) < -6), -1, 0)).astype(int)


def run(out: Path = OUT) -> dict:
    out = Path(out)
    if out.exists():
        raise ValueError("Use a new output directory; previous runs are immutable")
    out.mkdir(parents=True)
    plan = json.loads(PLAN.read_text())
    save_json(out / "protocol.json", plan)
    save_json(out / "source_hashes.json", {p.name: sha256(p) for p in
              (Path(__file__), PLAN, CODE / "tools/causal_execution.py", CODE / "tools/shared_game_state.py")})
    report = {"status": "running", "attempts": [], "failures": [], "sealed_2025_access": False}
    try:
        hashes = {}
        verify_manifest(PRIOR / "fresh02", hashes)
        # fresh01 is deliberately blocked by the overlap audit; its artifacts are
        # still hash-bound even though the generic completed-run helper rejects it.
        first = PRIOR / "fresh01"
        first_manifest = json.loads((first / "manifest.json").read_text())
        if first_manifest.get("status") != "blocked_data_integrity":
            raise ValueError("Unexpected fresh01 status")
        for name, expected in first_manifest["files_sha256"].items():
            if sha256(first / name) != expected:
                raise ValueError("Frozen fresh01 artifact changed: " + name)
        bars, old_features, _, old_audit = load_inputs(DATA)
        states = build_market_states(bars)
        ready = (states.ready & old_features.feature_ready & physics_features(bars, states).physics_ready).to_numpy(bool)
        matrix = states.copy()
        matrix["log1p_atr14_ticks"] = np.log1p(matrix.atr14 / .25)
        cutoff = pd.Timestamp(plan["training_cutoff_exclusive"])
        matured = cutoff - pd.Timedelta(minutes=plan["purge_minutes"])
        y, valid = targets(bars, matured)
        train = ready & valid & (bars.timestamp < matured).to_numpy()
        x = matrix.loc[train, FEATURES].to_numpy(float)
        if len(x) < 1000 or not np.isfinite(x).all():
            raise ValueError("Insufficient finite causal training inputs")
        save_json(out / "training_summary.json", {"rows": int(train.sum()),
                  "first_timestamp": bars.timestamp[train].iloc[0].isoformat(),
                  "last_timestamp": bars.timestamp[train].iloc[-1].isoformat(),
                  "target_max_maturity": matured.isoformat(),
                  "source_audit": old_audit, "features": FEATURES})
        upload = PRIOR / "fresh01/normalized_PRIVATE.csv"
        if sha256(upload) != json.loads((PRIOR / "fresh01/manifest.json").read_text())["files_sha256"][upload.name]:
            raise ValueError("Upload hash mismatch")
        test_bars, _ = load_candles([upload])
        start, end = (pd.Timestamp(t) for t in ("2026-10-13T00:00:00Z", "2026-10-30T00:00:00Z"))
        test_bars = test_bars[test_bars.timestamp < end].reset_index(drop=True)
        forecasts = read_records(PRIOR / "fresh02/forecasts_PRIVATE.jsonl.gz")
        eval_mask = (test_bars.timestamp >= start).to_numpy()
        expected_indices = np.flatnonzero(eval_mask)
        if len(forecasts) != len(expected_indices):
            raise ValueError("Frozen forecast count differs from upload")
        test_x = np.zeros((len(test_bars), len(FEATURES)))
        test_ready = np.zeros(len(test_bars), dtype=bool)
        test_atr = np.full(len(test_bars), np.nan)
        for row, i in zip(forecasts, expected_indices):
            if row["index"] != int(i) or pd.Timestamp(row["available_at"]) != test_bars.timestamp.iloc[i] + pd.Timedelta(minutes=1):
                raise ValueError("Forecast and upload alignment mismatch")
            test_ready[i] = row["ready"]
            if test_ready[i]:
                test_x[i] = [row["inputs"][f] for f in FEATURES]
                test_atr[i] = np.expm1(row["inputs"]["log1p_atr14_ticks"]) * .25
        if not np.isfinite(test_x[test_ready]).all():
            raise ValueError("Nonfinite evaluation input")
        days = sorted(set(session_days(test_bars.loc[eval_mask, "timestamp"])))
        models = {
            "ridge_dual_delay": make_pipeline(StandardScaler(), Ridge(alpha=100.0)),
            "extra_trees_dual_delay": ExtraTreesRegressor(n_estimators=80, max_depth=5,
                min_samples_leaf=80, random_state=20261102, n_jobs=1),
        }
        for name, model in models.items():
            try:
                with threadpool_limits(limits=1):
                    model.fit(x, y[train])
                    pred = np.zeros((len(test_bars), 2))
                    pred[test_ready] = model.predict(test_x[test_ready])
                joblib.dump({"id": name, "model": model, "features": FEATURES, "plan_sha256": sha256(PLAN),
                             "training_cutoff": cutoff.isoformat()}, out / (name + ".joblib"))
                signal = actions(pred, test_ready)
                write_records(out / (name + "_decisions_PRIVATE.jsonl.gz"), (
                    {"index": int(i), "available_at": forecasts[j]["available_at"],
                     "ready": bool(test_ready[i]), "predicted_gross_usd_immediate": float(pred[i, 0]),
                     "predicted_gross_usd_delayed": float(pred[i, 1]), "action": int(signal[i]),
                     "reason": "both_fill_values_exceed_stress_cost" if signal[i] else "abstain_dual_delay_value",
                     "live_authorized": False} for j, i in enumerate(expected_indices)))
                attempt = {"candidate": name, "training_rows": int(train.sum()), "evaluations": []}
                for delay in (0, 1):
                    delayed = delayed_signal(signal, test_ready, test_bars.timestamp) if delay else signal
                    for cost_name, cost in COSTS.items():
                        metrics, trades, events = replay_causal(test_bars, delayed, test_atr, start, end, "time10", cost)
                        if abs(metrics["net"] - sum(t["net"] for t in trades)) > 1e-8:
                            raise ValueError("Ledger accounting mismatch")
                        key = f"{name}_delay{delay}_{cost_name}"
                        write_records(out / (key + "_trades_PRIVATE.jsonl.gz"), trades)
                        write_records(out / (key + "_events_PRIVATE.jsonl.gz"), events)
                        row = {"delay": delay, "cost": cost_name, "metrics": metrics}
                        if cost_name == "stress":
                            row["session_bootstrap"] = lower_bound(trades, days)
                        attempt["evaluations"].append(row)
                report["attempts"].append(attempt)
                save_json(out / "results.json", report)
            except Exception as exc:  # noqa: BLE001 - preserve other registered attempt
                report["failures"].append({"candidate": name, "type": type(exc).__name__, "error": str(exc)})
                save_json(out / "results.json", report)
        report["status"] = "complete_development" if not report["failures"] else "partial_failure"
        save_json(out / "results.json", report)
        save_json(out / "manifest.json", {"completed": report["status"] == "complete_development",
                  "files_sha256": {p.name: sha256(p) for p in out.iterdir() if p.is_file() and p.name != "manifest.json"}})
        return report
    except Exception as exc:
        report["status"] = "failed"
        report["failures"].append({"type": type(exc).__name__, "error": str(exc)})
        save_json(out / "results.json", report)
        raise


if __name__ == "__main__":
    run(PRIOR / "cloud_campaign01_retry1")
