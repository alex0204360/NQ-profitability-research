"""Emit causal synchronized events, then resolve each frozen order on the MNQ tape."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.intraminute.run import load
from .neuron import Transfer

ROOT=Path(__file__).resolve().parents[1]
DELAYS=(0,1,9,60)
SEC=pd.Timedelta(seconds=1)


def issue(micro,peer,basis,verified,date):
    common=micro[['open','close']].join(peer.close.rename('peer'),how='inner')
    minute=common.index.floor('min')
    common['basis']=basis.reindex(minute).to_numpy()
    common['verified']=verified.reindex(minute-pd.Timedelta(minutes=1),fill_value=False).to_numpy()
    cutoff=pd.Timestamp(date+' 15:55',tz='America/New_York')
    model=Transfer()
    rows=[]
    for bar in common.itertuples():
        stamp=bar.Index
        emitted=stamp+SEC
        if emitted+122*SEC>cutoff:
            break
        e=model.step(int(stamp.timestamp()),bar.close,bar.peer,
                     None if pd.isna(bar.basis) else bar.basis,bool(bar.verified))
        if e is None:
            continue
        e.update(date=date,signal=emitted,signal_start=stamp,body=int(np.sign(bar.close-bar.open)),
                 anchor_direction=int(np.sign(e['midpoint_change'])),micro_close=bar.close,peer_close=bar.peer,
                 kind='continuation' if e['action']==e['direction'] else 'fade' if e['action'] else 'abstain')
        rows.append(e)
    return rows


def resolve(rows,tape,date):
    cutoff=pd.Timestamp(date+' 15:55',tz='America/New_York')
    output=[]
    for delay in DELAYS:
        busy=None
        for e in rows:
            if e['action']==0:
                continue
            t=e['signal']
            due=t+delay*SEC
            accepted=busy is None or t>=busy
            row={k:e[k] for k in ['date','signal','action','direction','kind','q','body','anchor_direction','leader']}
            row.update(delay=delay,requested_entry=due,accepted=accepted,entry_time=pd.NaT,exit_time=pd.NaT,
                       entry=np.nan,exit=np.nan,late_exit=False,unresolved=False,after_cutoff=False)
            i=tape.index.searchsorted(due)
            if i==len(tape) or tape.index[i]>due+2*SEC:
                if accepted:
                    busy=due+2*SEC
                output.append(row)
                continue
            start=tape.index[i]
            row.update(entry_time=start,entry=tape.open.iat[i])
            due_exit=start+60*SEC
            j=tape.index.searchsorted(due_exit)
            if j==len(tape):
                row['unresolved']=True
                if accepted:
                    busy=cutoff
            else:
                finish=tape.index[j]
                row.update(exit_time=finish,exit=tape.open.iat[j],late_exit=finish>due_exit+2*SEC,
                           after_cutoff=finish>cutoff)
                if accepted:
                    busy=finish
            output.append(row)
    return output


def run(market, dest):
    ref=ROOT/'intraminute/results'
    schedule=json.loads((ref/'summary.json').read_text())['scheduled_dates']
    coverage=pd.read_csv(ref/'minute-coverage.csv.gz')
    coverage.index=pd.to_datetime(coverage.pop('minute'),utc=True).dt.tz_convert('America/New_York')
    m,mhash=load(market/'MNQ_fine.csv','MNQ',True)
    p,phash=load(market/'NQ_fine.csv','NQ',True)
    m1,_=load(market/'MNQ.csv','MNQ',False)
    p1,_=load(market/'NQ.csv','NQ',False)
    events=[]
    opportunities=[]
    for date in schedule:
        start=pd.Timestamp(date+' 09:30',tz='America/New_York')
        end=start+pd.Timedelta(minutes=390)-SEC
        micro=m.loc[start:end]
        b=(p1.close.loc[start:end]-m1.close.loc[start:end]).shift(1).rolling(31,min_periods=31).median()
        day=issue(micro,p.loc[start:end],b,coverage.joint,date)
        events.extend(day)
        opportunities.extend(resolve(day,micro,date))
    dest.mkdir(exist_ok=True,parents=True)
    comp={'method':'gzip','mtime':0}
    pd.DataFrame(events).to_csv(dest/'events.csv.gz',index=False,compression=comp)
    pd.DataFrame(opportunities).to_csv(dest/'opportunities.csv.gz',index=False,compression=comp)
    (dest/'schedule.json').write_text(json.dumps(dict(scheduled_dates=schedule,micro_sha256=mhash,
                                   peer_sha256=phash),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('market',type=Path);p.add_argument('results',type=Path)
    a=p.parse_args();run(a.market,a.results)
