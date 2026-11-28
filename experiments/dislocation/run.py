"""Pinned two-observer dislocation replay with an executable-latency decomposition."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from experiments.hold_work.sources import load_sources
from experiments.hold_work.metrics import drawdown_bounds
from .neuron import encode

NQ_HASH = '583cd788b035c4b5ca612f8bb0e3e366d627348851c04d68bca295a5db116f61'
POLICIES = ('volume','equal','peer','micro_reversion')


def day_frame(b,p):
    f = encode(b,p)
    o = b.open
    f['close_to_open'] = o.shift(-1) - b.close
    f['peer_close_to_open'] = p.open.shift(-1) - p.close
    f['spread_convergence'] = f.close_to_open - f.peer_close_to_open
    for delay in (0,1):
        step = 1+delay
        f['open_'+str(delay)] = o.shift(-step)
        f['high_'+str(delay)] = b.high.shift(-step)
        f['low_'+str(delay)] = b.low.shift(-step)
        f['close_'+str(delay)] = b.close.shift(-step)
        f['exit_'+str(delay)] = o.shift(-step-1)
        f['paid_'+str(delay)] = o.shift(-step-1)-o.shift(-step)
        f['basis_paid_'+str(delay)] = (p.open-o).shift(-step) - (p.open-o).shift(-step-1)
    times = f.index + pd.Timedelta(minutes=3)
    return f.loc[f.volume.notna() & (times <= f.index.normalize()+pd.Timedelta(hours=15,minutes=55))]


def marks(t, cost):
    cash=0.
    events=[(0.,0.,0.,0.,True)]
    for row in t.itertuples():
        base=cash-cost/2
        high=base+2*row.side*(row.high-row.entry)
        low=base+2*row.side*(row.low-row.entry)
        close=base+2*row.side*(row.close-row.entry)
        events.append((base,min(low,high),max(low,high),close,True))
        pre=base+row.gross
        cash=pre-cost/2
        events.extend([(pre,)*4+(False,), (cash,)*4+(True,)])
    return drawdown_bounds(pd.DataFrame(events,columns=['open','low','high','close','is_close']))


def trades(frame, model, delay):
    step = pd.Timedelta(minutes=1+delay)
    suffix = str(delay)
    selected=frame[frame[model].abs()>3.]
    busy=None
    rows=[]
    for stamp,row in selected.iterrows():
        if busy is not None and stamp<busy:
            continue
        entry=stamp+step
        busy=entry+pd.Timedelta(minutes=1)
        side=int(np.sign(row[model]))
        rows.append([stamp,stamp.date().isoformat(),model,delay,side,row[model],entry,busy,
                     *(row[k+'_'+suffix] for k in ['open','high','low','close','exit']),
                     2*side*row['paid_'+suffix]])
    return pd.DataFrame(rows,columns=['signal','date','model','delay','side','score','entry_time','exit_time',
                                      'entry','high','low','close','exit','gross'])


def correlation(a,b):
    if len(a)<2 or a.nunique()<2 or b.nunique()<2:
        return None
    return float(spearmanr(a,b).statistic)


def run(market,dest):
    _, micro,source=load_sources(market_dir=market)
    path=market/'NQ.csv'
    if hashlib.sha256(path.read_bytes()).hexdigest()!=NQ_HASH:
        raise ValueError('pinned NQ hash mismatch')
    nq=pd.read_csv(path)
    nq.index=pd.to_datetime(nq.pop('datetime'),utc=True).dt.tz_convert('America/New_York')
    assert nq.index.is_unique and nq.index.is_monotonic_increasing
    frames=[]
    for date,b in micro['MNQ.csv'].groupby(micro['MNQ.csv'].index.date):
        if b.index.isin(nq.index).all():
            assert len(b)==390 and (b.index.to_series().diff().dropna()==pd.Timedelta(minutes=1)).all()
            frames.append(day_frame(b,nq.loc[b.index]))
    f=pd.concat(frames)
    dates=sorted(set(f.index.strftime('%Y-%m-%d')))
    reference=Path(__file__).resolve().parents[1]/'reservoir_lab/response_evidence/results/external/cross-market.json'
    assert dates==json.loads(reference.read_text())['included_dates'] and len(dates)==59
    n=len(dates)
    starts=np.random.default_rng(604).integers(n,size=(10000,(n+4)//5,1))
    idx=((starts+np.arange(5))%n).reshape(10000,-1)[:,:n]
    report={'dates':dates,'bars':len(f),'diagnostics':{},'policies':{},'paired':{}}
    for name,sub in [('all',f),('volume_gate',f[f.volume.abs()>3])]:
        sign=np.sign(sub.volume)
        fields=['close_to_open','peer_close_to_open','spread_convergence','paid_0','paid_1','basis_paid_0','basis_paid_1']
        diag={'rows':len(sub),'nonzero_volume_scores':int(sign.ne(0).sum()),
              'mean_abs_volume_score_pts':float(sub.volume.abs().mean()),
              'mean_signed_pts':{k:float((sign*sub[k]).mean()) for k in fields} if len(sub) else {},
              'rank':{k:{t:correlation(sub[k],sub[t]) for t in ['close_to_open','paid_0','paid_1']}
                      for k in POLICIES}}
        report['diagnostics'][name]=diag
    ledgers=[]
    for delay in [0,1]:
        daynets={}
        out={}
        for model in POLICIES:
            t=trades(f,model,delay)
            ledgers.append(t)
            net6=t.gross-6
            daynets[model]=net6.groupby(t.date).sum().reindex(dates,fill_value=0).to_numpy(dtype=float)
            out[model]={'trades':len(t),'active_days':int(t.date.nunique()),'gross':float(t.gross.sum()),
                        'long':int((t.side>0).sum()),'without_best_day_at6':float(net6.sum()-max(0,daynets[model].max())),
                        'costs':{cost:{'net':float((t.gross-cost).sum()),
                                      'without_best_trade':float((t.gross-cost).sum()-(t.gross-cost).nlargest(1).clip(lower=0).sum()),
                                      **marks(t,cost)} for cost in [3,6,9]}}
        paired={}
        for name,ctrl in dict(cash=np.zeros(n),equal=daynets['equal'],peer=daynets['peer'],
                              micro_reversion=daynets['micro_reversion']).items():
            diff=daynets['volume']-ctrl
            paired[name]={'daily_mean':float(diff.mean()),'interval95':np.quantile(diff[idx].mean(axis=1),[.025,.975]).tolist()}
        report['policies'][delay]=out
        report['paired'][delay]=paired
    dest.mkdir(parents=True,exist_ok=True)
    comp={'method':'gzip','mtime':0}
    pd.concat(ledgers,ignore_index=True).to_csv(dest/'trades.csv.gz',index=False,compression=comp)
    f.to_csv(dest/'decision_bars.csv.gz',index_label='signal_bar',compression=comp)
    (dest/'summary.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    (dest/'source.json').write_text(json.dumps(dict(peer_sha256=NQ_HASH,external=source['external']),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('market',type=Path)
    p.add_argument('results',type=Path)
    a=p.parse_args()
    run(a.market,a.results)
