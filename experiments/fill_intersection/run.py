"""Reproduce exploratory economics and inspect matured-address forecasts."""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from neuron import BLOCK, encode

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'return_map'))
from score import prepare_panels, checked_window, replay, describe, paired


def run(bars, out, encoder=encode):
    out.mkdir(parents=True, exist_ok=True)
    state = encoder(bars)
    state.to_csv(out / 'activations.csv.gz', compression={'method':'gzip','mtime':0})
    valid = state.cell >= 0
    time = bars.index.to_series()
    valid &= time.shift(-BLOCK-2) - time == pd.Timedelta(minutes=BLOCK+2)
    probes = state[valid].copy()
    for lag in [1, 2]:
        probes[f'forward{lag}'] = (bars.open.shift(-BLOCK-lag) - bars.open.shift(-lag)).loc[valid]
    probes.to_csv(out / 'probes.csv')
    summaries, days, ledgers = [], [], []
    for panel, b in [('all', bars), *[(str(m), g) for m,g in bars.groupby(bars.index.month)]]:
        for delay in [0, 1]:
            for fee in [3, 6]:
                for head in state.columns[-3:]:
                    trades, marks = replay(b, state.loc[b.index, head], delay, fee)
                    s, daily = describe(trades, marks, np.unique(b.index.date))
                    s.pop('by_side')
                    s.update(panel=panel, delay=delay, cost=fee, head=head,
                             less_top5=s['net']-trades.net_usd.nlargest(5).sum() if len(trades) else 0,
                             daily_mean_block95=paired(daily, 0)['block95'])
                    summaries.append(s)
                    if panel == 'all':
                        days.append(daily.rename('net').rename_axis('date').reset_index().assign(head=head,delay=delay,cost=fee))
                        ledgers.append(trades.assign(head=head,delay=delay,cost=fee))
    pd.concat(days).to_csv(out/'daily.csv',index=False)
    pd.concat(ledgers).to_csv(out/'trades.csv',index=False)
    pd.DataFrame(summaries).to_csv(out/'summary.csv',index=False)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--november', type=Path)
    p.add_argument('--extensions-only', action='store_true')
    p.add_argument('--erasure', action='store_true')
    p.add_argument('--discovery', type=Path, default=Path('/tmp/mnq-exposed/discovery'))
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    panels, _ = prepare_panels(a.discovery, None if a.extensions_only else a.november, bool(a.november))
    bars = panels.get('combined34', panels['discovery'])
    if a.extensions_only:
        bars = pd.concat([bars, *[checked_window(a.november / k / 'bars.csv', k, True)[0]
                                  for k in ('extension1', 'extension2')]])
    from erasure import encode as erase
    run(bars, a.out, erase if a.erasure else encode)
