"""Frozen causal state encoders and day-cluster-shrunk net payoff tables.

Encoders see only the initial fit rows supplied by the caller. Payoff tables see
only the caller's expanding, purged fit cohort. Inference never refits either
artifact, and its output is a forecast, not a profitability qualification.
"""

from __future__ import annotations

from numbers import Integral
from typing import Any

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

PROTOTYPE_FEATURES = [
    "price_z20",
    "trend20_60",
    "body_fraction",
    "upper_wick_fraction",
    "lower_wick_fraction",
    "lag1_return_to_range",
    "range_to_atr14",
    "volume_z20",
    "range_z20",
    "position60",
]
_FAMILIES = {"regime8": 8, "regime16": 16, "prototype8": 8, "prototype16": 16}
_PSEUDOCOUNT = 200
_MIN_SAMPLE = 200
_MIN_DATES = 20
_SEED = 20260909


def _timestamps(timestamps: Any, n: int) -> pd.DatetimeIndex:
    try:
        values = pd.DatetimeIndex(timestamps)
    except (ValueError, TypeError) as exc:
        raise ValueError("timestamps must be timezone-aware completed-bar close times") from exc
    if len(values) != n or values.tz is None or values.hasnans:
        raise ValueError("timestamps must be complete, timezone aware, and match feature rows")
    return values


def _feature_values(features: pd.DataFrame, columns: list[str]) -> np.ndarray:
    if not isinstance(features, pd.DataFrame) or not set(columns).issubset(features.columns):
        raise ValueError(f"features must contain {columns}")
    try:
        values = features[columns].to_numpy(dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("encoder features must be finite numeric values") from exc
    if not np.isfinite(values).all():
        raise ValueError("encoder features must be finite numeric values")
    return values


def fit_encoder(features: pd.DataFrame, timestamps: Any, family: str) -> dict[str, Any]:
    """Fit a JSON-serializable encoder on supplied initial-fit opportunities only.

    ``timestamps`` are decision close times, never canonical bar-start times.
    The caller owns chronological purging and the five-minute decision cohort.
    """
    if family not in _FAMILIES:
        raise ValueError(f"unknown policy family: {family}")
    _timestamps(timestamps, len(features))
    if len(features) == 0:
        raise ValueError("cannot fit an encoder without initial-fit observations")
    n_states = _FAMILIES[family]
    encoder: dict[str, Any] = {"family": family, "n_states": n_states}
    if family.startswith("regime"):
        values = _feature_values(features, ["trend20_60", "atr14_fraction"])
        encoder["volatility_median"] = float(np.median(values[:, 1]))
        return encoder

    values = _feature_values(features, PROTOTYPE_FEATURES)
    if len(values) < n_states:
        raise ValueError("prototype encoder needs at least one fit observation per prototype")
    with threadpool_limits(limits=1):
        scaler = StandardScaler()
        standardized = scaler.fit_transform(values)
        estimator = KMeans(
            n_clusters=n_states,
            random_state=_SEED,
            n_init=10,
            algorithm="lloyd",
            max_iter=300,
        ).fit(standardized)
    encoder.update(
        feature_columns=list(PROTOTYPE_FEATURES),
        scaler_mean=scaler.mean_.tolist(),
        scaler_scale=scaler.scale_.tolist(),
        centroids=estimator.cluster_centers_.tolist(),
        random_state=_SEED,
        n_init=10,
        algorithm="lloyd",
        max_iter=300,
    )
    return encoder


def encode_states(features: pd.DataFrame, timestamps: Any, encoder: dict[str, Any]) -> np.ndarray:
    """Assign states using saved scales/centroids or the frozen volatility median."""
    family = encoder.get("family")
    if family not in _FAMILIES or encoder.get("n_states") != _FAMILIES[family]:
        raise ValueError("invalid frozen encoder family or state count")
    close_times = _timestamps(timestamps, len(features))
    if family.startswith("regime"):
        values = _feature_values(features, ["trend20_60", "atr14_fraction"])
        median = float(encoder["volatility_median"])
        if not np.isfinite(median):
            raise ValueError("frozen volatility median must be finite")
        eastern = close_times.tz_convert("America/New_York")
        minute = eastern.hour.to_numpy() * 60 + eastern.minute.to_numpy()
        if family == "regime8":
            bucket = ((minute >= 570) & (minute < 960)).astype(np.int64)
        else:
            bucket = np.searchsorted([360, 570, 960], minute, side="right")
        trend = (values[:, 0] >= 0).astype(np.int64)
        volatility = (values[:, 1] > median).astype(np.int64)
        return (bucket * 4 + trend * 2 + volatility).astype(np.int64)

    if encoder.get("feature_columns") != PROTOTYPE_FEATURES:
        raise ValueError("prototype feature order differs from the frozen protocol")
    values = _feature_values(features, PROTOTYPE_FEATURES)
    mean = np.asarray(encoder["scaler_mean"], dtype=np.float64)
    scale = np.asarray(encoder["scaler_scale"], dtype=np.float64)
    centroids = np.asarray(encoder["centroids"], dtype=np.float64)
    if (
        mean.shape != (len(PROTOTYPE_FEATURES),)
        or scale.shape != mean.shape
        or centroids.shape != (_FAMILIES[family], len(PROTOTYPE_FEATURES))
        or not np.isfinite(mean).all()
        or not np.isfinite(scale).all()
        or not np.isfinite(centroids).all()
        or (scale <= 0).any()
    ):
        raise ValueError("invalid frozen prototype scales or centroids")
    if len(values) == 0:
        return np.empty(0, dtype=np.int64)
    standardized = (values - mean) / scale
    # Chunk inference to avoid an observations x states x features large temporary.
    states = np.empty(len(values), dtype=np.int64)
    for start in range(0, len(values), 4096):
        chunk = standardized[start : start + 4096]
        distances = np.square(chunk[:, None, :] - centroids[None, :, :]).sum(axis=2)
        states[start : start + len(chunk)] = distances.argmin(axis=1)
    return states


def _actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(actions, list) or not actions:
        raise ValueError("at least one action is required")
    copied = []
    identifiers = set()
    for action in actions:
        try:
            horizon = action["horizon"]
            direction = action["direction"]
            target, stop = float(action["tp_atr"]), float(action["sl_atr"])
            identifier = action["action_id"]
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("actions require direction, TP, SL, horizon and action ID") from exc
        if (
            isinstance(horizon, bool)
            or not isinstance(horizon, Integral)
            or not 1 <= horizon <= 45
            or isinstance(direction, bool)
            or direction not in (-1, 1)
            or not np.isfinite([target, stop]).all()
            or min(target, stop) <= 0
            or not isinstance(identifier, str)
            or not identifier
            or identifier in identifiers
        ):
            raise ValueError("invalid or duplicate action; horizons must be within 1..45")
        identifiers.add(identifier)
        copied.append(
            {
                "action_id": identifier,
                "direction": int(direction),
                "tp_atr": target,
                "sl_atr": stop,
                "horizon": int(horizon),
            }
        )
    return copied


def _mean_and_se(payoffs: np.ndarray, days: np.ndarray) -> tuple[Any, Any, int]:
    n = len(payoffs)
    if n == 0:
        return None, None, 0
    _, inverse = np.unique(days, return_inverse=True)
    date_count = int(inverse.max()) + 1
    mean = payoffs.mean(axis=0, dtype=np.float64)
    if date_count < 2:
        return mean, None, date_count
    # Chronological input requires no full-size copy; shuffled input is still valid.
    if (inverse[1:] < inverse[:-1]).any():
        order = np.argsort(inverse, kind="stable")
        ordered, groups = payoffs[order], inverse[order]
    else:
        ordered, groups = payoffs, inverse
    starts = np.r_[0, np.flatnonzero(np.diff(groups)) + 1]
    counts = np.diff(np.r_[starts, n])
    daily_sums = np.add.reduceat(ordered, starts, axis=0, dtype=np.float64)
    residuals = daily_sums - counts[:, None] * mean[None, :]
    se = np.sqrt(date_count / (date_count - 1) * np.square(residuals).sum(axis=0)) / n
    return mean, se, date_count


def _table(
    payoffs: np.ndarray,
    days: np.ndarray,
    global_mean: np.ndarray | None = None,
    global_se: np.ndarray | None = None,
) -> dict[str, Any]:
    n = len(payoffs)
    mean, se, date_count = _mean_and_se(payoffs, days)
    supported = n >= _MIN_SAMPLE and date_count >= _MIN_DATES
    weight = n / (n + _PSEUDOCOUNT) if global_mean is not None else 1.0
    prediction = (
        None
        if mean is None
        else (weight * mean + (1 - weight) * global_mean if global_mean is not None else mean)
    )
    combined_se = (
        None
        if se is None
        else (weight * se + (1 - weight) * global_se if global_se is not None else se)
    )
    score = None if prediction is None or combined_se is None else prediction - combined_se
    return {
        "sample_size": n,
        "date_count": date_count,
        "supported": supported,
        "mean_net_points": None if mean is None else mean.tolist(),
        "standard_errors": None if se is None else se.tolist(),
        "shrinkage_weight": weight,
        "combined_standard_errors": None if combined_se is None else combined_se.tolist(),
        "predicted_net_points": None if prediction is None else prediction.tolist(),
        "ranking_scores": None if score is None else score.tolist(),
    }


def fit_policy(
    states: np.ndarray,
    days: np.ndarray,
    net_payoffs: np.ndarray,
    *,
    policy_id: str,
    n_states: int,
    actions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Fit shrunk payoff tables on a common complete-45-bar past cohort.

    Rows must contain every action outcome and one ET date per observation.
    Overlap within dates is reflected in the date-cluster SE used for ranking.
    State/day support and a positive feasible score are mandatory for trading.
    """
    state_values, day_values, payoffs = (
        np.asarray(states),
        np.asarray(days),
        np.asarray(net_payoffs),
    )
    normalized_actions = _actions(actions)
    if (
        isinstance(n_states, bool)
        or not isinstance(n_states, Integral)
        or n_states < 1
        or not isinstance(policy_id, str)
        or not policy_id
        or state_values.ndim != 1
        or state_values.dtype.kind not in "iu"
        or day_values.ndim != 1
        or len(day_values) != len(state_values)
        or payoffs.shape != (len(state_values), len(actions))
        or payoffs.dtype.kind not in "fiu"
        or not np.isfinite(payoffs).all()
        or ((state_values < 0) | (state_values >= n_states)).any()
        or any(not isinstance(day, str) or not day.strip() for day in day_values)
    ):
        raise ValueError("invalid states, ET dates, or common-cohort net payoff matrix")
    global_table = _table(payoffs, day_values)
    global_mean = (
        None
        if global_table["mean_net_points"] is None
        else np.asarray(global_table["mean_net_points"])
    )
    global_se = (
        None
        if global_table["standard_errors"] is None
        else np.asarray(global_table["standard_errors"])
    )
    tables = []
    for state in range(n_states):
        mask = state_values == state
        table = _table(payoffs[mask], day_values[mask], global_mean, global_se)
        table["state_id"] = state
        tables.append(table)
    return {
        "schema_version": 2,
        "policy_id": policy_id,
        "n_states": int(n_states),
        "actions": normalized_actions,
        "pseudocount": _PSEUDOCOUNT,
        "minimum_state_samples": _MIN_SAMPLE,
        "minimum_state_dates": _MIN_DATES,
        "ranking_method": "shrunk_mean_minus_linear_weighted_day_cluster_se",
        "global": global_table,
        "states": tables,
    }


def select_action(
    model: dict[str, Any], state: int, max_horizon: int = 45
) -> dict[str, Any] | None:
    """Return the highest positive, feasible forecast, or abstain.

    ``max_horizon`` is known scheduled availability, never future data coverage.
    Ties use H, SL, TP and long-before-short priority. Returned fields are a copy.
    """
    if (
        isinstance(max_horizon, bool)
        or not isinstance(max_horizon, Integral)
        or not 0 <= max_horizon <= 45
    ):
        raise ValueError("max_horizon must be an integer from 0 to 45")
    if model["policy_id"] == "unconditional":
        table = model["global"]
    else:
        if (
            isinstance(state, bool)
            or not isinstance(state, Integral)
            or not 0 <= state < model["n_states"]
        ):
            raise ValueError("state is outside the frozen model")
        table = model["states"][int(state)]
    if not table["supported"] or max_horizon == 0:
        return None
    scores = table["ranking_scores"]
    eligible = [
        i
        for i, action in enumerate(model["actions"])
        if action["horizon"] <= max_horizon and np.isfinite(scores[i]) and scores[i] > 0
    ]
    if not eligible:
        return None
    selected = min(
        eligible,
        key=lambda i: (
            -scores[i],
            model["actions"][i]["horizon"],
            model["actions"][i]["sl_atr"],
            model["actions"][i]["tp_atr"],
            -model["actions"][i]["direction"],
        ),
    )
    return {
        **model["actions"][selected],
        "action_index": selected,
        "predicted_net_points": table["predicted_net_points"][selected],
        "ranking_score": scores[selected],
        "sample_size": table["sample_size"],
        "date_count": table["date_count"],
    }
