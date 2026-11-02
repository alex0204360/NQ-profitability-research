"""Explainable research queries for the rejected multi-horizon MNQ student."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np

from tools.cloud_campaign02 import HORIZONS, choose
from tools.opportunity_research import FEATURES
from tools.reliability_decision_api import _time


def decide(run, observation, *, mode="historical", now=None):
    if mode not in ("historical", "paper"):
        raise ValueError("Historical or paper mode required")
    if not isinstance(observation, dict) or set(observation) != {"available_at", "ready", "features"}:
        raise ValueError("Exact causal observation fields required")
    if type(observation["ready"]) is not bool:
        raise ValueError("Boolean readiness required")
    features = observation["features"]
    if not isinstance(features, dict) or set(features) != set(FEATURES):
        raise ValueError("Exact 18-feature schema required")
    values = [features[name] for name in FEATURES]
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in values):
        raise ValueError("Finite numeric causal features required")
    available = _time(observation["available_at"])
    age = None
    if mode == "paper":
        current = datetime.now(UTC) if now is None else now
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("Aware clock required")
        age = (current - available).total_seconds()
        if age < 0 or age > 120:
            raise ValueError("Future or stale completed bar")
    run = Path(run).resolve()
    if "2025" in str(run):
        raise ValueError("Sealed path forbidden")
    manifest = json.loads((run / "manifest.json").read_text())
    if manifest.get("completed") is not True:
        raise ValueError("Incomplete student campaign")
    hashes = manifest["files_sha256"]
    for name in ("student.joblib", "protocol.json", "source_hashes.json", "results.json"):
        if hashlib.sha256((run / name).read_bytes()).hexdigest() != hashes[name]:
            raise ValueError("Student artifact changed: " + name)
    source_hashes = json.loads((run / "source_hashes.json").read_text())
    code = Path(__file__).resolve().parents[1]
    for name, relative in {"cloud_campaign02.py": "tools/cloud_campaign02.py",
                           "CLOUD_CAMPAIGN02.json": "docs/CLOUD_CAMPAIGN02.json",
                           "causal_execution_v3.py": "tools/causal_execution_v3.py",
                           "shared_game_state.py": "tools/shared_game_state.py"}.items():
        if hashlib.sha256((code / relative).read_bytes()).hexdigest() != source_hashes[name]:
            raise ValueError("Campaign source changed: " + name)
    bundle = joblib.load(io.BytesIO((run / "student.joblib").read_bytes()))
    if (bundle["id"] != "extra_trees_multihorizon" or bundle["features"] != FEATURES or
            tuple(bundle["horizons"]) != HORIZONS or
            bundle["plan_sha256"] != source_hashes["CLOUD_CAMPAIGN02.json"]):
        raise ValueError("Student identity changed")
    if available <= _time(bundle["training_end"]):
        raise ValueError("Observation overlaps training")
    prediction = np.asarray(bundle["model"].predict(np.asarray([values], float)))
    if prediction.shape != (1, 8) or not np.isfinite(prediction).all():
        raise ValueError("Eight finite expected values required")
    direction, horizon, minimum_net = choose(prediction, np.array([observation["ready"]]))
    side = int(direction[0])
    action = {0: "abstain", 1: "enter_long", -1: "enter_short"}[side]
    forecast = {str(held): {"next_open_gross_usd": float(prediction[0, j * 2]),
                            "one_bar_delay_gross_usd": float(prediction[0, j * 2 + 1])}
                for j, held in enumerate(HORIZONS)}
    return {"schema_version": "cloud-exit-student-v1", "mode": mode,
            "available_at": available.isoformat(), "paper_age_seconds": age,
            "action": action, "planned_horizon_bars": int(horizon[0]) if side else None,
            "minimum_predicted_stress_net_usd": float(minimum_net[0]),
            "predicted_long_gross_by_horizon": forecast,
            "reason": "Both fill timings exceed stressed modeled costs" if side else
                      "No horizon and direction clears both fill timings after stress costs",
            "model_scope": "Expected values only; hindsight teacher exits were targets, never causal inputs",
            "uncertainty": "Uncalibrated. This candidate failed registered development screens.",
            "hash_lineage": {name: hashes[name] for name in ("student.joblib", "protocol.json", "results.json")},
            "research_only": True, "selected": False, "live_authorized": False, "orders_submitted": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--observation", type=Path, required=True)
    parser.add_argument("--mode", choices=("historical", "paper"), default="historical")
    args = parser.parse_args()
    print(json.dumps(decide(args.run, json.loads(args.observation.read_text()), mode=args.mode), indent=2))


if __name__ == "__main__":
    main()
