"""Exactly 100 frozen robust-value trials on earlier 2026 MNQ observations.

The October 1–6 internal holdout is opened development evidence, never
independent confirmation. No 2025 data or uploaded October 13+ bars are read.
"""
from __future__ import annotations

import itertools
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import ExtraTreesRegressor
from threadpoolctl import threadpool_limits

from tools.causal_execution import replay_causal
from tools.cloud_robust_teacher import robust_teacher
from tools.fresh_transfer_test import delayed_signal, lower_bound, session_days
from tools.mnq_oracle_prepare import sha256
from tools.mnq_oracle_research import load_inputs, save_json
from tools.opportunity_research import COSTS, FEATURES, write_records
from tools.physics_state import physics_features
from tools.shared_game_state import build_market_states

ROOT = Path("/workspace")
CODE = Path(__file__).resolve().parents[1]
PLAN = CODE / "docs/CLOUD_CAMPAIGN04.json"
DATA = ROOT / "mnq-private-data"
OUT = ROOT / "mnq-private-results/cloud_campaign04"


def configurations(plan: dict) -> list[dict]:
    grid = plan["grid"]
    keys = ("n_estimators", "max_depth", "min_samples_leaf", "max_features", "bootstrap")
    all_configs = [dict(zip(keys, values)) for values in itertools.product(*(grid[key] for key in keys))]
    if len(all_configs) < plan["trial_budget"] or len({tuple(c.values()) for c in all_configs}) != len(all_configs):
        raise ValueError("Insufficient unique fixed trial configurations")
    order = np.random.default_rng(20261103).permutation(len(all_configs))[:plan["trial_budget"]]
    return [all_configs[int(i)] for i in order]


def decision(prediction: np.ndarray, ready: np.ndarray) -> np.ndarray:
    if prediction.shape != (len(ready), 2) or not np.isfinite(prediction[ready]).all():
        raise ValueError("Invalid robust long/short predictions")
    return np.where(ready & (prediction[:, 0] > 0) & (prediction[:, 0] > prediction[:, 1]), 1,
                    np.where(ready & (prediction[:, 1] > 0) & (prediction[:, 1] > prediction[:, 0]), -1, 0)).astype(int)


def fold_arrays(bars: pd.DataFrame, features: np.ndarray, ready: np.ndarray,
                train_end: pd.Timestamp, val_start: pd.Timestamp, val_end: pd.Timestamp,
                purge_minutes: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    maturity = train_end - pd.Timedelta(minutes=purge_minutes)
    train_net, train_valid, _ = robust_teacher(bars, maturity)
    val_net, val_valid, _ = robust_teacher(bars, val_end)
    train = ready & train_valid & (bars.timestamp < maturity).to_numpy()
    val = ready & val_valid & (bars.timestamp >= val_start).to_numpy() & (bars.timestamp < val_end).to_numpy()
    if train.sum() < 1000 or val.sum() < 300:
        raise ValueError("Too few mature ready rows in fixed chronological fold")
    return features[train], np.min(train_net[train], axis=2), features[val], np.min(val_net[val], axis=2)


def rank_score(pred: np.ndarray, actual: np.ndarray) -> float:
    correlations = [float(spearmanr(pred[:, k], actual[:, k]).statistic) for k in range(2)]
    if not np.isfinite(correlations).all():
        return -1.0
    return float(np.mean(correlations))


def run(out: Path = OUT) -> dict:
    out = Path(out)
    if out.exists():
        raise ValueError("Campaign04 output exists; immutable run requires a new directory")
    plan = json.loads(PLAN.read_text())
    configs = configurations(plan)
    out.mkdir(parents=True)
    save_json(out / "protocol.json", plan)
    save_json(out / "source_hashes.json", {p.name: sha256(p) for p in
              (PLAN, Path(__file__), CODE / "tools/cloud_robust_teacher.py",
               CODE / "tools/cloud_campaign01.py", CODE / "tools/causal_execution.py")})
    report = {"status": "running", "trial_budget": len(configs), "trials": [],
              "selected": None, "internal_holdout": None, "sealed_2025_access": False,
              "broker_orders": 0}
    try:
        bars, old_features, _, audit = load_inputs(DATA)
        states = build_market_states(bars)
        ready = (states.ready & old_features.feature_ready & physics_features(bars, states).physics_ready).to_numpy(bool)
        states["log1p_atr14_ticks"] = np.log1p(states.atr14 / .25)
        x = states[FEATURES].to_numpy(float)
        if not np.isfinite(x[ready]).all():
            raise ValueError("Nonfinite causal training feature")
        folds = []
        for fold in plan["selection_folds"]:
            arrays = fold_arrays(bars, x, ready, pd.Timestamp(fold["train_end_exclusive"]),
                                 pd.Timestamp(fold["validation_start"]),
                                 pd.Timestamp(fold["validation_end_exclusive"]), plan["purge_minutes"])
            folds.append(arrays)
        save_json(out / "data_summary.json", {"source_audit": audit, "features": FEATURES,
                  "fold_rows": [{"train": len(a), "validation": len(c)} for a, _, c, _ in folds],
                  "last_source_timestamp": bars.timestamp.iloc[-1].isoformat()})
        for i, config in enumerate(configs):
            scores = []
            for train_x, train_y, val_x, val_y in folds:
                model = ExtraTreesRegressor(**config, random_state=20261103, n_jobs=1)
                with threadpool_limits(limits=1):
                    model.fit(train_x, train_y)
                    pred = model.predict(val_x)
                scores.append(rank_score(pred, val_y))
            report["trials"].append({"index": i, "configuration": config,
                                     "fold_rank_scores": scores, "mean_rank_score": float(np.mean(scores))})
            if (i + 1) % 10 == 0:
                save_json(out / "results.json", report)
                print(f"campaign04 completed {i+1}/100 trials", flush=True)
        eligible = [trial for trial in report["trials"] if min(trial["fold_rank_scores"]) > 0
                    and trial["mean_rank_score"] > .05]
        if not eligible:
            report["status"] = "rejected_no_rank_signal"
        else:
            best = max(eligible, key=lambda row: (row["mean_rank_score"], -row["index"]))
            report["selected"] = best["index"]
            hold = plan["internal_holdout"]
            start, end = pd.Timestamp(hold["start"]), pd.Timestamp(hold["end_exclusive"])
            maturity = pd.Timestamp(hold["train_end_exclusive"]) - pd.Timedelta(minutes=plan["purge_minutes"])
            net, valid, _ = robust_teacher(bars, maturity)
            train = ready & valid & (bars.timestamp < maturity).to_numpy()
            model = ExtraTreesRegressor(**best["configuration"], random_state=20261103, n_jobs=1)
            with threadpool_limits(limits=1):
                model.fit(x[train], np.min(net[train], axis=2))
                pred = np.zeros((len(bars), 2))
                hold_mask = ready & (bars.timestamp >= start).to_numpy() & (bars.timestamp < end).to_numpy()
                pred[hold_mask] = model.predict(x[hold_mask])
            joblib.dump({"model": model, "features": FEATURES, "plan_sha256": sha256(PLAN),
                         "training_maturity_cutoff": maturity.isoformat(),
                         "live_authorized": False}, out / "selected_model.joblib")
            hold_net, hold_valid, _ = robust_teacher(bars, end)
            rank_mask = hold_mask & hold_valid
            rank = rank_score(pred[rank_mask], np.min(hold_net[rank_mask], axis=2)) if rank_mask.sum() >= 20 else None
            signal = decision(pred, hold_mask)
            atr = states.atr14.to_numpy(float)
            days = sorted(set(session_days(bars.loc[(bars.timestamp >= start) & (bars.timestamp < end), "timestamp"])))
            evaluations = []
            for delay in (0, 1):
                delayed = delayed_signal(signal, ready, bars.timestamp) if delay else signal
                for cost_name, cost in COSTS.items():
                    metrics, trades, events = replay_causal(bars, delayed, atr, start, end, "time10", cost)
                    key = f"selected_delay{delay}_{cost_name}"
                    write_records(out / (key + "_trades_PRIVATE.jsonl.gz"), trades)
                    write_records(out / (key + "_events_PRIVATE.jsonl.gz"), events)
                    gap_trades = [t for t in trades if t["reason"] == "unresolved_gap_next_observed_open"]
                    row = {"delay": delay, "cost": cost_name, "metrics": metrics,
                           "unresolved_gap_trade_net_usd": float(sum(t["net"] for t in gap_trades))}
                    if cost_name == "stress":
                        row["session_bootstrap"] = lower_bound(trades, days)
                    evaluations.append(row)
            report["internal_holdout"] = {"mature_ready_opportunities": int(rank_mask.sum()),
                                          "robust_value_rank_score": rank,
                                          "signals": int(np.count_nonzero(signal)),
                                          "evaluations": evaluations,
                                          "classification": "opened development evidence, not confirmation"}
            report["status"] = "complete_internal_development"
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
