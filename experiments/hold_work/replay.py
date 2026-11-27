"""Causal, one-MNQ hold-head replay on expressly exposed sessions.

Models prefixed fixed share the corresponding delay's original entry ledger.
Full policies listen to the untouched reservoir while flat. Both add an
early exit to the original reservoir exit rule. Timestamps label bar starts
(local New York time). Decisions consume finalized bars, and reset trade
memory at each fill. Diagnostic next-open prices are joined after replay.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
import sys

import numpy as np
import pandas as pd

from .circuit import Head

PATH_ORDER = Path(__file__).resolve().parents[1] / "path_order"
sys.path.insert(0, str(PATH_ORDER / "workbench"))
from session import activations, verify_brain
from execution import ENTRY_THRESHOLD_POINTS, FLATTEN_TIME, MINUTE, POINT_VALUE_USD, TRADE_COLUMNS, replay

COST = 6.0
BACKGROUND_SPAN = 32
FIELDS = ["open", "high", "low", "close", "volume"]
POLICIES = ("trail", "price", "volume")


@dataclass(frozen=True)
class Order:
    kind: str
    due: pd.Timestamp
    bar_start: pd.Timestamp
    side: int = 0
    reason: str = ""


@dataclass(frozen=True)
class Position:
    signal_time: pd.Timestamp
    entry_time: pd.Timestamp
    side: int
    entry: float
    entry_scale: float
    entry_forecast: float
    head: Head

    @property
    def side_name(self):
        return "long" if self.side == 1 else "short"

    @property
    def trade_id(self):
        return self.entry_time.isoformat()


def run_day(bars, encoded, delay, policy="original", fixed_signals=None, head_factory=Head):
    """Return trades, open-position activations, and per-bar marked equity.

    Round-trip cost is assessed as half on entry and half on exit. Occupancy
    and completed trade count allow exact repricing of this equity for any
    round-trip cost on the same fills. Entry scale is known before the open.
    """
    if delay not in (0, 1) or policy not in ("original", *POLICIES):
        raise ValueError("unknown policy or execution delay")
    if not bars.index.equals(encoded.index) or len(set(bars.index.date)) != 1:
        raise ValueError("bars and activations must share a single session index")
    if (
        str(bars.index.tz) != "America/New_York" or not bars.index.is_unique
        or not bars.index.is_monotonic_increasing
    ):
        raise ValueError("bars must be ordered, unique and America/New_York")
    scores = encoded.reservoir.to_numpy()
    candles = bars[FIELDS].to_numpy(dtype=float)
    if not np.isfinite(candles).all():
        raise ValueError("non-finite OHLCV")
    expected_lag = (delay + 1) * MINUTE
    contiguous = bars.index.to_series().diff().eq(MINUTE)
    runs = (~contiguous).cumsum().to_numpy()

    def lagged_background(values):
        return values.rename("background").groupby(runs).transform(
            lambda v: v.ewm(span=BACKGROUND_SPAN, adjust=False).mean().shift()
        ).to_numpy()

    prior_volume = lagged_background(bars.volume)
    scales = np.maximum(0.25, lagged_background(bars.high - bars.low))
    gaps = ~contiguous.to_numpy()

    trades, trace, equity = [], [], []
    realized = 0.0
    position = pending = None

    def exit_at(timestamp, price, reason, signal_time=None):
        nonlocal position, realized
        gross = position.side * (price - position.entry) * POINT_VALUE_USD
        realized += gross
        trades.append(dict(
            trade_id=position.trade_id, signal_time=position.signal_time,
            entry_time=position.entry_time, exit_time=timestamp, side=position.side_name,
            entry=position.entry, exit=price, gross_usd=gross, net_usd=gross-COST,
            reason=reason, exit_signal_time=signal_time, entry_scale=position.entry_scale,
            entry_forecast=position.entry_forecast,
        ))
        position = None

    for i, timestamp in enumerate(bars.index):
        open_, high, low, close, volume = candles[i]
        if i and gaps[i]:
            pending = None
            if position is not None:
                exit_at(timestamp, open_, "gap")

        if pending is not None and timestamp == pending.due:
            order, pending = pending, None
            if order.kind == "entry":
                assert position is None and timestamp.time() < FLATTEN_TIME
                signal_index = bars.index.get_loc(order.bar_start)
                scale = scales[i]
                position = Position(
                    order.bar_start, timestamp, order.side, open_, scale,
                    scores[signal_index], head_factory(order.side, open_, scale),
                )
            elif position is not None:
                exit_at(timestamp, open_, order.reason, order.bar_start)

        if timestamp.time() >= FLATTEN_TIME:
            pending = None
            if position is not None:
                exit_at(timestamp, open_, "time")

        due = timestamp + expected_lag
        score = scores[i]
        if position is not None:
            mean = prior_volume[i]
            state = position.head.step(open_, high, low, close, volume, mean)
            eligible = bool(state["eligible"])
            trail = state["trail"]
            price = state["price"]
            weighted = state["volume"]
            trigger = (
                policy == "trail" and trail <= 0
                or policy == "price" and eligible and price <= 0
                or policy == "volume" and eligible and weighted <= 0
            )
            invalid = not np.isfinite(score) or score * position.side <= 0
            discretionary = pending is None and due.time() < FLATTEN_TIME and not invalid
            if pending is None and due.time() < FLATTEN_TIME and (invalid or trigger):
                pending = Order("exit", due, timestamp, reason="signal" if invalid else "hold")
            cells = {key: value for key, value in state.items() if key not in {"price", "volume", "trail", "eligible"}}
            trace.append(dict(
                trade_id=position.trade_id, bar_start=timestamp, side=position.side_name,
                direction=position.side, entry_time=position.entry_time, entry=position.entry,
                entry_scale=position.entry_scale, forecast=score, open=open_, high=high,
                low=low, close=close, volume=volume, prior_mean_volume=mean,
                eligible=eligible, volume_score=weighted, price_score=price, trail_score=trail,
                pending_exit=pending is not None, discretionary=discretionary, **cells,
            ))
        elif pending is None and due.time() < FLATTEN_TIME:
            if fixed_signals is None:
                side = int(np.sign(score)) if np.isfinite(score) and abs(score) > ENTRY_THRESHOLD_POINTS else 0
            else:
                side = fixed_signals.get(timestamp, 0)
            if side:
                pending = Order("entry", due, timestamp, side)

        floating = 0.0 if position is None else position.side * (close - position.entry) * POINT_VALUE_USD
        occupied = int(position is not None)
        equity.append(dict(
            bar_start=timestamp, equity_usd=realized + floating - COST * (len(trades) + occupied / 2),
            gross_equity_usd=realized + floating, completed_trades=len(trades), occupancy=occupied,
            open=open_, high=high, low=low, close=close, volume=volume, forecast=score,
        ))

    if position is not None:
        raise ValueError("session ended with an open position")
    ledger = pd.DataFrame(trades, columns=[
        *TRADE_COLUMNS, "trade_id", "exit_signal_time", "entry_scale", "entry_forecast",
    ])
    traces = pd.DataFrame(trace)
    if len(traces):
        # The label-only executable price must never enter the head. A gap
        # invalidates orders, and 15:55 is independently executed as a flatten.
        future = pd.DataFrame({"next_executable_price": bars.open.shift(-1-delay),
                               "next_executable_time": bars.index.to_series().shift(-1-delay)})
        delta = future.next_executable_time - future.index.to_series()
        executable = delta.eq(expected_lag) & future.next_executable_time.dt.time.le(FLATTEN_TIME)
        future.loc[~executable, "next_executable_price"] = np.nan
        future.loc[~executable, "next_executable_time"] = pd.NaT
        traces = traces.join(future, on="bar_start")
        if policy == "original":
            traces["original_exit_price"] = traces.trade_id.map(ledger.set_index("trade_id").exit)
            traces["original_exit_time"] = traces.trade_id.map(ledger.set_index("trade_id").exit_time)
    return ledger, traces, pd.DataFrame(equity)


def evaluate(frames, head_factory=Head):
    """Replay both delays and enforce identical original forecasts and ledgers."""
    verify_brain()
    rows = {key: [] for key in ("trades", "activations", "equity")}
    entry_fields = ["signal_time", "entry_time", "side", "entry"]

    def append(result, model):
        for key, frame in zip(rows, result, strict=True):
            if len(frame):
                rows[key].append(frame.assign(panel=panel, date=str(date), delay=delay, model=model))

    for panel, frame in frames.items():
        for date, bars in frame.groupby(frame.index.date):
            encoded = activations(bars, "reservoir")
            for delay in (0, 1):
                original = run_day(bars, encoded, delay, head_factory=head_factory)
                expected, marked = replay(bars, encoded.reservoir, delay=delay, cost=COST)
                pd.testing.assert_frame_equal(expected, original[0][TRADE_COLUMNS], check_dtype=False)
                np.testing.assert_array_equal(marked.to_numpy(), original[2].equity_usd.to_numpy())
                append(original, "original")
                fixed = {t.signal_time: 1 if t.side == "long" else -1 for t in expected.itertuples()}
                for policy in POLICIES:
                    group = run_day(bars, encoded, delay, policy, fixed_signals=fixed, head_factory=head_factory)
                    pd.testing.assert_frame_equal(expected[entry_fields], group[0][entry_fields], check_dtype=False)
                    assert (group[0].exit_time <= expected.exit_time).all()
                    append(group, f"fixed_{policy}")
                    append(run_day(bars, encoded, delay, policy, head_factory=head_factory), f"full_{policy}")
    return {key: pd.concat(parts, ignore_index=True) for key, parts in rows.items()}


def verify_archived(trades):
    """Compare all archived per-trade economics before publishing replays."""
    archive = PATH_ORDER.parent / "reservoir_lab/response_evidence/results"
    for track in ("discovery", "external"):
        reference = pd.read_csv(archive / track / "trades.csv.gz")
        reference = reference.loc[reference.model.eq("original"), ["panel", *TRADE_COLUMNS]]
        for key in ("signal_time", "entry_time", "exit_time"):
            reference[key] = pd.to_datetime(reference[key], utc=True).dt.tz_convert("America/New_York")
        candidate = trades.loc[
            trades.delay.eq(0) & trades.model.eq("original") & trades.panel.isin(reference.panel),
            reference.columns,
        ]
        if not len(candidate):
            continue
        order = ["panel", "entry_time"]
        pd.testing.assert_frame_equal(
            reference.sort_values(order).reset_index(drop=True),
            candidate.sort_values(order).reset_index(drop=True),
            check_dtype=False,
        )
        print(f"{track}: verified {len(reference)} archived original fills")

def write_outputs(rows, out):
    out.mkdir(parents=True, exist_ok=True)
    for name, frame in rows.items():
        frame.to_csv(out / f"{name}.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})


def main():
    from .sources import load_sources

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="exposed source directory")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    discovery, external, provenance = load_sources(root, args.source)
    frames = {panel: group[FIELDS] for panel, group in discovery.groupby("panel", sort=False)}
    frames["external"] = external["MNQ.csv"][FIELDS]
    rows = evaluate(frames)
    verify_archived(rows["trades"])
    write_outputs(rows, args.output)
    (args.output / "source.json").write_text(json.dumps(provenance, indent=2) + "\n")


if __name__ == "__main__":
    main()
