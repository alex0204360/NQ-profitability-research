"""One fixed internal replay of the single campaign05 selection winner.

This is already opened 2026 development data, not prospective confirmation.
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from tools.causal_execution_v3 import replay_causal
from tools.cloud_campaign05 import (
    ACTIONS,
    OUT,
    PLAN,
    POOL,
    PROPOSALS,
    make_model,
    oracle_values,
    score_actions,
)
from tools.cloud_campaign05_report import aggregate
from tools.fresh_transfer_test import delayed_signal, lower_bound, session_days
from tools.mnq_oracle_prepare import FEATURE_NAMES, causal_features, load_candles, sha256
from tools.mnq_oracle_research import PART_HASHES, save_json
from tools.opportunity_research import COSTS, FEATURES, write_records
from tools.physics_state import physics_features
from tools.shared_game_state import build_market_states

ROOT = Path("/workspace")
START = pd.Timestamp("2026-10-01T00:00:00Z")
END = pd.Timestamp("2026-10-07T00:00:00Z")


def decide(prediction: np.ndarray, ready: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if prediction.shape != (len(ready), 8) or not np.isfinite(prediction[ready]).all():
        raise ValueError("Eight finite aligned forecasts required")
    best = np.argmax(prediction, axis=1)
    chosen = ready & (prediction[np.arange(len(prediction)), best] > 0)
    direction = np.where(chosen, np.asarray([ACTIONS[i][0] for i in best]), 0)
    horizon = np.asarray([ACTIONS[i][1] for i in best])
    horizon[~chosen] = 10
    return direction.astype(int), horizon.astype(int), best


def linear_trace(model, names: list[str], values: np.ndarray, predicted: np.ndarray, action: int,
                 available_at: str, realized: np.ndarray | None = None) -> dict:
    """Exact additive Ridge decomposition around each training feature mean."""
    scaler, ridge = model.steps[0][1], model.steps[1][1]
    if len(names) != len(values) or ridge.coef_.shape != (8, len(names)):
        raise ValueError("Expected fitted eight-output Ridge model")
    centered = (values - scaler.mean_) / scaler.scale_
    contribution = centered * ridge.coef_[action]
    baseline = float(ridge.intercept_[action])
    if not np.isclose(baseline + contribution.sum(), predicted[action], atol=1e-7):
        raise ValueError("Trace does not reconstruct forecast")
    order = np.argsort(-np.abs(contribution), kind="stable")
    side, horizon = ACTIONS[action]
    return {"available_at": available_at, "action": "long" if side == 1 else "short",
            "horizon_bars": horizon, "predicted_stress_net_usd": [float(x) for x in predicted],
            "chosen_action_predicted_net_usd": float(predicted[action]),
            "chosen_action_baseline_usd": baseline,
            "feature_contributions_usd": [{"feature": names[i], "completed_bar_value": float(values[i]),
                                           "contribution_to_chosen_forecast_usd": float(contribution[i])}
                                          for i in order],
            "realized_oracle_stress_net_usd_after_maturity":
                [float(x) for x in realized] if realized is not None else None,
            "explanation": "Exact Ridge forecast decomposition around training means; contributions describe model arithmetic, not hidden thoughts or proof of causality.",
            "research_only": True, "live_authorized": False}


def run() -> dict:
    target = OUT / "internal_holdout.json"
    if target.exists():
        raise ValueError("Internal holdout already evaluated; no second peek")
    summary = aggregate()
    selected = summary["selected"]
    if selected is None:
        raise ValueError("No registered winner passed ranking gate")
    plan = json.loads(PLAN.read_text())
    proposal = json.loads((PROPOSALS / f"search_{selected['searcher']:02d}.json").read_text())
    variant = proposal["variants"][selected["variant"]]
    if variant["id"] != f"v{selected['variant']:02d}" or variant["model"] != selected["model"]:
        raise ValueError("Selected variant/proposal mismatch")
    parts = [ROOT / "mnq-private-data" / f"MNQ_Yahoo_1m_20260913_20261012_part{i:02d}.csv" for i in range(1, 6)]
    if any(sha256(part) != expected for part, expected in zip(parts, PART_HASHES[:5])):
        raise ValueError("Holdout source part hash mismatch")
    bars, audit = load_candles(parts)
    bars = bars[bars.timestamp < END].reset_index(drop=True)
    states = build_market_states(bars)
    causal = causal_features(bars)
    ready = (states.ready & causal.feature_ready & physics_features(bars, states).physics_ready).to_numpy(bool)
    states["log1p_atr14_ticks"] = np.log1p(states.atr14 / .25)
    features = pd.concat([states[FEATURES], causal[FEATURE_NAMES]], axis=1)
    if tuple(features.columns) != POOL or not np.isfinite(features.loc[ready].to_numpy(float)).all():
        raise ValueError("Holdout feature bank differs from selection")
    names = variant["features"]
    maturity = START - pd.Timedelta(minutes=plan["purge_minutes"])
    train_y, train_valid = oracle_values(bars, maturity)
    train = ready & train_valid & (bars.timestamp < maturity).to_numpy()
    eval_mask = ready & (bars.timestamp >= START).to_numpy() & (bars.timestamp < END).to_numpy()
    model = make_model(variant)
    with threadpool_limits(limits=1):
        model.fit(features.loc[train, names].to_numpy(float), train_y[train])
        prediction = np.zeros((len(bars), 8), float)
        prediction[eval_mask] = model.predict(features.loc[eval_mask, names].to_numpy(float))
    joblib.dump({"model": model, "features": names, "action_order": ACTIONS,
                 "plan_sha256": sha256(PLAN), "proposal_sha256": sha256(PROPOSALS / f"search_{selected['searcher']:02d}.json"),
                 "training_maturity_cutoff": maturity.isoformat(), "research_only": True,
                 "live_authorized": False}, OUT / "selected_model_RESEARCH.joblib")
    signal, horizon, chosen = decide(prediction, eval_mask)
    holdout_y, holdout_valid = oracle_values(bars, END)
    ranked = eval_mask & holdout_valid
    rank, by_action = score_actions(prediction[ranked], holdout_y[ranked])
    actual_best = np.where(np.max(holdout_y[ranked], axis=1) > 0,
                           np.argmax(holdout_y[ranked], axis=1) + 1, 0)
    student_best = np.where(signal[ranked] != 0, chosen[ranked] + 1, 0)
    chosen_net = np.where(signal[ranked] != 0,
                          holdout_y[ranked][np.arange(ranked.sum()), chosen[ranked]], 0.)
    write_records(OUT / "selected_decisions_PRIVATE.jsonl.gz", (
        {"index": int(i), "available_at": (bars.timestamp.iloc[i] + pd.Timedelta(minutes=1)).isoformat(),
         "ready": bool(eval_mask[i]), "action": int(signal[i]), "horizon": int(horizon[i]),
         "predicted_robust_net_usd": [float(v) for v in prediction[i]],
         "live_authorized": False} for i in np.flatnonzero((bars.timestamp >= START) & (bars.timestamp < END))))
    atr = states.atr14.to_numpy(float)
    days = sorted(set(session_days(bars.loc[(bars.timestamp >= START) & (bars.timestamp < END), "timestamp"])))
    evaluations = []
    for delay in (0, 1):
        action = delayed_signal(signal, ready, bars.timestamp) if delay else signal
        held = np.r_[10, horizon[:-1]] if delay else horizon
        for name, cost in COSTS.items():
            metrics, trades, events = replay_causal(bars, action, atr, START, END,
                                                     "time10", cost, holding_bars=held)
            key = f"selected_delay{delay}_{name}"
            write_records(OUT / (key + "_trades_PRIVATE.jsonl.gz"), trades)
            write_records(OUT / (key + "_events_PRIVATE.jsonl.gz"), events)
            gap = [trade for trade in trades if trade["reason"] == "unresolved_gap_next_observed_open"]
            row = {"delay": delay, "cost": name, "metrics": metrics,
                   "gap_exit_net_usd": float(sum(trade["net"] for trade in gap))}
            if name == "stress":
                row["session_bootstrap"] = lower_bound(trades, days)
            evaluations.append(row)
    trace_index = next((int(i) for i in np.flatnonzero(ranked) if signal[i]), int(np.flatnonzero(ranked)[0]))
    trace = linear_trace(model, names, features.loc[trace_index, names].to_numpy(float),
                         prediction[trace_index], int(chosen[trace_index]),
                         (bars.timestamp.iloc[trace_index] + pd.Timedelta(minutes=1)).isoformat(),
                         holdout_y[trace_index]) if variant["model"] == "ridge" else None
    if trace is not None:
        trace["actual_student_action"] = int(signal[trace_index])
        save_json(OUT / "brain_trace_PRIVATE.json", trace)
    result = {"status": "complete_internal_development", "selected_searcher": selected["searcher"],
              "selected_variant": selected["variant"], "selected_model": variant["model"],
              "training_rows": int(train.sum()), "holdout_ready_mature_opportunities": int(ranked.sum()),
              "holdout_rank_score": rank, "holdout_action_rank_scores": by_action,
              "oracle_positive_fraction": float((actual_best != 0).mean()),
              "student_signal_fraction": float((student_best != 0).mean()),
              "oracle_action_imitation_fraction": float((student_best == actual_best).mean()),
              "selected_opportunity_robust_net_mean_usd": float(chosen_net[student_best != 0].mean()) if (student_best != 0).any() else None,
              "signals": int(np.count_nonzero(signal)), "evaluations": evaluations,
              "source_audit": audit, "holdout_is_confirmation": False,
              "paper_api_feature_parity": set(names) <= set(FEATURES),
              "live_authorized": False, "broker_orders": 0, "sealed_2025_access": False}
    save_json(target, result)
    return result


if __name__ == "__main__":
    run()
