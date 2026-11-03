"""Consume one newly completed MNQ CSV bar into the local paper decision journal.

The same file must grow append-only. Earlier rows are checked on every invocation.
No data download, broker connection, order placement, or profit claim is made.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from tools.cloud_exit_student_decision_api import decide as exit_decide
from tools.cloud_student_decision_api import decide as student_decide
from tools.mnq_oracle_prepare import causal_features, load_candles, sha256
from tools.opportunity_research import FEATURES
from tools.paper_decision_service import PaperRecorder
from tools.physics_state import physics_features
from tools.shared_game_state import build_market_states

START = pd.Timestamp("2026-10-30T00:00:00Z")


def _fingerprint(bars: pd.DataFrame) -> str:
    records = [[t.isoformat(), *map(float, row)] for t, row in zip(
        bars.timestamp, bars[["open", "high", "low", "close", "volume"]].to_numpy())]
    raw = json.dumps(records, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def submit(history_csv: Path, state_path: Path, recorder: PaperRecorder, source_id: str) -> dict:
    history_csv, state_path = Path(history_csv), Path(state_path)
    if "2025" in str(history_csv.resolve()) or "2025" in str(state_path.resolve()):
        raise ValueError("Sealed 2025 path forbidden")
    before = sha256(history_csv)
    raw = pd.read_csv(history_csv)
    if list(raw.columns) != ["timestamp_utc", "open", "high", "low", "close", "volume"]:
        raise ValueError("Exact normalized OHLCV columns required")
    times = pd.to_datetime(raw.timestamp_utc, utc=True, errors="raise")
    if not times.is_monotonic_increasing or times.duplicated().any():
        raise ValueError("Feed rows must be strictly ordered and unique")
    if (times < START).any() or (times.dt.year != 2026).any():
        raise ValueError("Only new post-October-2026 bars are permitted")
    bars, audit = load_candles([history_csv])
    if audit["nonminute_rows_rejected_as_partial"] or audit["duplicate_rows_identical_removed"]:
        raise ValueError("Partial or duplicate feed bars forbidden")
    if len(bars) < 61 or len(bars) > 10000:
        raise ValueError("Require 61..10000 same-source bars; start a new audited segment after limit")
    if sha256(history_csv) != before:
        raise ValueError("Feed file changed while reading")
    prior = json.loads(state_path.read_text()) if state_path.exists() else None
    if prior:
        if prior["source_id"] != source_id:
            raise ValueError("Source identity changed")
        if len(bars) != prior["rows"] + 1:
            raise ValueError("Feed must append exactly one completed bar per call")
        if _fingerprint(bars.iloc[:-1]) != prior["prefix_sha256"]:
            raise ValueError("Previously recorded feed bars changed")
        if prior["decision_id"] in recorder.pending:
            if bars.timestamp.iloc[-1] != pd.Timestamp(prior["last_available_at"]):
                recorder.record_gap(prior["decision_id"], source_id,
                                    bars.timestamp.iloc[-1].isoformat())
                raise ValueError("Source gap left paper position unresolved")
            recorder.record_next_open({"decision_id": prior["decision_id"],
                                       "source_id": source_id,
                                       "bar_start": bars.timestamp.iloc[-1].isoformat(),
                                       "open": float(bars.open.iloc[-1])})
    states = build_market_states(bars)
    common = (states.ready & causal_features(bars).feature_ready &
              physics_features(bars, states).physics_ready).to_numpy(bool)
    state = states.iloc[-1].copy()
    state["log1p_atr14_ticks"] = np.log1p(state.atr14 / .25) if pd.notna(state.atr14) else 0.
    feature_values = {name: float(state[name]) for name in FEATURES}
    if not np.isfinite(list(feature_values.values())).all():
        raise ValueError("Nonfinite causal state")
    observation = {"available_at": (bars.timestamp.iloc[-1] + pd.Timedelta(minutes=1)).isoformat(),
                   "ready": bool(common[-1]), "features": feature_values}
    response = recorder.query({"source_id": source_id, "data_sha256": before,
                               "observation": observation})
    if response["event"]["status"] != "accepted":
        return response
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_value = {"source_id": source_id, "rows": len(bars),
                   "prefix_sha256": _fingerprint(bars), "last_available_at": observation["available_at"],
                   "feed_sha256": before, "decision_id": response["event"]["decision_id"]}
    temporary = state_path.with_suffix(state_path.suffix + ".tmp")
    temporary.write_text(json.dumps(state_value, indent=2) + "\n")
    temporary.replace(state_path)
    return response


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history-csv", type=Path, required=True)
    parser.add_argument("--feed-state", type=Path, required=True)
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--student", choices=("ridge_dual_delay", "extra_trees_dual_delay"))
    parser.add_argument("--exit-student", action="store_true")
    args = parser.parse_args()
    if args.student and args.exit_student:
        parser.error("Choose only one student family")
    if not args.student and not args.exit_student:
        parser.error("Choose --student or --exit-student")

    def engine(root, candidate, _fold, observation, *, mode, now):
        return student_decide(root, candidate, observation, mode=mode, now=now)

    if args.exit_student:
        def exit_engine(root, _candidate, _fold, observation, *, mode, now):
            return exit_decide(root, observation, mode=mode, now=now)

        recorder = PaperRecorder(args.journal, args.run, "extra_trees_multihorizon",
                                 "cloud_campaign02", gate_usd=None, engine=exit_engine)
    else:
        recorder = PaperRecorder(args.journal, args.run, args.student, "cloud_campaign01",
                                 gate_usd=None, engine=engine)
    print(json.dumps(submit(args.history_csv, args.feed_state, recorder, args.source_id), indent=2))


if __name__ == "__main__":
    main()
