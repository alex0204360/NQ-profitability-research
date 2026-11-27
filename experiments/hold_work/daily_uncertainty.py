"""Paired five-session-block uncertainty for the full-policy comparison."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def evaluate(ledger, destination):
    t = pd.read_csv(ledger)
    t['group'] = np.where(t.panel == 'external', 'external60', 'discovery40')
    result = []
    for (group, delay), part in t.groupby(['group', 'delay']):
        dates = sorted(part.date.unique())
        n = len(dates)
        if n != (60 if group == 'external60' else 40):
            raise ValueError('expected full date grid')
        starts = np.random.default_rng(604).integers(n, size=(10000, (n+4)//5, 1))
        indexes = ((starts + np.arange(5)) % n).reshape(10000, -1)[:, :n]
        for cost in [3, 6, 9]:
            daily = part.assign(net=part.gross_usd-cost).pivot_table(
                values='net', index='date', columns='model', aggfunc='sum', fill_value=0).loc[dates]
            daily['cash'] = 0
            for mode, controls in [('fixed_volume', ['original', 'fixed_price', 'fixed_trail']),
                                   ('full_volume', ['cash', 'original', 'full_price', 'full_trail'])]:
                for control in controls:
                    delta = (daily[mode] - daily[control]).to_numpy()
                    ci = np.quantile(delta[indexes].mean(axis=1), [.025, .975])
                    result.append(dict(group=group, delay=int(delay), cost=cost, policy=mode,
                                       comparator=control, sessions=n, total_usd=float(delta.sum()),
                                       mean_daily_usd=float(delta.mean()), interval95_daily=ci.tolist()))
    destination.write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trades', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    evaluate(args.trades, args.destination)
