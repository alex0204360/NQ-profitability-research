"""Post-decision attribution on identical trades. No outputs feed the models."""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from score import prepare_panels
from circuit import encode
from execution import FLATTEN_TIME, POINT_VALUE_USD, replay


def attribution(bars, states, model):
    signal = states[model]
    trades, _ = replay(bars, signal, delay=0, cost=3.)
    one_minute = pd.Timedelta(minutes=1)
    entry = pd.DatetimeIndex(trades.entry_time)
    exit_at = pd.DatetimeIndex(trades.exit_time)
    side = np.where(trades.side == "long", 1, -1)
    entry_late = entry + one_minute
    # The counterfactual shifts signal exits only. 15:55 flatten remains fixed.
    exit_late = exit_at.where(trades.reason == "time", exit_at + one_minute)
    usable = ((trades.reason != "gap").to_numpy() & (entry_late.time < FLATTEN_TIME)
              & (exit_late.time <= FLATTEN_TIME) & (exit_late > entry_late)
              & entry_late.isin(bars.index) & exit_late.isin(bars.index))
    buy_later = side * (trades.entry.to_numpy() - bars.open.reindex(entry_late).to_numpy()) * POINT_VALUE_USD
    sell_later = side * (bars.open.reindex(exit_late).to_numpy() - trades.exit.to_numpy()) * POINT_VALUE_USD
    next_close_score = signal.reindex(pd.DatetimeIndex(trades.signal_time) + one_minute).to_numpy()
    return dict(immediate_trades=len(trades), stale_at_next_close=int((side * next_close_score <= 0).sum()),
                matched_trades=int(usable.sum()), same_trade_immediate_gross=trades.gross_usd[usable].sum(),
                entry_delay_effect_usd=buy_later[usable].sum(), exit_delay_effect_usd=sell_later[usable].sum(),
                same_trade_both_late_gross=(trades.gross_usd.to_numpy() + buy_later + sell_later)[usable].sum())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discovery", type=Path, required=True)
    parser.add_argument("--november-dir", type=Path)
    parser.add_argument("--reissued", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    panels, _ = prepare_panels(args.discovery, args.november_dir, args.reissued)
    rows = []
    for name, bars in panels.items():
        if name in {"combined34", "november_all"}:
            continue
        states = encode(bars)
        for model in ["return_map", "confirmed"]:
            rows.append(dict(panel=name, model=model, bars=len(bars),
                             deposits=int((states.charge > 0).sum()),
                             **states[["departures", "contacts", "crossed_at_contact", "confirmations"]].sum().astype(int).to_dict(),
                             **attribution(bars, states, model)))
    pd.DataFrame(rows).to_csv(args.out, index=False)
