"""Create a self-contained chart of the frozen fixed-entry counterfactuals."""
import argparse
from pathlib import Path

import pandas as pd

from experiments.hold_work.metrics import _svg_series


def run(replay, output):
    t = pd.read_csv(replay/'trades.csv.gz')
    t = t[t.delay.eq(0)]
    x = t[t.model.eq('original')].merge(t[t.model.eq('fixed_volume_exit')], on=['trade_id','date','side'],
                                         suffixes=('_o','_e'), validate='one_to_one')
    x['delta'] = x.gross_usd_e-x.gross_usd_o
    winners = x[x.gross_usd_o>3]
    a = pd.read_csv(replay/'activations.csv.gz')
    a = a[a.delay.eq(0)&a.model.eq('original')]
    levels = pd.read_csv(output/'barriers.csv.gz')
    levels['issued_bar'] = pd.to_datetime(levels.issued_bar,utc=True).dt.tz_convert('America/New_York')
    cases = [('Largest saving',x.loc[x.delta.idxmax()]),('Largest damaged winner',winners.loc[winners.delta.idxmin()]),
             ('November 19 long',x[x.entry_time_o.str.startswith('2026-11-19 10:45')].iloc[0])]
    html = ['<!doctype html><meta charset="utf-8"><title>Reservoir capacity cases</title>',
            '<style>body{max-width:920px;margin:32px auto;font:16px system-ui;color:#172d45}svg{width:100%;height:auto}svg text{font:12px system-ui}section{margin:40px 0}</style>',
            '<h1>Reservoir reversal capacity</h1><p>Identical original entries, one MNQ, next-open fills and $3 round-trip friction. Times are New York. Each gray dot is a reachable next-close reversal level issued one bar earlier. Hover over dots and fills for details. The hold lines show experimental score margins.</p>']
    for name,row in cases:
        b=a[a.trade_id.eq(row.trade_id)].copy()
        time=pd.to_datetime(b.bar_start,utc=True).dt.tz_convert('America/New_York')
        entry=pd.Timestamp(row.entry_time_o)
        orig=pd.Timestamp(row.exit_time_o)
        edit=pd.Timestamp(row.exit_time_e)
        barrier=levels[levels.issued_bar.between(entry,orig-pd.Timedelta(minutes=1))&
                       levels.direction.eq(1 if row.side=='long' else -1)&levels.reachable]
        markers=[(v.issued_bar+pd.Timedelta(minutes=1),v.next_close_barrier,'#8495a3','Next-close reversal level') for v in barrier.itertuples()]
        markers.extend([(entry,row.entry_o,'#166534','Entry'),(orig,row.exit_o,'#b83a39','Original exit'),
                        (edit,row.exit_e,'#5937ac','Capacity exit')])
        html.extend([f'<section><h2>{name} · {row.date}</h2><p>{row.side.title()} at {entry:%H:%M}. Original net ${row.gross_usd_o-3:,.2f}; capacity net ${row.gross_usd_e-3:,.2f}. Change ${row.delta:,.2f}.</p>',
                     _svg_series('MNQ price',[('Minute close','#263f5b',list(zip(time,b.close)))],markers),
                     _svg_series('Forecast and position-relative margins',[
                       ('Forecast (pts)','#263f5b',list(zip(time,b.reservoir))),
                       ('Hold value (pts), volume','#5937ac',list(zip(time,b.hold_score))),
                       ('Hold value (pts), price','#995000',list(zip(time,b.price_score)))]),'</section>'])
    (output/'cases.html').write_text('\n'.join(html)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('replay',type=Path)
    p.add_argument('output',type=Path)
    a=p.parse_args()
    run(a.replay,a.output)
