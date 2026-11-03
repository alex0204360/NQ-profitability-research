"""One bounded teacher/student fit for execution-aware direction and exits."""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor
from threadpoolctl import threadpool_limits

from tools.causal_execution_v3 import replay_causal
from tools.fresh_transfer_test import delayed_signal, lower_bound, session_days
from tools.mnq_oracle_prepare import causal_features, load_candles, sha256
from tools.mnq_oracle_research import load_inputs, save_json
from tools.opportunity_research import FEATURES, verify_manifest, write_records
from tools.physics_state import physics_features
from tools.shared_game_state import build_market_states

ROOT = Path("/workspace")
CODE = Path(__file__).resolve().parents[1]
PRIOR = ROOT / "mnq-private-results"
PLAN = CODE / "docs/CLOUD_CAMPAIGN02.json"
OUT = PRIOR / "cloud_campaign02"
HORIZONS = (3, 5, 10, 20)


def values(bars, cutoff):
    """Gross long P&L for each horizon and delay; no future value enters inputs."""
    output = np.zeros((len(bars), 8), dtype=float)
    eligible = np.zeros(len(bars), dtype=bool)
    segments = bars.segment.to_numpy()
    opens, closes = bars.open.to_numpy(float), bars.close.to_numpy(float)
    for i in range(len(bars) - 22):
        if segments[i] != segments[i + 21] or bars.timestamp.iloc[i + 21] + pd.Timedelta(minutes=1) >= cutoff:
            continue
        eligible[i] = True
        for j, horizon in enumerate(HORIZONS):
            output[i, j * 2] = (closes[i + horizon] - opens[i + 1]) * 2
            output[i, j * 2 + 1] = (closes[i + horizon + 1] - opens[i + 2]) * 2
    return output, eligible


def choose(predictions, ready):
    if predictions.shape != (len(ready), 8) or not np.isfinite(predictions[ready]).all():
        raise ValueError("Eight finite action values required")
    signal = np.zeros(len(ready), dtype=int)
    horizon = np.full(len(ready), 10, dtype=int)
    estimate = np.zeros(len(ready), dtype=float)
    for i in np.flatnonzero(ready):
        best = (0., 0, 10)  # minimum net, side, horizon
        for j, held in enumerate(HORIZONS):
            immediate, delayed = predictions[i, j * 2:j * 2 + 2]
            for side in (1, -1):
                minimum_net = min(side * immediate, side * delayed) - 6
                if minimum_net > best[0]:
                    best = (float(minimum_net), side, held)
        estimate[i], signal[i], horizon[i] = best
    return signal, horizon, estimate


def state_inputs(bars):
    states = build_market_states(bars)
    ready = (states.ready & causal_features(bars).feature_ready &
             physics_features(bars, states).physics_ready).to_numpy(bool)
    x = states.copy()
    x["log1p_atr14_ticks"] = np.log1p(x.atr14 / .25)
    if not np.isfinite(x.loc[ready, FEATURES].to_numpy(float)).all():
        raise ValueError("Nonfinite causal inputs")
    return x, ready, states.atr14.to_numpy(float)


def run(out=OUT):
    out = Path(out)
    if out.exists():
        raise ValueError("Output must be new; preserve all historical attempts")
    plan = json.loads(PLAN.read_text())
    out.mkdir(parents=True)
    save_json(out / "protocol.json", plan)
    save_json(out / "source_hashes.json", {p.name: sha256(p) for p in
              (Path(__file__), PLAN, CODE / "tools/causal_execution_v3.py",
               CODE / "tools/shared_game_state.py")})
    result = {"status": "running", "fit_count": 0, "evaluations": [], "selection": None,
              "sealed_2025_access": False, "orders_submitted": 0}
    try:
        hashes = {}
        verify_manifest(PRIOR / "fresh02", hashes)
        verify_manifest(PRIOR / "cloud_fresh03_lineage", hashes)
        old_bars, _, _, audit = load_inputs(ROOT / "mnq-private-data")
        x, ready, atr = state_inputs(old_bars)
        cutoff = pd.Timestamp(plan["training_end_exclusive"])
        mature = cutoff - pd.Timedelta(minutes=plan["purge_minutes"])
        y, valid = values(old_bars, mature)
        train = ready & valid & (old_bars.timestamp < mature).to_numpy()
        if train.sum() < 1000:
            raise ValueError("Insufficient matured training outcomes")
        model = ExtraTreesRegressor(**plan["model"])
        with threadpool_limits(limits=1):
            model.fit(x.loc[train, FEATURES].to_numpy(float), y[train])
        joblib.dump({"id": plan["candidate"], "model": model, "features": FEATURES,
                     "horizons": HORIZONS, "plan_sha256": sha256(PLAN),
                     "training_end": cutoff.isoformat()}, out / "student.joblib")
        result["fit_count"] = 1
        save_json(out / "training_summary.json", {"rows": int(train.sum()),
                  "last_signal_time": old_bars.timestamp[train].iloc[-1].isoformat(),
                  "maturity_before": mature.isoformat(), "audit": audit})
        windows = [
            ("original_oct08_12", old_bars, x, ready, atr,
             pd.Timestamp("2026-10-08T00:00:00Z"), pd.Timestamp("2026-10-12T14:20:00Z")),
        ]
        for name, path, start, end in (
            ("fresh02_oct13_29", PRIOR / "fresh01/normalized_PRIVATE.csv",
             "2026-10-13T00:00:00Z", "2026-10-30T00:00:00Z"),
            ("fresh03_oct30_nov02", PRIOR / "cloud_fresh03_lineage/normalized_PRIVATE.csv",
             "2026-10-30T00:00:00Z", "2026-11-02T20:54:00Z"),
        ):
            bars, _ = load_candles([path])
            bars = bars[bars.timestamp < pd.Timestamp(end)].reset_index(drop=True)
            matrix, usable, atr_values = state_inputs(bars)
            windows.append((name, bars, matrix, usable, atr_values,
                            pd.Timestamp(start), pd.Timestamp(end)))
        for name, bars, matrix, usable, atr_values, start, end in windows:
            eval_mask = (bars.timestamp >= start).to_numpy()
            predictions = np.zeros((len(bars), 8))
            with threadpool_limits(limits=1):
                predictions[usable] = model.predict(matrix.loc[usable, FEATURES].to_numpy(float))
            signal, horizon, estimate = choose(predictions, usable)
            signal[~eval_mask] = 0
            days = sorted(set(session_days(bars.loc[eval_mask, "timestamp"])))
            write_records(out / (name + "_decisions_PRIVATE.jsonl.gz"), (
                {"index": int(i), "available_at": (bars.timestamp.iloc[i] + pd.Timedelta(minutes=1)).isoformat(),
                 "ready": bool(usable[i]), "action": int(signal[i]), "horizon": int(horizon[i]),
                 "minimum_predicted_stress_net_usd": float(estimate[i]), "live_authorized": False}
                for i in np.flatnonzero(eval_mask)))
            for delay in (0, 1):
                action = delayed_signal(signal, usable, bars.timestamp) if delay else signal
                held = np.r_[10, horizon[:-1]] if delay else horizon
                for cost_name, costs in plan["costs"].items():
                    metrics, trades, events = replay_causal(bars, action, atr_values, start, end,
                                                            "time10", costs, holding_bars=held)
                    if abs(metrics["net"] - sum(t["net"] for t in trades)) > 1e-8:
                        raise ValueError("Trade ledger mismatch")
                    key = f"{name}_delay{delay}_{cost_name}"
                    write_records(out / (key + "_trades_PRIVATE.jsonl.gz"), trades)
                    write_records(out / (key + "_events_PRIVATE.jsonl.gz"), events)
                    cell = {"window": name, "delay": delay, "cost": cost_name, "metrics": metrics}
                    if cost_name == "stress":
                        cell["session_bootstrap"] = lower_bound(trades, days)
                    result["evaluations"].append(cell)
                    save_json(out / "results.json", result)
        if len(result["evaluations"]) != 18:
            raise ValueError("Incomplete three-window evaluation matrix")
        result["status"] = "complete_development_no_selection"
        save_json(out / "results.json", result)
        save_json(out / "manifest.json", {"completed": True, "files_sha256":
                  {p.name: sha256(p) for p in out.iterdir() if p.is_file() and p.name != "manifest.json"}})
        return result
    except Exception as exc:
        result.update(status="failed", error={"type": type(exc).__name__, "detail": str(exc)})
        save_json(out / "results.json", result)
        raise


if __name__ == "__main__":
    run()
