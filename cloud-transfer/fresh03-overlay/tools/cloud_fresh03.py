"""Upload-only, no-selection diagnostic on the November 2 MNQ CSV transfer."""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from tools.causal_execution import replay_causal
from tools.cloud_campaign01 import actions as student_actions
from tools.fresh_transfer_test import delayed_signal, lower_bound, session_days
from tools.mnq_oracle_prepare import causal_features, load_candles, sha256
from tools.mnq_oracle_research import save_json
from tools.opportunity_research import FEATURES, verify_manifest, write_records
from tools.physics_state import physics_features
from tools.shared_game_state import build_market_states

ROOT = Path("/workspace")
CODE = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "attachments/0e9f0a4e-9b75-4bfc-9df0-838ca2510148/MNQ_Yahoo_1m_2026-10-28_to_2026-11-02_161500_327580.csv"
PRIOR = ROOT / "mnq-private-results"
PLAN = CODE / "docs/CLOUD_FRESH03_PLAN.json"
OUT = PRIOR / "cloud_fresh03"


def run(source=SOURCE, out=OUT):
    source, out = Path(source), Path(out)
    if out.exists():
        raise ValueError("Use a new output directory; completed/failed runs are immutable")
    plan = json.loads(PLAN.read_text())
    if sha256(source) != plan["source_sha256"]:
        raise ValueError("Uploaded source SHA-256 differs from registered input")
    out.mkdir(parents=True)
    save_json(out / "protocol.json", plan)
    save_json(out / "source_hashes.json", {p.name: sha256(p) for p in
              (Path(__file__), PLAN, CODE / "tools/causal_execution.py",
               CODE / "tools/shared_game_state.py", CODE / "tools/cloud_campaign01.py")})
    result = {"status": "running", "evaluations": [], "failures": [], "selection": None,
              "sealed_2025_access": False, "orders_submitted": 0}
    try:
        hashes = {}
        verify_manifest(PRIOR / "fresh02", hashes)
        verify_manifest(PRIOR / "cloud_campaign01_retry2", hashes)
        raw = pd.read_csv(source)
        mapping = {"Datetime": "timestamp_utc", "Open": "open", "High": "high",
                   "Low": "low", "Close": "close", "Volume": "volume"}
        if list(raw.columns) != list(mapping):
            raise ValueError("Unexpected upload schema")
        if not raw.Datetime.astype(str).str.contains(r"(?:Z|[+-]\d{2}:?\d{2})$").all():
            raise ValueError("Explicit timestamp offsets required")
        raw = raw.rename(columns=mapping)
        raw["timestamp_utc"] = pd.to_datetime(raw.timestamp_utc, utc=True)
        if not raw.timestamp_utc.is_monotonic_increasing or raw.timestamp_utc.duplicated().any():
            raise ValueError("Unordered or duplicate source bars")
        if not raw.timestamp_utc.dt.year.eq(2026).all():
            raise ValueError("Only 2026 source bars allowed")
        normalized = out / "normalized_PRIVATE.csv"
        raw.to_csv(normalized, index=False)
        bars, audit = load_candles([normalized])
        if audit["nonminute_rows_rejected_as_partial"] or audit["duplicate_rows_identical_removed"]:
            raise ValueError("Partial or duplicate source bars")
        end = pd.Timestamp(plan["evaluation_end_exclusive"])
        start = pd.Timestamp(plan["evaluation_start"])
        bars = bars[bars.timestamp < end].reset_index(drop=True)
        states = build_market_states(bars)
        ready = (states.ready & causal_features(bars).feature_ready &
                 physics_features(bars, states).physics_ready).to_numpy(bool)
        matrix = states.copy()
        matrix["log1p_atr14_ticks"] = np.log1p(matrix.atr14 / .25)
        if not np.isfinite(matrix.loc[ready, FEATURES].to_numpy(float)).all():
            raise ValueError("Nonfinite ready feature")
        eval_mask = (bars.timestamp >= start).to_numpy()
        days = sorted(set(session_days(bars.loc[eval_mask, "timestamp"])))
        reference = json.loads((PRIOR / "fresh02/protocol.json").read_text())
        baseline_model = PRIOR / "opportunity02/fold3__hist_gradient_boosting.joblib"
        if sha256(baseline_model) != reference["model_sha256"]:
            raise ValueError("Baseline checkpoint changed")
        checkpoint = joblib.load(baseline_model)
        if checkpoint["features"] != FEATURES:
            raise ValueError("Baseline feature schema changed")
        raw_prediction = np.zeros(len(bars))
        raw_prediction[ready] = checkpoint["model"].predict(matrix.loc[ready, FEATURES].to_numpy(float))
        baseline_usd = raw_prediction * reference["coefficient"] * states.atr14.fillna(0).to_numpy(float) * 2
        signals = {"unchanged_8_gate": np.where(ready & (abs(baseline_usd) > 8),
                                                   np.sign(baseline_usd), 0).astype(int)}
        for student in ("ridge_dual_delay", "extra_trees_dual_delay"):
            bundle_path = PRIOR / "cloud_campaign01_retry2" / (student + ".joblib")
            frozen = json.loads((PRIOR / "cloud_campaign01_retry2/manifest.json").read_text())
            if sha256(bundle_path) != frozen["files_sha256"][bundle_path.name]:
                raise ValueError("Student checkpoint changed")
            bundle = joblib.load(bundle_path)
            if bundle["id"] != student or bundle["features"] != FEATURES:
                raise ValueError("Student identity changed")
            predictions = np.zeros((len(bars), 2))
            predictions[ready] = bundle["model"].predict(matrix.loc[ready, FEATURES].to_numpy(float))
            signals[student] = student_actions(predictions, ready)
        atr = states.atr14.to_numpy(float)
        for policy, signal in signals.items():
            write_records(out / (policy + "_decisions_PRIVATE.jsonl.gz"), (
                {"index": int(i), "available_at": (bars.timestamp.iloc[i] + pd.Timedelta(minutes=1)).isoformat(),
                 "ready": bool(ready[i]), "action": int(signal[i]), "live_authorized": False}
                for i in np.flatnonzero(eval_mask)))
            for delay in plan["delays_bars"]:
                delayed = delayed_signal(signal, ready, bars.timestamp) if delay else signal
                for cost_name, cost in plan["costs"].items():
                    metrics, trades, events = replay_causal(bars, delayed, atr, start, end, "time10", cost)
                    if abs(metrics["net"] - sum(t["net"] for t in trades)) > 1e-8:
                        raise ValueError("Trade accounting mismatch")
                    key = f"{policy}_delay{delay}_{cost_name}"
                    write_records(out / (key + "_trades_PRIVATE.jsonl.gz"), trades)
                    write_records(out / (key + "_events_PRIVATE.jsonl.gz"), events)
                    cell = {"policy": policy, "delay": delay, "cost": cost_name, "metrics": metrics}
                    if cost_name == "stress":
                        cell["session_bootstrap"] = lower_bound(trades, days)
                    result["evaluations"].append(cell)
                    save_json(out / "results.json", result)
        if len(result["evaluations"]) != plan["evaluations"]:
            raise ValueError("Incomplete registered evaluation matrix")
        if sha256(source) != plan["source_sha256"]:
            raise ValueError("Source changed during evaluation")
        result.update(status="complete_diagnostic_not_confirmation", input_audit=audit,
                      observed_sessions=len(days), evaluation_bars=int(eval_mask.sum()),
                      eligible_bars=int((eval_mask & ready).sum()))
        save_json(out / "results.json", result)
        save_json(out / "manifest.json", {"completed": True,
                  "files_sha256": {p.name: sha256(p) for p in out.iterdir() if p.is_file() and p.name != "manifest.json"}})
        return result
    except Exception as exc:
        result.update(status="failed", failures=[{"type": type(exc).__name__, "error": str(exc)}])
        save_json(out / "results.json", result)
        raise


if __name__ == "__main__":
    run()
