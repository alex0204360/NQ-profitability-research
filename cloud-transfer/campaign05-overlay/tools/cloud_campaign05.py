"""Cross-check ten searcher proposals against a hindsight oracle, without leakage.

Each tester runs ten fixed variants on three chronological selection folds.
This module never opens campaign05's reserved October 1–6 holdout outcomes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import ExtraTreesRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from tools.cloud_campaign02 import HORIZONS, values
from tools.mnq_oracle_prepare import FEATURE_NAMES, causal_features, load_candles, sha256
from tools.mnq_oracle_research import PART_HASHES, save_json
from tools.opportunity_research import FEATURES
from tools.physics_state import physics_features
from tools.shared_game_state import build_market_states

ROOT = Path("/workspace")
CODE = Path(__file__).resolve().parents[1]
PLAN = CODE / "docs/CLOUD_CAMPAIGN05.json"
PROPOSALS = CODE / "docs/campaign05"
MANIFEST = PROPOSALS / "proposals_manifest.json"
OUT = ROOT / "mnq-private-results/cloud_campaign05"
POOL = tuple(FEATURES + FEATURE_NAMES)
ACTIONS = tuple((side, horizon) for horizon in HORIZONS for side in (1, -1))


def oracle_values(bars: pd.DataFrame, cutoff: pd.Timestamp) -> tuple[np.ndarray, np.ndarray]:
    """Eight hindsight robust net actions; both fill delays must mature."""
    gross, valid = values(bars, cutoff)
    output = np.empty((len(bars), 8), float)
    for j in range(4):
        immediate, delayed = gross[:, 2*j], gross[:, 2*j+1]
        output[:, 2*j] = np.minimum(immediate, delayed) - 6.
        output[:, 2*j+1] = -np.maximum(immediate, delayed) - 6.
    output[~valid] = np.nan
    return output, valid


def check_proposal(index: int) -> dict:
    if index not in range(1, 11):
        raise ValueError("Searcher index must be 1..10")
    manifest = json.loads(MANIFEST.read_text())
    if sha256(PLAN) != manifest["plan_sha256"] or sha256(Path(__file__)) != manifest["runner_sha256"]:
        raise ValueError("Frozen protocol or tester runner changed")
    path = PROPOSALS / f"search_{index:02d}.json"
    if sha256(path) != manifest["proposals"][path.name]:
        raise ValueError("Frozen searcher proposal changed")
    proposal = json.loads(path.read_text())
    if proposal["id"] != f"search_{index:02d}" or len(proposal["variants"]) != 10:
        raise ValueError("Proposal must contain exactly ten variants")
    signatures = set()
    for j, variant in enumerate(proposal["variants"]):
        if variant["id"] != f"v{j:02d}" or variant["model"] not in {"ridge", "extra_trees", "random_forest"}:
            raise ValueError("Unsupported model or variant ID")
        features = variant["features"]
        if not features or len(features) != len(set(features)) or not set(features) <= set(POOL):
            raise ValueError("Invalid or noncausal feature selection")
        params = variant["params"]
        if variant["model"] == "ridge":
            if set(params) != {"alpha"} or not 0 < params["alpha"] <= 10000:
                raise ValueError("Invalid ridge configuration")
        elif set(params) != {"n_estimators", "max_depth", "min_samples_leaf", "max_features", "bootstrap"} or (
            params["n_estimators"] not in (24, 40) or params["max_depth"] not in range(3, 8)
            or params["min_samples_leaf"] not in (40, 80, 160, 320)
            or params["max_features"] not in (.5, .75, 1.) or type(params["bootstrap"]) is not bool
        ):
            raise ValueError("Invalid tree configuration")
        signature = json.dumps({"features": features, "model": variant["model"], "params": params}, sort_keys=True)
        if signature in signatures:
            raise ValueError("Duplicate trial configuration")
        signatures.add(signature)
    return proposal


def make_model(variant: dict):
    if variant["model"] == "ridge":
        return make_pipeline(StandardScaler(), Ridge(**variant["params"]))
    cls = ExtraTreesRegressor if variant["model"] == "extra_trees" else RandomForestRegressor
    return cls(**variant["params"], random_state=20261103, n_jobs=1)


def score_actions(pred: np.ndarray, realized: np.ndarray) -> tuple[float, list[float]]:
    if pred.shape != realized.shape or pred.shape[1] != 8 or not np.isfinite(pred).all() or not np.isfinite(realized).all():
        raise ValueError("Eight aligned finite action values required")
    by_action = []
    for j in range(8):
        statistic = float(spearmanr(pred[:, j], realized[:, j]).statistic)
        by_action.append(statistic if np.isfinite(statistic) else -1.)
    return float(np.mean(by_action)), by_action


def build_folds(plan: dict) -> tuple[pd.DataFrame, pd.DataFrame, np.ndarray, list]:
    # The first four source parts cover all selection folds. Later files and
    # the legacy hindsight teacher CSV are never opened by tester workers.
    parts = [ROOT / "mnq-private-data" / f"MNQ_Yahoo_1m_20260913_20261012_part{i:02d}.csv" for i in range(1, 5)]
    if any(sha256(part) != expected for part, expected in zip(parts, PART_HASHES[:4])):
        raise ValueError("Selection source part hash mismatch")
    bars, audit = load_candles(parts)
    if audit["duplicate_rows_identical_removed"]:
        raise ValueError("Unexpected source duplicates")
    # Outcome access is capped at the end of selection fold 3.
    cutoff = pd.Timestamp(plan["folds"][-1]["validation_end_exclusive"])
    mask = (bars.timestamp < cutoff).to_numpy()
    bars = bars.loc[mask].reset_index(drop=True)
    states = build_market_states(bars)
    causal = causal_features(bars)
    ready = (states.ready & causal.feature_ready &
             physics_features(bars, states).physics_ready).to_numpy(bool)
    states["log1p_atr14_ticks"] = np.log1p(states.atr14 / .25)
    features = pd.concat([states[FEATURES], causal[FEATURE_NAMES]], axis=1)
    if tuple(features.columns) != POOL or not np.isfinite(features.loc[ready].to_numpy(float)).all():
        raise ValueError("Invalid finite causal feature bank")
    folds = []
    for spec in plan["folds"]:
        train_end = pd.Timestamp(spec["train_end_exclusive"])
        maturity = train_end - pd.Timedelta(minutes=plan["purge_minutes"])
        val_start, val_end = pd.Timestamp(spec["validation_start"]), pd.Timestamp(spec["validation_end_exclusive"])
        train_y, train_valid = oracle_values(bars, maturity)
        val_y, val_valid = oracle_values(bars, val_end)
        train = ready & train_valid & (bars.timestamp < maturity).to_numpy()
        val = ready & val_valid & (bars.timestamp >= val_start).to_numpy() & (bars.timestamp < val_end).to_numpy()
        if train.sum() < 1000 or val.sum() < 300:
            raise ValueError("Insufficient mature ready fold rows")
        folds.append((train, train_y, val, val_y))
    return bars, features, ready, folds


def run_family(index: int, out: Path | None = None) -> dict:
    proposal = check_proposal(index)
    out = Path(out) if out is not None else OUT / f"test_{index:02d}.json"
    if out.exists():
        raise ValueError("Tester result already exists; immutable output")
    plan = json.loads(PLAN.read_text())
    _bars, features, _ready, folds = build_folds(plan)
    result = {"status": "running", "searcher": proposal["id"], "tester": f"test_{index:02d}",
              "proposal_sha256": sha256(PROPOSALS / f"search_{index:02d}.json"),
              "plan_sha256": sha256(PLAN), "runner_sha256": sha256(Path(__file__)),
              "fold_rows": [{"train": int(train.sum()), "validation": int(val.sum())}
                            for train, _, val, _ in folds],
              "variants": [], "holdout_opened": False, "sealed_2025_access": False, "broker_orders": 0}
    for variant in proposal["variants"]:
        columns = variant["features"]
        scores, oracle_rates, imitation, participation = [], [], [], []
        for train, train_y, val, val_y in folds:
            model = make_model(variant)
            with threadpool_limits(limits=1):
                model.fit(features.loc[train, columns].to_numpy(float), train_y[train])
                pred = model.predict(features.loc[val, columns].to_numpy(float))
            fold_score, _ = score_actions(pred, val_y[val])
            scores.append(fold_score)
            oracle_action = np.where(np.max(val_y[val], axis=1) > 0, np.argmax(val_y[val], axis=1) + 1, 0)
            student_action = np.where(np.max(pred, axis=1) > 0, np.argmax(pred, axis=1) + 1, 0)
            oracle_rates.append(float((oracle_action != 0).mean()))
            imitation.append(float((student_action == oracle_action).mean()))
            participation.append(float((student_action != 0).mean()))
        result["variants"].append({"id": variant["id"], "fold_rank_scores": scores,
                                   "mean_rank_score": float(np.mean(scores)),
                                   "oracle_positive_fraction_by_fold": oracle_rates,
                                   "oracle_imitation_fraction_by_fold": imitation,
                                   "student_signal_fraction_by_fold": participation,
                                   "current_paper_api_feature_parity": set(columns) <= set(FEATURES)})
    result["status"] = "complete_selection_only"
    out.parent.mkdir(parents=True, exist_ok=True)
    save_json(out, result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--searcher", type=int, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    run_family(args.searcher, args.out)
