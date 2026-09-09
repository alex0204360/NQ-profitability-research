"""Recorded two-round research with an explicit publication seal before holdout."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict
from itertools import chain, pairwise
from pathlib import Path

import numpy as np
import pandas as pd

from .execution import action_grid, payoff_matrix
from .features import compute_features
from .inference import bootstrap_evidence, daily_arrays, holm, summarize_trades
from .policies import encode_states, fit_encoder, fit_policy
from .replay import complete_future, decision_indices, feasible_horizons, replay_policy

ET = "America/New_York"
BOUNDARIES = tuple(
    pd.Timestamp(t, tz=ET).tz_convert("UTC")
    for t in ["2023-04-01", "2023-07-01", "2024-01-01", "2024-07-01", "2025-01-01"]
)
CUTOFF = BOUNDARIES[-1]
HOLDOUT_END = pd.Timestamp("2025-12-12", tz=ET).tz_convert("UTC")
FAMILIES = {1: ("regime8", "prototype8"), 2: ("regime16", "prototype16")}
V1_COMMIT = "731607099729bdc1e3151b767a695e5c86aea503"
RAW_SHA256 = "1577e60a7feab411e49da7a56c7052a64738cd1757cfd60aa11fd783ff43b60b"


def file_hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value, *, immutable=False):
    path = Path(path)
    raw = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if immutable and path.exists():
        if path.read_text() != raw:
            raise ValueError(f"immutable artifact differs: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(raw)
    temporary.replace(path)


def event(root, stage, status, **detail):
    path = Path(root) / "history/events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "time_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "stage": stage,
        "status": status,
        "agent": "root",
        **detail,
    }
    with path.open("a") as stream:
        stream.write(json.dumps(entry, sort_keys=True, allow_nan=False) + "\n")


def check_gate(summary, *, folds=None, heldout=False, benchmarks=None):
    """Preregistered economic/support screen, independent of bootstrap inference."""
    reasons = []
    if summary["n"] < (200 if heldout else 300):
        reasons.append("sample_size")
    if summary["censored_trades"] != 0:
        reasons.append("censored_executions")
    if benchmarks is not None and any(b["censored_trades"] != 0 for b in benchmarks):
        reasons.append("baseline_censored_executions")
    if summary["dates"] < (60 if heldout else 90):
        reasons.append("date_support")
    if heldout and summary["weeks"] < 26:
        reasons.append("week_support")
    mean = summary["mean_net_points"]
    if mean is None or mean < 0.25:
        reasons.append("net_expectancy")
    # Primary cost1 to stress cost2 adds exactly one point per priced trade.
    if mean is None or mean - 1.0 < 0:
        reasons.append("stress_expectancy")
    if not heldout:
        if folds is None or len(folds) != 4 or any(f["n"] < 30 for f in folds):
            reasons.append("fold_support")
        if folds is None or sum(f["total_net_points"] > 0 for f in folds) < 3:
            reasons.append("fold_consistency")
    return reasons


def prepare(root, upstream):
    """Copy audited training/calendar inputs; never open held-out market data."""
    root, upstream = Path(root), Path(upstream)
    inherited = read_json(upstream / "reports/pipeline_freeze.json")
    if inherited["raw_sha256"] != RAW_SHA256 or inherited["training_rows"] != 706008:
        raise ValueError("upstream acquisition differs from preregistered input")
    (root / "data").mkdir(exist_ok=True)
    for name in ("training.parquet", "schedule.parquet"):
        source, target = upstream / "data" / name, root / "data" / name
        if target.exists() and file_hash(source) != file_hash(target):
            raise ValueError("prepared input changed")
        if not target.exists():
            shutil.copyfile(source, target)
    for name in ("pipeline_freeze.json", "data_quality.json"):
        write_json(
            root / "reports" / ("inherited_" + name),
            read_json(upstream / "reports" / name),
            immutable=True,
        )
    training = pd.read_parquet(root / "data/training.parquet")
    if (training.timestamp >= CUTOFF).any() or len(training) != 706008:
        raise ValueError("training contains wrong dates or row count")
    manifest = {
        "v1_commit": V1_COMMIT,
        "raw_sha256": RAW_SHA256,
        "input_hashes": {
            name: file_hash(root / "data" / name)
            for name in ("training.parquet", "schedule.parquet")
        },
        "training_rows": len(training),
        "holdout_rows": inherited["holdout_rows"],
        "holdout_sha256": file_hash(upstream / "data/holdout.parquet"),
        "holdout_cutoff": CUTOFF.isoformat(),
        "holdout_end": HOLDOUT_END.isoformat(),
        "holdout_access": "not_opened_by_v2",
        "metadata_ready": False,
    }
    write_json(root / "reports/input_manifest.json", manifest, immutable=True)
    actions = [{**asdict(a), "action_id": a.action_id} for a in action_grid()]
    write_json(root / "models/action_manifest.json", actions, immutable=True)
    event(
        root,
        "phase1",
        "completed",
        artifact="reports/input_manifest.json",
        detail="Training/calendar reused; inherited exclusions retained; holdout not opened",
    )
    return manifest


def training_context(root):
    """Cache only training features and common-cohort outcome labels."""
    root = Path(root)
    manifest = read_json(root / "reports/input_manifest.json")
    for name, expected in manifest["input_hashes"].items():
        if file_hash(root / "data" / name) != expected:
            raise ValueError("training input hash changed")
    bars = pd.read_parquet(root / "data/training.parquet")
    if (bars.timestamp >= CUTOFF).any():
        raise ValueError("holdout forbidden in training context")
    schedule = pd.read_parquet(root / "data/schedule.parquet")
    feature_path = root / "data/features.parquet"
    if feature_path.exists():
        features = pd.read_parquet(feature_path)
    else:
        features = compute_features(bars)
        features.to_parquet(feature_path)
    indices = decision_indices(bars, features)
    horizons = feasible_horizons(bars, schedule, CUTOFF)
    common = indices[complete_future(bars, indices) & (horizons[indices] == 45)]
    path = root / "data/net_payoffs.npy"
    if not path.exists():
        values = payoff_matrix(bars, common, features.atr14.iloc[common].to_numpy())
        if not np.isfinite(values).all():
            raise ValueError("common45 cohort has a censored payoff")
        np.save(path, values)
    payoffs = np.load(path, mmap_mode="r")
    if payoffs.shape != (len(common), 1080):
        raise ValueError("cached payoff shape differs")
    close_times = pd.DatetimeIndex(bars.timestamp) + pd.Timedelta(minutes=1)
    days = close_times.tz_convert(ET).strftime("%Y-%m-%d").to_numpy()
    label_report = {
        "status": "completed",
        "opportunities": len(indices),
        "common45_fit_opportunities": len(common),
        "actions": 1080,
        "horizons": list(range(1, 46)),
        "net_payoffs_sha256": file_hash(path),
        "feature_sha256": file_hash(feature_path),
        "common45_indices_sha256": hashlib.sha256(common.tobytes()).hexdigest(),
        "out_of_scope_candidates_evaluated": 0,
        "scope_guard": "H>45 raises rejected — out of scope; tested on fixtures",
    }
    write_json(root / "reports/labeling.json", label_report, immutable=True)
    return bars, schedule, features, indices, common, payoffs, close_times, days


def _baseline(model):
    return {**model, "policy_id": "unconditional", "n_states": 1, "states": [model["global"]]}


def _write_trades(path, trades):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = "".join(json.dumps(t, sort_keys=True, allow_nan=False) + "\n" for t in trades)
    if path.exists() and path.read_text() != raw:
        raise ValueError("immutable trade ledger differs")
    path.write_text(raw)


def evaluate_family(root, family, context):
    root = Path(root)
    bars, schedule, features, indices, common, payoffs, close_times, days = context
    actions = read_json(root / "models/action_manifest.json")
    initial = indices[close_times[indices] < BOUNDARIES[0] - pd.Timedelta(minutes=45)]
    encoder = fit_encoder(features.iloc[initial], close_times[initial], family)
    write_json(root / "models" / f"{family}.encoder.json", encoder, immutable=True)
    states = np.full(len(bars), -1, dtype=int)
    states[indices] = encode_states(features.iloc[indices], close_times[indices], encoder)
    all_trades, fold_reports, periods = [], [], []
    for fold, (start, end) in enumerate(pairwise(BOUNDARIES), 1):
        print(f"{family}: fitting/replaying fold {fold}", flush=True)
        mask = close_times[common] < start - pd.Timedelta(minutes=45)
        fit_rows = common[mask]
        model = fit_policy(
            states[fit_rows],
            days[fit_rows],
            payoffs[mask],
            policy_id=family,
            n_states=encoder["n_states"],
            actions=actions,
        )
        model.update(
            fit_end_exclusive=(start - pd.Timedelta(minutes=45)).isoformat(),
            validation_start=start.isoformat(),
            validation_end=end.isoformat(),
        )
        write_json(root / "models" / f"{family}.fold{fold}.json", model, immutable=True)
        validation = indices[(close_times[indices] >= start) & (close_times[indices] < end)]
        horizons = feasible_horizons(bars, schedule, end)
        replay = replay_policy(bars, features, validation, horizons, states, model)
        baseline = replay_policy(
            bars, features, validation, horizons, np.zeros(len(bars), dtype=int), _baseline(model)
        )
        for trade in replay["trades"]:
            trade["fold"] = fold
        _write_trades(root / "reports/trades" / f"{family}.fold{fold}.jsonl", replay["trades"])
        _write_trades(
            root / "reports/trades" / f"unconditional.fold{fold}.jsonl", baseline["trades"]
        )
        summary = summarize_trades(replay["trades"])
        benchmark_summary = summarize_trades(baseline["trades"])
        policy_daily = daily_arrays(replay["trades"], start, end)
        baseline_daily = daily_arrays(baseline["trades"], start, end)
        periods.append((policy_daily, baseline_daily))
        fold_reports.append(
            {
                "fold": fold,
                "fit_opportunities": len(fit_rows),
                "start": start.isoformat(),
                "end": end.isoformat(),
                "summary": summary,
                "baseline": benchmark_summary,
                "decisions": {k: v for k, v in replay.items() if k != "trades"},
            }
        )
        all_trades.extend(replay["trades"])
    summary = summarize_trades(all_trades)
    reasons = check_gate(
        summary,
        folds=[f["summary"] for f in fold_reports],
        benchmarks=[f["baseline"] for f in fold_reports],
    )
    evidence = None
    if not reasons:
        evidence = bootstrap_evidence(periods, draws=9999, seed=20260909 + sum(map(ord, family)))
        if not evidence["lower_bounds_positive"]:
            reasons.append("dependent_bootstrap_bounds")
    days_count = sum(len(p) for p, _ in periods)
    advantage = sum(float((p.pnl - b.pnl).sum()) for p, b in periods) / days_count
    report = {
        "policy_id": family,
        "status": "retained" if not reasons else "rejected",
        "reasons": reasons,
        "summary": summary,
        "folds": fold_reports,
        "daily_advantage_points": advantage,
        "bootstrap": evidence,
        "bootstrap_status": "completed" if evidence else "not_run_screen_failed",
        "qualification_level": "training_screen_only",
        "metadata_ready": False,
    }
    write_json(root / "reports" / f"{family}.training.json", report, immutable=True)
    print(
        f"{family}: n={summary['n']} mean={summary['mean_net_points']} reasons={reasons}",
        flush=True,
    )
    # Final payoff table sees training only. Diagnostic serving remains explicit.
    model = fit_policy(
        states[common],
        days[common],
        payoffs,
        policy_id=family,
        n_states=encoder["n_states"],
        actions=actions,
    )
    model.update(fit_end_exclusive=CUTOFF.isoformat(), fit_scope="training_only")
    write_json(root / "models" / f"{family}.final.json", model, immutable=True)
    write_json(root / "models/unconditional.final.json", _baseline(model), immutable=True)
    event(
        root,
        "candidate",
        report["status"],
        policy_id=family,
        artifact=f"reports/{family}.training.json",
        reasons=reasons,
        authors=["v2_execution", "v2_policies", "v2_inference", "root"],
    )
    return report


def run_round(root, number):
    root = Path(root)
    if number not in FAMILIES:
        raise ValueError("only rounds1 and2 are preregistered")
    path = root / "reports" / f"round{number}.json"
    if path.exists():
        return read_json(path)
    if number == 2 and not (root / "reports/round1.json").exists():
        raise ValueError("round1 must complete before round2")
    context = training_context(root)
    reports = []
    for family in FAMILIES[number]:
        try:
            existing = root / "reports" / f"{family}.training.json"
            if existing.exists() and (root / "models" / f"{family}.final.json").exists():
                result = read_json(existing)
            else:
                result = evaluate_family(root, family, context)
        except Exception as exc:
            result = {"policy_id": family, "status": "failed", "reasons": [str(exc)]}
            event(root, "candidate", "failed", policy_id=family, detail=str(exc))
            write_json(root / "reports" / f"{family}.failure.json", result, immutable=True)
        reports.append(result)
    quality = max(
        [0.0] + [r["daily_advantage_points"] for r in reports if r["status"] == "retained"]
    )
    result = {
        "round": number,
        "status": "completed",
        "policies": reports,
        "quality_points_per_calendar_day": quality,
        "retained": [r["policy_id"] for r in reports if r["status"] == "retained"],
    }
    if number == 2:
        prior = read_json(root / "reports/round1.json")["quality_points_per_calendar_day"]
        result["quality_improvement"] = max(prior, quality) - prior
        result["stop_reasons"] = ["fixed_round_budget"]
        if result["quality_improvement"] < 0.10:
            result["stop_reasons"].append("diminishing_returns")
    write_json(path, result, immutable=True)
    event(root, "tournament_round", "completed", round=number, artifact=str(path.relative_to(root)))
    return result


def freeze(root):
    root = Path(root)
    rounds = [read_json(root / "reports" / f"round{i}.json") for i in (1, 2)]
    survivors = [p for report in rounds for p in report["retained"]]
    artifacts = {}
    for folder in ("src", "models"):
        for path in sorted((root / folder).rglob("*")):
            if path.suffix in (".py", ".json"):
                artifacts[str(path.relative_to(root))] = file_hash(path)
    for name in (
        "docs/research.plan.md",
        "docs/implementation-clarifications.md",
        "reports/input_manifest.json",
        "reports/labeling.json",
        "reports/round1.json",
        "reports/round2.json",
        "data/training.parquet",
        "data/schedule.parquet",
    ):
        artifacts[name] = file_hash(root / name)
    result = {
        "status": "frozen_before_holdout",
        "survivors": survivors,
        "artifacts": artifacts,
        "holdout_cutoff": CUTOFF.isoformat(),
        "holdout_end": HOLDOUT_END.isoformat(),
        "metadata_ready": False,
        "stop_reasons": rounds[-1]["stop_reasons"],
    }
    write_json(root / "reports/freeze.json", result, immutable=True)
    event(root, "freeze", "awaiting_publication_verification", survivors=survivors)
    return result


def validate_freeze(root):
    root = Path(root)
    path = root / "reports/freeze.json"
    proof_path = root / "history/freeze_publication.json"
    if not proof_path.exists():
        raise ValueError("freeze publication must be verified before terminal validation")
    proof = read_json(proof_path)
    if not proof.get("verified") or proof.get("freeze_sha256") != file_hash(path):
        raise ValueError("freeze publication proof differs")
    result = read_json(path)
    for name, expected in result["artifacts"].items():
        artifact = (root / name).resolve()
        if not artifact.is_relative_to(root.resolve()) or file_hash(artifact) != expected:
            raise ValueError(f"frozen artifact changed: {name}")
    return result


def terminal_validation(root, *, holdout_path):
    root = Path(root)
    frozen = validate_freeze(root)
    destination = root / "reports/stage2.json"
    if destination.exists():
        return read_json(destination)
    if not frozen["survivors"]:
        result = {
            "status": "not_run_no_survivors",
            "policies": [],
            "qualified": [],
            "heldout_opened": False,
            "reason": "No training-qualified policy",
        }
        write_json(destination, result, immutable=True)
        event(root, "stage2", result["status"], artifact="reports/stage2.json")
        return result
    sentinel = root / "history/heldout_access.json"
    if sentinel.exists():
        raise ValueError("heldout already opened; no automatic repeat after incomplete evaluation")
    # Exclusive claim is persisted before the first heldout price read.
    with sentinel.open("x") as stream:
        json.dump(
            {
                "freeze_sha256": file_hash(root / "reports/freeze.json"),
                "status": "terminal_access_started",
                "survivors": frozen["survivors"],
            },
            stream,
        )
        stream.write("\n")
    try:
        result = _evaluate_holdout(root, holdout_path, frozen)
    except Exception as exc:
        result = {
            "status": "failed",
            "qualified": [],
            "policies": [],
            "heldout_opened": None,
            "terminal_access_attempted": True,
            "reasons": ["shared_terminal_failure", str(exc)],
        }
    write_json(destination, result, immutable=True)
    event(
        root,
        "stage2",
        result["status"],
        qualified=result["qualified"],
        artifact="reports/stage2.json",
    )
    return result


def score_frozen_family(root, survivors, evaluate):
    """An operational failure remains in the frozen multiplicity family at p=1."""
    results, pvalues = [], {}
    for family in survivors:
        try:
            result = evaluate(family)
        except Exception as exc:
            result = {
                "policy_id": family,
                "status": "failed",
                "summary": None,
                "reasons": ["candidate_execution_failure", str(exc)],
                "bootstrap": None,
            }
            event(root, "heldout_candidate", "failed", policy_id=family, detail=str(exc))
        evidence = result["bootstrap"]
        pvalues[family] = evidence["p_value"] if evidence else 1.0
        results.append(result)
    adjusted = holm(pvalues)
    for result in results:
        result["holm"] = adjusted[result["policy_id"]]
        if not result["holm"]["passed"]:
            result["reasons"].append("holm_familywise")
        result["qualified"] = not result["reasons"]
    return results


def _evaluate_holdout(root, holdout_path, frozen):
    manifest = read_json(root / "reports/input_manifest.json")
    if file_hash(holdout_path) != manifest["holdout_sha256"]:
        raise ValueError("heldout file hash differs from frozen mechanical digest")
    holdout = pd.read_parquet(holdout_path)
    if len(holdout) != 330516 or (holdout.timestamp < CUTOFF).any():
        raise ValueError("heldout input differs from frozen dataset")
    # Causal lookback may use training history without importing any future outcome.
    training_tail = pd.read_parquet(root / "data/training.parquet").tail(61)
    bars = pd.concat([training_tail, holdout], ignore_index=True)
    features = compute_features(bars)
    indices = decision_indices(bars, features)
    times = pd.DatetimeIndex(bars.timestamp) + pd.Timedelta(minutes=1)
    indices = indices[(times[indices] >= CUTOFF) & (times[indices] < HOLDOUT_END)]
    schedule = pd.read_parquet(root / "data/schedule.parquet")
    horizons = feasible_horizons(bars, schedule, HOLDOUT_END)
    baseline_model = read_json(root / "models/unconditional.final.json")
    baseline = replay_policy(
        bars, features, indices, horizons, np.zeros(len(bars), int), baseline_model
    )
    _write_trades(root / "reports/trades/unconditional.heldout.jsonl", baseline["trades"])
    baseline_daily = daily_arrays(baseline["trades"], CUTOFF, HOLDOUT_END)
    baseline_summary = summarize_trades(baseline["trades"])

    def evaluate(family):
        encoder = read_json(root / "models" / f"{family}.encoder.json")
        model = read_json(root / "models" / f"{family}.final.json")
        states = np.full(len(bars), -1, dtype=int)
        states[indices] = encode_states(features.iloc[indices], times[indices], encoder)
        replay = replay_policy(bars, features, indices, horizons, states, model)
        _write_trades(root / "reports/trades" / f"{family}.heldout.jsonl", replay["trades"])
        summary = summarize_trades(replay["trades"])
        reasons = check_gate(summary, heldout=True, benchmarks=[baseline_summary])
        evidence = None
        if not reasons:
            daily = daily_arrays(replay["trades"], CUTOFF, HOLDOUT_END)
            evidence = bootstrap_evidence(
                [(daily, baseline_daily)], draws=99999, seed=20260909 + sum(map(ord, family))
            )
            if not evidence["lower_bounds_positive"]:
                reasons.append("dependent_bootstrap_bounds")
        return {"policy_id": family, "summary": summary, "reasons": reasons, "bootstrap": evidence}

    results = score_frozen_family(root, frozen["survivors"], evaluate)
    return {
        "status": "completed",
        "policies": results,
        "heldout_opened": True,
        "qualified": [r["policy_id"] for r in results if r["qualified"]],
        "baseline": baseline_summary,
        "metadata_ready": False,
        "claim_scope": "modeled historical NQ policy; not live or verified MNQ execution",
    }


def finalize(root):
    root = Path(root)
    stage2 = read_json(root / "reports/stage2.json")
    frozen = read_json(root / "reports/freeze.json")
    entries, qualified = [], []
    for family in chain.from_iterable(FAMILIES.values()):
        model_path = f"models/{family}.final.json"
        if not (root / model_path).exists():
            continue
        training = read_json(root / "reports" / f"{family}.training.json")
        passed = family in stage2["qualified"]
        stats = next(
            (
                r["summary"]
                for r in stage2["policies"]
                if r["policy_id"] == family and r.get("summary") is not None
            ),
            training["summary"],
        )
        entry = {
            "policy_id": family,
            "model_path": model_path,
            "encoder_path": f"models/{family}.encoder.json",
            "model_sha256": file_hash(root / model_path),
            "encoder_sha256": file_hash(root / "models" / f"{family}.encoder.json"),
            "qualified": passed,
            "status": "historical_modeled_qualified" if passed else "unqualified_diagnostic",
            "stats": stats,
            "training_reasons": training["reasons"],
            "stats_scope": "heldout"
            if any(r["policy_id"] == family for r in stage2["policies"])
            else "walk_forward",
        }
        (qualified if passed else entries).append(entry)
    library = {
        "schema_version": 2,
        "instrument": "NQ",
        "tick_size": 0.25,
        "qualified_policies": qualified,
        "diagnostic_policies": entries,
        "metadata_ready": False,
        "max_horizon": 45,
        "qualification_unit": "policy; individual states/actions are descriptive",
    }
    write_json(root / "patterns/library.json", library, immutable=True)
    write_json(
        root / "reports/stage1.json",
        {"status": "completed", "training_survivors": frozen["survivors"], "causal_features": True},
        immutable=True,
    )
    write_json(
        root / "reports/stage3.json",
        {
            "status": "out_of_scope_not_run",
            "reason": "No feed, broker, Pine, or forward-testing connection",
        },
        immutable=True,
    )
    result = {
        "rounds": 2,
        "policies_attempted": 4,
        "qualified_policies": len(qualified),
        "stop_reasons": frozen["stop_reasons"],
        "stage2_status": stage2["status"],
        "metadata_ready": False,
    }
    write_json(root / "reports/research_summary.json", result, immutable=True)
    event(root, "finalize", "completed", artifact="patterns/library.json", **result)
    return result
