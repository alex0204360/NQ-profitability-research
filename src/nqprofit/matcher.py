"""Feed-agnostic serving of frozen, explicitly qualified research policies.

Inputs are completed one-minute OHLCV bars with timezone-aware interval-start
timestamps. Recommendations contain offsets from the next open, never a claimed
fill price. The caller supplies whether its position is flat and, optionally, the
next known scheduled close. No market feed or order connection is provided.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from numbers import Integral
from pathlib import Path

import numpy as np
import pandas as pd

from .execution import MAX_HORIZON, MINUTE, TICK_SIZE, quantize_distance
from .features import REQUIRED_COLUMNS, WARMUP_PRIOR_BARS, compute_features
from .policies import encode_states, select_action


def _read_json(path: Path) -> tuple[dict, str]:
    raw = path.read_bytes()
    document = json.loads(raw)
    if not isinstance(document, dict):
        raise ValueError(f"Expected a JSON object in {path.name}")
    return document, hashlib.sha256(raw).hexdigest()


def _project_file(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ValueError("Model and encoder paths must be nonempty project-relative paths")
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Model and encoder paths must remain relative to the project")
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("Model or encoder path escapes the project")
    return resolved


def _validate_bars(bars: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(bars, pd.DataFrame):
        raise TypeError("bars must be a pandas DataFrame")
    missing = set(REQUIRED_COLUMNS) - set(bars.columns)
    if missing:
        raise ValueError(f"Missing standard OHLCV columns: {sorted(missing)}")
    try:
        timestamps = pd.DatetimeIndex(bars["timestamp"])
    except (TypeError, ValueError) as exc:
        raise ValueError("timestamp must be timezone-aware") from exc
    if timestamps.tz is None or timestamps.hasnans:
        raise ValueError("timestamp must be timezone-aware and nonmissing")
    timestamps = timestamps.tz_convert("UTC").as_unit("ns")
    if timestamps.has_duplicates or not timestamps.is_monotonic_increasing:
        raise ValueError("timestamp must be strictly increasing without duplicates")
    if np.any(timestamps.asi8 % MINUTE.value):
        raise ValueError("timestamp must identify an exact whole-minute bar start")
    try:
        prices = bars[list(REQUIRED_COLUMNS[1:])].to_numpy(dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("OHLCV values must be finite numbers") from exc
    if not np.isfinite(prices).all():
        raise ValueError("OHLCV values must be finite")
    if (prices[:, :4] <= 0).any() or (prices[:, 4] < 0).any():
        raise ValueError("OHLC must be positive and volume nonnegative")
    if len(prices):
        open_, high, low, close, _ = prices.T
        if (
            (high < np.maximum.reduce([open_, close, low]))
            | (low > np.minimum.reduce([open_, close, high]))
        ).any():
            raise ValueError("Inconsistent OHLC geometry")
        ticks = prices[:, :4] / TICK_SIZE
        if not np.isclose(ticks, np.rint(ticks), rtol=0, atol=1e-8).all():
            raise ValueError("OHLC prices must align with the 0.25-point NQ tick")
    result = bars.copy()
    result["timestamp"] = timestamps
    return result


def _feasible_horizon(entry_time: pd.Timestamp, known_close) -> int:
    if known_close is None:
        return MAX_HORIZON
    try:
        boundary = pd.Timestamp(known_close)
    except (TypeError, ValueError) as exc:
        raise ValueError("known_close must be a timezone-aware timestamp") from exc
    if pd.isna(boundary) or boundary.tzinfo is None:
        raise ValueError("known_close must be a finite timezone-aware timestamp")
    remaining = int((boundary.tz_convert("UTC") - entry_time) // MINUTE)
    return min(MAX_HORIZON, max(0, remaining))


class PolicyMatcher:
    """Load schema-2 policy models and match completed standard OHLCV bars.

    Library entries name model and encoder JSON files relative to the project
    root, defined as ``library_path.parent.parent`` (normally ``patterns/library.json``).
    Default matching uses only ``qualified_policies``. ``diagnostic=True`` also
    exposes explicitly unqualified diagnostic policies for testing mechanics.

    ``match`` is stateless; ``update`` maintains at most 61 bars. Both use the same
    feature and policy functions. ``flat=False`` suppresses recommendations but
    still allows ``update`` to keep history current. No position is inferred or
    sent to a broker. All timestamps in output are UTC ISO-8601 strings.
    """

    def __init__(self, library_path: str | Path, diagnostic: bool = False):
        self.library_path = Path(library_path).resolve()
        self.project_root = self.library_path.parent.parent
        document, self.library_sha256 = _read_json(self.library_path)
        if document.get("schema_version") != 2:
            raise ValueError("Only library schema_version 2 is supported")
        self._loaded: list[dict] = []
        self._buffer: list[dict] = []
        seen: set[str] = set()
        for group, qualified in (("qualified_policies", True), ("diagnostic_policies", False)):
            entries = document.get(group, [])
            if not isinstance(entries, list):
                raise ValueError(f"{group} must be a list")
            for entry in entries:
                if not isinstance(entry, dict):
                    raise ValueError("Every policy entry must be an object")
                policy_id = entry.get("policy_id")
                if not isinstance(policy_id, str) or not policy_id:
                    raise ValueError("Every policy requires a nonempty policy_id")
                if policy_id in seen:
                    raise ValueError(f"duplicate policy_id: {policy_id}")
                seen.add(policy_id)
                if entry.get("qualified") is not qualified:
                    raise ValueError(f"Policy qualification disagrees with {group}")
                if not isinstance(entry.get("status"), str) or not entry["status"]:
                    raise ValueError("Policy status must be a nonempty string")
                if not isinstance(entry.get("stats"), dict):
                    raise ValueError("Policy historical stats must be an object")
                if not qualified and not diagnostic:
                    continue
                model_path = _project_file(self.project_root, entry.get("model_path"))
                encoder_path = _project_file(self.project_root, entry.get("encoder_path"))
                model, model_hash = _read_json(model_path)
                encoder, encoder_hash = _read_json(encoder_path)
                if (
                    entry.get("model_sha256") != model_hash
                    or entry.get("encoder_sha256") != encoder_hash
                ):
                    raise ValueError("Model or encoder hash differs from its library statistics")
                if (
                    model.get("policy_id") != policy_id
                    or encoder.get("family") != policy_id
                    or model.get("n_states") != encoder.get("n_states")
                ):
                    raise ValueError("Model/encoder identity differs from its library policy")
                self._loaded.append(
                    {
                        "entry": copy.deepcopy(entry),
                        "model": model,
                        "encoder": encoder,
                        "provenance": {
                            "model_path": entry["model_path"],
                            "encoder_path": entry["encoder_path"],
                            "model_sha256": model_hash,
                            "encoder_sha256": encoder_hash,
                            "library_sha256": self.library_sha256,
                        },
                    }
                )

    def match(self, bars: pd.DataFrame, flat: bool = True, known_close=None) -> list[dict]:
        """Return current recommendations; abstain during warmup or infeasibility.

        ``known_close`` is a caller-supplied scheduled close. Remaining fractional
        minutes are floored. Without it, only the hard 45-minute cap is enforced,
        and output explicitly reports that no closure boundary was supplied.
        """
        frame = _validate_bars(bars)
        if not flat or len(frame) < WARMUP_PRIOR_BARS + 1:
            return []
        decision_time = frame["timestamp"].iloc[-1] + MINUTE
        if decision_time.minute % 5:
            return []
        max_horizon = _feasible_horizon(decision_time, known_close)
        if max_horizon < 1 or not self._loaded:
            return []
        features = compute_features(frame.iloc[-(WARMUP_PRIOR_BARS + 1) :]).iloc[-1:]
        if not bool(features["valid"].iloc[0]) or features["atr14"].iloc[0] <= 0:
            return []
        timestamps = pd.DatetimeIndex([decision_time])
        result = []
        for loaded in self._loaded:
            state = int(encode_states(features, timestamps, loaded["encoder"])[0])
            action = select_action(loaded["model"], state, max_horizon=max_horizon)
            if action is None:
                continue
            horizon = action.get("horizon")
            if (
                isinstance(horizon, (bool, np.bool_))
                or not isinstance(horizon, Integral)
                or not 1 <= horizon <= max_horizon
            ):
                raise ValueError("Selected action has an invalid or infeasible holding horizon")
            direction = action.get("direction")
            if direction not in (1, -1) or isinstance(direction, (bool, np.bool_)):
                raise ValueError("Selected direction must be +1 (long) or -1 (short)")
            predicted = float(action["predicted_net_points"])
            score = float(action["ranking_score"])
            if not np.isfinite([predicted, score]).all() or score <= 0:
                raise ValueError("Selected action must have a positive finite ranking score")
            entry = loaded["entry"]
            atr = float(features["atr14"].iloc[0])
            result.append(
                {
                    "policy_id": entry["policy_id"],
                    "status": entry["status"],
                    "qualified": entry["qualified"],
                    "state": state,
                    "direction": "long" if direction == 1 else "short",
                    "action_id": action["action_id"],
                    "tp_points": quantize_distance(atr, action["tp_atr"]),
                    "sl_points": quantize_distance(atr, action["sl_atr"]),
                    "horizon": int(horizon),
                    "decision_time": decision_time.isoformat(),
                    "intended_entry_time": decision_time.isoformat(),
                    "predicted_net_points": predicted,
                    "ranking_score": score,
                    "known_close_supplied": known_close is not None,
                    "calendar_feasibility": "checked"
                    if known_close is not None
                    else "not_supplied",
                    "historical_stats": copy.deepcopy(entry["stats"]),
                    "model_provenance": copy.deepcopy(loaded["provenance"]),
                }
            )
        return result

    def update(self, bar: Mapping, flat: bool = True, known_close=None) -> list[dict]:
        """Append one completed bar, retaining 61 bars, then apply ``match``.

        Duplicate or out-of-order observations raise without changing the buffer.
        Gap or optional contract/segment changes restart feature warmup through the
        same causal feature logic used by batch matching.
        """
        if not isinstance(bar, (Mapping, pd.Series)):
            raise TypeError("bar must be a mapping of standard OHLCV fields")
        candidate = pd.DataFrame([*self._buffer, dict(bar)])
        validated = _validate_bars(candidate)
        result = self.match(validated, flat=flat, known_close=known_close)
        self._buffer = validated.tail(WARMUP_PRIOR_BARS + 1).to_dict("records")
        return result
