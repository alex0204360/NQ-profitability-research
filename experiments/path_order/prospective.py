"""Replay the single predeclared prospective window on audited individual-contract bars."""
import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from data import regular_hours
from evaluate import evaluate


def load_panel(path, digest, spec):
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError("source checksum differs from the independent capture receipt")
    raw = pd.read_csv(path)
    local = pd.to_datetime(raw.timestamp_utc, utc=True).dt.tz_convert("America/New_York")
    days = local.dt.strftime("%Y-%m-%d")
    raw = raw.loc[days.isin(spec["sessions"])].copy()
    bars = regular_hours(raw, min(spec["sessions"]), max(spec["sessions"]))
    indexed_contract = raw.set_index(pd.DatetimeIndex(pd.to_datetime(raw.timestamp_utc, utc=True)))
    for day, contract in spec["sessions"].items():
        session = bars[bars.index.strftime("%Y-%m-%d") == day]
        if session.empty:
            raise ValueError(f"missing registered session {day}")
        if not indexed_contract.loc[session.index, "contract"].eq(contract).all():
            raise ValueError(f"contract mismatch on {day}")
    return bars


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("csv", type=Path, help="canonical UTC minute-start OHLCV plus contract")
    p.add_argument("--sha256", required=True, help="from independent immutable source receipt")
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    spec = json.loads(Path(__file__).with_name("prospective.json").read_text())
    for name, expected in spec["frozen_files"].items():
        if hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"prospective freeze mismatch: {name}")
    bars = load_panel(args.csv, args.sha256, spec)
    evaluate(bars, ["area", "reservoir", "volume_control"], args.out)
    report = json.loads((args.out / "results.json").read_text())
    checks = {"all_regular_minutes_observed": len(bars) == 390 * len(spec["sessions"]),
              "exchange_tick_grid": report["off_tick_ohlc_rows"] == 0}
    for delay in [0, 1]:
        z = report["replays"][f"delay{delay}_cost6"]["reservoir"]
        checks[f"delay{delay}"] = dict(enough_trades=z["trades"] >= 50, positive_net=z["net"] > 0,
            no_gap_fills=z["gap_trades"] == 0,
            positive_lower_bounds=all(z["daily_delta"][k]["block95"][0] > 0
                                      for k in ["cash","trend","volume_control"]),
            within_research_drawdown_screen=z["drawdown"] < 1500)
    record = {"input_sha256": args.sha256, "candidate": "reservoir", "checks": checks,
              "source_and_executable_fill_audit": "requires independent verification"}
    (args.out / "prospective-checks.json").write_text(json.dumps(record, indent=2) + "\n")
