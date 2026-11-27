"""Replay the frozen same-minute historical volume placebo."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .replay import (
    COST, FIELDS, TRADE_COLUMNS, activations, replay, run_day, verify_archived,
    verify_brain,
)
from .sources import _load_external


def interval(difference):
    """Compute the registered circular five-session block interval for mean USD."""
    rng = np.random.default_rng(2711)
    n = len(difference)
    starts = rng.integers(0, n, size=(10_000, (n+4)//5))
    indices = ((starts[..., None] + np.arange(5)) % n).reshape(10_000, -1)[:, :n]
    return np.quantile(difference[indices].mean(axis=1), [0.025, 0.975]).tolist()


def run(source_dir, out):
    verify_brain()
    root = Path(__file__).resolve().parents[2]
    external, source = _load_external(root, source_dir)
    frame = external["MNQ.csv"][FIELDS]
    sessions = list(frame.groupby(frame.index.date))
    if len(sessions) != 60:
        raise ValueError("expected the 60 registered external sessions")
    volume = []
    minute_grid = pd.date_range("2026-01-20 09:30", periods=390, freq="min").time
    for _, bars in sessions:
        if not np.array_equal(bars.index.time, minute_grid):
            raise ValueError("same-time donor alignment requires the complete RTH minute grid")
        volume.append(bars.volume.to_numpy(copy=True))

    ledger, daily, originals = [], [], []

    def record(date, delay, mode, donor, bars, trades, equity):
        label = f"lag{donor}" if isinstance(donor, int) else donor
        donor_date = sessions[i-donor][0].isoformat() if isinstance(donor, int) else ""
        keys = dict(date=date.isoformat(), delay=delay, mode=mode, model=label, donor_date=donor_date)
        ledger.append(trades.assign(**keys))
        occupied = int(equity.occupancy.sum())
        assert occupied <= len(bars)
        daily.append(dict(
            **keys, trades=len(trades), occupied_minutes=occupied,
            gross_usd=float(trades.gross_usd.sum()), net_usd=float(trades.net_usd.sum()),
        ))

    for i, (date, bars) in enumerate(sessions):
        encoded = activations(bars, "reservoir")
        for delay in (0, 1):
            baseline, marks = replay(bars, encoded.reservoir, delay=delay, cost=COST)
            originals.append(baseline.assign(panel="external", delay=delay, model="original"))
            if i < 5:
                continue
            fixed = {t.signal_time: 1 if t.side == "long" else -1 for t in baseline.itertuples()}
            parent, _, equity = run_day(bars, encoded, delay)
            pd.testing.assert_frame_equal(parent[TRADE_COLUMNS], baseline, check_dtype=False)
            np.testing.assert_array_equal(equity.equity_usd, marks)
            entry_cols = ["signal_time", "entry_time", "entry", "side", "entry_scale", "entry_forecast"]
            for mode, signals in (("fixed", fixed), ("full", None)):
                record(date, delay, mode, "original", bars, parent, equity)
                for donor in ("actual", "unit", 1, 2, 3, 4, 5):
                    candidate_bars = bars.assign(volume=volume[i-donor]) if isinstance(donor, int) else bars
                    policy = "price" if donor == "unit" else "volume"
                    trades, _, marked = run_day(candidate_bars, encoded, delay, policy, fixed_signals=signals)
                    if mode == "fixed":
                        pd.testing.assert_frame_equal(parent[entry_cols], trades[entry_cols], check_dtype=False)
                        assert (trades.exit_time <= parent.exit_time).all()
                    record(date, delay, mode, donor, bars, trades, marked)

    verify_archived(pd.concat(originals, ignore_index=True))
    trades = pd.concat(ledger, ignore_index=True)
    day = pd.DataFrame(daily)
    donors = [f"lag{i}" for i in range(1, 6)]
    report = {}
    for (delay, mode), group in day.groupby(["delay", "mode"], sort=True):
        for cost in (3, 6, 9):
            rows = group.assign(net=group.gross_usd-cost*group.trades)
            paired = rows.pivot(index="date", columns="model", values="net").sort_index()
            assert len(paired) == 55 and not paired.isna().any().any()
            difference = (paired.actual - paired[donors].mean(axis=1)).to_numpy()
            report.setdefault(mode, {}).setdefault(str(delay), {})[str(cost)] = dict(
                totals_usd=paired.sum().to_dict(),
                trade_counts=rows.groupby("model").trades.sum().to_dict(),
                occupied_minutes=rows.groupby("model").occupied_minutes.sum().to_dict(),
                donor_mean_total_usd=float(paired[donors].sum().mean()),
                actual_minus_donor_mean_total_usd=float(difference.sum()),
                actual_minus_donor_mean_daily_usd=float(difference.mean()),
                actual_minus_donor_mean_daily_ci95_usd=interval(difference),
            )

    out.mkdir(parents=True, exist_ok=True)
    source.update(
        study_freeze="d93bc5f", first_target=sessions[5][0].isoformat(),
        last_target=sessions[-1][0].isoformat(),
        replay_sha256=hashlib.sha256(Path(__file__).with_name("replay.py").read_bytes()).hexdigest(),
    )
    (out/"source.json").write_text(json.dumps(source, indent=2)+"\n")
    (out/"results.json").write_text(json.dumps(report, indent=2)+"\n")
    day.to_csv(out/"daily.csv", index=False)
    trades.to_csv(out/"trades.csv.gz", index=False, compression={"method":"gzip","mtime":0})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    run(args.source, args.output)


if __name__ == "__main__":
    main()
