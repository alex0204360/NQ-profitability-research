"""Exact one-position policy-class economics, then chronological table selection."""
import argparse
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

DELAYS=[0,1,9,60]
COSTS=[3,6,9]


def replay_subsets(day):
    # Every sign assignment with the same active subset has the same fills.
    masks=np.arange(256)
    busy=np.full(256,-1,dtype=np.int64)
    counts=np.zeros((256,8),dtype=int)
    gross=np.zeros((256,8))
    for e in day.itertuples():
        bit=4*e.leader+2*int(e.direction>0)+int(e.kind=='continuation')
        signal=e.signal.value
        taking=((masks&(1<<bit))>0)&(signal>=busy)
        if pd.isna(e.entry_time):
            busy[taking]=(e.requested_entry+pd.Timedelta(seconds=2)).value
            continue
        if pd.isna(e.exit_time):
            raise ValueError('An unresolved opportunity prevents a complete class bound')
        busy[taking]=e.exit_time.value
        counts[taking,bit]+=1
        gross[taking,bit]+=2*e.direction*(e.exit-e.entry)
    return counts,gross


def run(bundle, output):
    days=json.loads((bundle/'schedule.json').read_text())['scheduled_dates']
    opportunities=pd.read_csv(bundle/'opportunities.csv.gz')
    for k in ['signal','entry_time','exit_time','requested_entry']:
        opportunities[k]=pd.to_datetime(opportunities[k],utc=True)
    # Order by complexity, then lexicographically; argmax chooses cash in a tie.
    codes=np.array(sorted(itertools.product([-1,0,1],repeat=8),key=lambda t:(sum(v!=0 for v in t),t)))
    masks=np.abs(codes)@(1<<np.arange(8))
    baseline=np.flatnonzero(np.all(codes==np.tile([-1,1],4),axis=1)).item()
    gross=np.zeros((len(days),4,len(codes)))
    counts=np.zeros(gross.shape,dtype=np.int32)
    for (date,delay), part in opportunities.groupby(['date','delay']):
        i,j=days.index(date),DELAYS.index(delay)
        n,g=replay_subsets(part.sort_values('signal'))
        counts[i,j]=n[masks].sum(axis=1)
        gross[i,j]=(codes*g[masks]).sum(axis=1)
        known=part[part.accepted & part.exit.notna()]
        assert counts[i,j,baseline]==len(known)
        assert gross[i,j,baseline]==(2*known.action*(known.exit-known.entry)).sum()
    returns={cost:gross-cost*counts for cost in COSTS}
    scored=pd.DataFrame({'code':[''.join({1:'F',0:'.',-1:'R'}[v] for v in t) for t in codes]})
    report={'tables':len(codes),'results':{},'worst_of_1s_9s':{},'chronological':{}}
    for j,delay in enumerate(DELAYS):
        n=counts[:,j].sum(axis=0)
        scored[f'trades_{delay}']=n
        report['results'][delay]={}
        for cost in COSTS:
            val=returns[cost][:,j].sum(axis=0)
            scored[f'net_{delay}_{cost}']=val
            report['results'][delay][cost]={'maximum':float(val.max()),'positive':int((val>0).sum()),
                                            'best_with_exposure':float(val[n>0].max()),
                                            'exposed_tables':int((n>0).sum())}
    for cost in COSTS:
        pair=returns[cost][:,[1,2]].sum(axis=0)
        robust=pair.min(axis=0)
        active=(counts[:,[1,2]].sum(axis=0)>0).all(axis=0)
        report['worst_of_1s_9s'][cost]={'maximum':float(robust.max()),'positive_both':int((robust>0).sum()),
                                       'best_with_exposure':float(robust[active].max())}
    selections=[]
    for i,date in enumerate(days):
        history=returns[6][:i,1:3]
        if i:
            robust=(history.sum(axis=0)-np.maximum(0,history.max(axis=0))).min(axis=0)
            winner=int(np.argmax(robust))
        else:
            winner=0
        for j,delay in enumerate(DELAYS):
            selections.append(dict(date=date,delay=delay,code=scored.code.iloc[winner],
                                   trades=int(counts[i,j,winner]),gross=float(gross[i,j,winner]),
                                   **{f'net_{c}':float(returns[c][i,j,winner]) for c in COSTS}))
    selected=pd.DataFrame(selections)
    for delay,z in selected.groupby('delay'):
        report['chronological'][int(delay)]={'trades':int(z.trades.sum()),'active_days':int((z.trades>0).sum()),
                                            'net':{c:float(z[f'net_{c}'].sum()) for c in COSTS}}
    output.mkdir(exist_ok=True,parents=True)
    scored.to_csv(output/'tables.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    selected.to_csv(output/'chronological.csv',index=False)
    (output/'summary.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('bundle',type=Path);p.add_argument('out',type=Path)
    a=p.parse_args();run(a.bundle,a.out)
