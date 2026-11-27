"""Event and one-contract policy replay for the frozen reversal-boundary study."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.capacity.barrier import audit
from experiments.capacity.neuron import encode
from experiments.hold_work.sources import load_sources
from experiments.hold_work.metrics import drawdown_bounds

ONE = pd.Timedelta(minutes=1)
HOLD = 5 * ONE


def events(bars, z):
    """Signal at the close of the touch bar, a minute after issuance."""
    boundary = audit(bars, z)
    boundary = boundary.loc[boundary.touched_intrabar].copy()
    times = pd.DatetimeIndex(boundary.issued_bar) + ONE
    touch = bars.loc[times]
    sign = boundary.direction.to_numpy()
    level = boundary.next_close_barrier.to_numpy()
    response = sign * (touch.close.to_numpy() - level)
    boundary['signal'] = times
    boundary['event'] = np.where(response > 0, 'retained', 'crossed')
    boundary['side'] = np.where(response > 0, sign, -sign).astype(int)
    boundary['body'] = np.sign(touch.close.to_numpy() - touch.open.to_numpy()).astype(int)
    boundary['open_beyond'] = sign * (touch.open.to_numpy() - level) < 0
    return boundary.loc[response != 0]


def opportunities(bars, signals, delay):
    """A known clock sets order due times. Gaps cancel entries or force exits."""
    rows = []
    closes = bars.index
    busy_until = {key: closes[0] for key in ('retained','crossed')}
    cutoff = closes[0].normalize() + pd.Timedelta(hours=15,minutes=55)
    for e in signals.itertuples():
        due = e.signal + (1+delay)*ONE
        end = due + HOLD
        if end > cutoff:
            continue
        signal_idx = closes.get_loc(e.signal)
        scheduled = closes[signal_idx+1:signal_idx+2+delay]
        accepts = e.signal >= busy_until[e.event]
        if len(scheduled) != delay+1 or not (scheduled == pd.date_range(e.signal+ONE,due,freq='min')).all():
            if accepts:
                missing = next((stamp for j,stamp in enumerate(scheduled, start=1)
                                if stamp != e.signal+j*ONE), None)
                busy_until[e.event] = missing if missing is not None else closes[-1]
            continue
        start_idx = signal_idx + 1 + delay
        # At a gap during exposure the actual cash flow realizes at the first available open.
        exit_idx = start_idx+1
        while closes[exit_idx] < end and closes[exit_idx]-closes[exit_idx-1] == ONE:
            exit_idx += 1
        finish = closes[exit_idx]
        if accepts:
            busy_until[e.event] = finish
        rows.append(dict(event=e.event, signal=e.signal, issued=e.issued_bar, barrier=e.next_close_barrier,
                         open_beyond=e.open_beyond, entry_time=due, exit_time=finish, side=e.side,
                         body=e.body, entry=bars.open.iat[start_idx], exit=bars.open.iat[exit_idx],
                         accepted=accepts))
    return rows


def equity_path(trades, bars_by_date, side_col, cost):
    realized = 0.0
    events = [(0.,0.,0.,0.,True)]
    for trade in trades.sort_values('entry_time').itertuples():
        side = getattr(trade,side_col) if side_col != 'long' else 1
        if side == 0:
            continue
        tape = bars_by_date[trade.date]
        path = tape.loc[trade.entry_time:trade.exit_time].iloc[:-1]
        base = realized - cost/2
        marks = base + 2*side*(path[['open','low','high','close']].to_numpy()-trade.entry)
        for o,l,h,c in marks:
            events.append((o,min(l,h),max(l,h),c,True))
        pre_exit = base + 2*side*(trade.exit-trade.entry)
        realized = pre_exit - cost/2
        events.extend([(pre_exit,)*4+(False,), (realized,)*4+(True,)])
    return drawdown_bounds(pd.DataFrame(events,columns=['open','low','high','close','is_close']))


def evaluate(raw, days, bar_map):
    summary, daily_records = {}, []
    for (source,delay,event), group in raw.groupby(['source','delay','event']):
        dates = days[source]
        n = len(dates)
        starts = np.random.default_rng(604).integers(n,size=(10000,(n+4)//5,1))
        ix = ((starts+np.arange(5))%n).reshape(10000,-1)[:,:n]
        stats, daily6 = {}, {}
        for name, family, col in [('volume','volume','side'),('body','volume','body'),
                                 ('long','volume','long'),('price','price','side')]:
            observations = group[group.family.eq(family)]
            overlap_gross = 2*(observations.exit-observations.entry)*(observations[col] if col!='long' else 1)
            t = observations.loc[observations.accepted].copy()
            if col == 'body':
                t=t[t.body.ne(0)]
            gross = 2*(t.exit-t.entry)*(t[col] if col!='long' else 1)
            info = dict(n=len(t), opportunities=len(observations), mean_overlapping_gross=overlap_gross.mean(),
                        gross=gross.sum(), net={}, drawdown={}, without_top3_net6=(gross-6).sum()-(gross-6).nlargest(3).clip(lower=0).sum())
            for cost in [3,6,9]:
                net = gross-cost
                info['net'][cost]=net.sum()
                info['drawdown'][cost]=equity_path(t,bar_map,col,cost)
            daily6[name] = (gross-6).groupby(t.date).sum().reindex(dates,fill_value=0).to_numpy()
            for date, value in zip(dates,daily6[name],strict=True):
                daily_records.append(dict(source=source, delay=delay, event=event, policy=name,date=date,net6=value))
            stats[name]=info
        bounds = {}
        for name,control in dict(cash=np.zeros(n),price=daily6['price'],body=daily6['body'],long=daily6['long']).items():
            delta = daily6['volume'] - control
            bounds[name] = dict(mean_daily=delta.mean(),interval95=np.quantile(delta[ix].mean(axis=1),[.025,.975]).tolist())
        summary.setdefault(source,{}).setdefault(int(delay),{})[event] = dict(policies=stats, paired_vs=bounds)
    return summary, pd.DataFrame(daily_records)


def run(market, dest):
    history, external, source = load_sources(market_dir=market)
    records, days, bar_map = [], {}, {}
    for name, frame in [('discovery40',history),('external60',external['MNQ.csv'])]:
        days[name] = []
        for date,bars in frame.groupby(frame.index.date):
            date = str(date)
            days[name].append(date)
            bar_map[date]=bars
            z=encode(bars)
            for family in ('volume','price'):
                brain = z if family=='volume' else z.assign(reservoir=z.price_forecast,stock=z.price_stock)
                signals = events(bars,brain)
                for delay in [0,1]:
                    for row in opportunities(bars,signals,delay):
                        records.append(dict(source=name,date=date,family=family,delay=delay,**row))
    all_rows = pd.DataFrame(records)
    summary,daily = evaluate(all_rows, days, bar_map)
    dest.mkdir(exist_ok=True,parents=True)
    all_rows.to_csv(dest/'events.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    daily.to_csv(dest/'daily.csv',index=False)
    (dest/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    (dest/'source.json').write_text(json.dumps(source,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('market',type=Path)
    p.add_argument('output',type=Path)
    args=p.parse_args()
    run(args.market,args.output)
