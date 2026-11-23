"""Paper replay and portable chart export using the original frozen engine."""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
CORE = HERE.parent
sys.path.insert(0, str(CORE))
from brain import activations
from execution import replay

FRICTION = 6.0
LOSS_TRIGGER = -500.0


def verify_brain():
    frozen = json.loads((CORE / "prospective.json").read_text())["frozen_files"]
    for name in ["brain.py", "area.json", "reservoir.json", "execution.py", "data.py"]:
        if hashlib.sha256((CORE / name).read_bytes()).hexdigest() != frozen[name]:
            raise ValueError(f"Frozen reference changed: {name}")


def simulate_day(bars, score):
    if len(set(bars.index.date)) != 1:
        raise ValueError("replay one New York session at a time")
    base, equity = replay(bars, score, delay=0, cost=FRICTION)
    breaches = equity[equity <= LOSS_TRIGGER]
    if breaches.empty:
        return base, equity, base.copy(), equity.copy(), None
    first = breaches.index[0]
    # Both strategies have identical positions, costs and marks up to first passage.
    # The first breach can therefore be read off the reference equity path causally.
    guarded_score = score.mask(score.index >= first)
    guard, guarded_equity = replay(bars, guarded_score, delay=0, cost=FRICTION)
    forced = (guard.entry_time <= first) & (guard.exit_time == first + pd.Timedelta(minutes=1))
    # If the unguarded policy would have exited here too, retain its original reason.
    same = base[["entry_time","exit_time"]].apply(tuple, axis=1).tolist()
    for i in guard.index[forced]:
        row = guard.loc[i]
        if (row.entry_time, row.exit_time) not in same and row.reason == "signal":
            guard.loc[i, "reason"] = "daily loss"
    return base, equity, guard, guarded_equity, first


def minute(t):
    return int(t.hour * 60 + t.minute)


def ledger(rows):
    return [dict(entry=minute(t.entry_time), exit=minute(t.exit_time), signal=minute(t.signal_time),
                 side=t.side, ep=t.entry, xp=t.exit, net=t.net_usd, reason=t.reason)
            for t in rows.itertuples()]


def max_drawdown(equity):
    path = np.r_[0., equity]
    return float(np.max(np.maximum.accumulate(path) - path))


def day_stats(trades, equity):
    return dict(trades=len(trades), net=float(equity.iloc[-1]), drawdown=max_drawdown(equity),
                cutoff_exits=int((trades.reason == "time").sum()),
                gap_exits=int((trades.reason == "gap").sum()),
                last_exit=None if trades.empty else trades.exit_time.iloc[-1].isoformat())


def run_day(bars):
    a = activations(bars, "reservoir")
    base, equity, guard, guarded_equity, first = simulate_day(bars, a.reservoir)
    day = bars.index[0].date().isoformat()
    candles = [[minute(t.Index), t.open, t.high, t.low, t.close, t.volume,
                None if pd.isna(t.reservoir) else round(t.reservoir, 6), round(t.stock, 6),
                round(t.charge, 6), round(t.signed_release, 6)]
               for t in bars.join(a[["reservoir","stock","charge","signed_release"]]).itertuples()]
    chart = dict(date=day, bars=candles, base=ledger(base), guard=ledger(guard),
                 lock=None if first is None else minute(first))
    stats = dict(date=day, bars=len(bars), missing_daytime_minutes=390-len(bars),
                 loss_trigger_close=None if first is None else (first+pd.Timedelta(minutes=1)).isoformat(),
                 base=day_stats(base,equity), guard=day_stats(guard,guarded_equity), cash_net=0.)
    return chart, stats, base, guard, equity, guarded_equity, a


def save_chart(sessions, target):
    template = (HERE / "viewer.html").read_text()
    if template.count("__REPLAY_DATA__") != 1:
        raise ValueError("missing unique chart data slot")
    payload = json.dumps({"sessions":sessions}, separators=(",",":"), allow_nan=False).replace("<", r"\u003c")
    target.write_text(template.replace("__REPLAY_DATA__", payload))
