"""Keep the frozen holding-value circuit and change only its causal issuance clock."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.branch_value.run import evaluate_cohort, summarize


def run(root,dest):
    bundle=root/'capacity/results'
    a=pd.read_csv(bundle/'activations.csv.gz',usecols=['bar_start','panel','date','delay','trade_id','model',
        'entry_scale','eligible','discretionary','direction','reservoir','original_exit_time','original_exit_price','next_executable_price'])
    a=a[a.model.eq('original') & a.eligible & a.discretionary].copy()
    a['stamp']=pd.to_datetime(a.bar_start,utc=True)
    a['source']=np.where(a.panel.eq('external'),'external60','discovery40')
    w=pd.read_csv(root/'reversal_hazard/results/warnings.csv.gz',usecols=['stamp','source','possible','feasibility','grid','laplace','reversal'])
    w['stamp']=pd.to_datetime(w.stamp,utc=True)
    w=w.rename(columns={k:'p_'+k for k in ('grid','laplace','feasibility')})
    selected=a.merge(w[w.possible],on=['source','stamp'],validate='many_to_one').sort_values('stamp')
    selected=selected.drop_duplicates(['source','delay','trade_id']).copy()
    assert (selected.direction*selected.reservoir>0).all()
    selected['matures']=pd.to_datetime(selected.original_exit_time,utc=True)
    selected['realized_hold_pts']=selected.direction*(selected.original_exit_price-selected.next_executable_price)
    t=pd.read_csv(bundle/'trades.csv.gz')
    t=t[t.model.eq('original')].copy()
    t['source']=np.where(t.panel.eq('external'),'external60','discovery40')
    data=[];result={}
    for (s,d),g in selected.groupby(['source','delay']):
        rows=evaluate_cohort(g)
        baseline=t[t.source.eq(s)&t.delay.eq(d)]
        summary=summarize(baseline,rows,sorted(baseline.date.unique()))
        common=rows.dropna(subset=['reversal','y'])
        delta=-2*common.y
        summary['always_exit_at_first_possible']={'chosen':len(delta),'increment_usd':delta.sum(),
            'net':{cost:float((baseline.gross_usd-cost).sum()+delta.sum()) for cost in [3,6,9]}}
        summary['grid_minus_always_exit_usd']=summary['models']['grid']['increment_usd']-delta.sum()
        result.setdefault(s,{})[int(d)]=summary
        data.append(rows)
    dest.mkdir(exist_ok=True,parents=True)
    pd.concat(data).to_csv(dest/'predictions.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    (dest/'summary.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('experiments',type=Path);p.add_argument('out',type=Path)
    a=p.parse_args();run(a.experiments,a.out)
