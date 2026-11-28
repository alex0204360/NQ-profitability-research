"""Chronological forecasts, fixed-entry policy effects, and explicit retrospective control."""
import argparse
import hashlib
import heapq
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from .neuron import BranchValue

MODELS=['zero','pooled','feasibility','laplace','grid','retrospective']
MIN=pd.Timedelta(minutes=1)


def evaluate_cohort(cohort):
    model=BranchValue()
    rows=[]
    pending=[]
    for i,x in enumerate(cohort.sort_values('stamp').itertuples()):
        now=x.stamp+MIN
        while pending and pending[0][0]<now:
            _,_,label,value=heapq.heappop(pending)
            model.settle(label,value)
        probs={name:getattr(x,'p_'+name) for name in ['grid','laplace','feasibility']}
        pred=model.predict(x.entry_scale,probs)
        pooled,branches=model.means()
        # The retrospective comparator has access to the realized next event only here.
        later=x.reversal
        hindsight=x.entry_scale*branches[int(later)] if pd.notna(later) else np.nan
        rows.append(dict(date=x.date,source=x.source,delay=x.delay,trade_id=x.trade_id,issue=now,
                         entry_scale=x.entry_scale,reversal=later,y=x.realized_hold_pts,
                         prior_survives=model.n[0],prior_flips=model.n[1],p_grid=probs['grid'],
                         survive_value=x.entry_scale*branches[0],flip_value=x.entry_scale*branches[1],
                         retrospective=hindsight,**pred))
        if pd.notna(later) and pd.notna(x.realized_hold_pts):
            maturity=max(now+MIN,x.matures)
            heapq.heappush(pending,(maturity,i,int(later),x.realized_hold_pts/x.entry_scale))
    return pd.DataFrame(rows)


def summarize(original,rows,dates):
    common=rows.dropna(subset=['y',*MODELS]).copy()
    n=len(dates)
    blocks=np.random.default_rng(604).integers(n,size=(10000,(n+4)//5,1))
    ix=((blocks+np.arange(5))%n).reshape(10000,-1)[:,:n]
    count=common.groupby('date').size().reindex(dates,fill_value=0).to_numpy()[ix].sum(axis=1)
    valid=count>0
    result={'scheduled':len(rows),'common':len(common),'original_trades':len(original),
            'branches':{int(k):{'n':len(z),'mean_realized_pts':z.y.mean()} for k,z in common.groupby('reversal')},
            'models':{},'grid_minus':{}}
    for k in MODELS:
        err=common[k]-common.y
        common['se_'+k]=err**2
        pair=original.merge(common[['trade_id','y',k]],on='trade_id',how='left',validate='one_to_one')
        acted=pair[k].lt(0)
        delta=(-2*pair.y).where(acted,0.)
        result['models'][k]=dict(mse=(err**2).mean(),mae=err.abs().mean(),bias=err.mean(),
            rank=float(spearmanr(common[k],common.y).statistic) if common[k].nunique()>1 else None,
            early_exits=int(acted.sum()),increment_usd=delta.sum(),without_best_three=delta.sum()-delta.clip(lower=0).nlargest(3).sum(),costs={})
        for c in (3,6,9):
            base=pair.gross_usd-c
            result['models'][k]['costs'][c]=dict(original_net=base.sum(),edited_net=base.sum()+delta.sum(),
                saved_on_losers=delta[base<0].clip(lower=0).sum(),added_loss_on_losers=-delta[base<0].clip(upper=0).sum(),
                surrendered_on_winners=-delta[base>0].clip(upper=0).sum(),added_gain_on_winners=delta[base>0].clip(lower=0).sum())
    for ctrl in ['zero','pooled','feasibility','laplace','retrospective']:
        ds=common.se_grid-common['se_'+ctrl]
        totals=ds.groupby(common.date).sum().reindex(dates,fill_value=0).to_numpy()
        ci=np.quantile(totals[ix].sum(axis=1)[valid]/count[valid],[.025,.975]).tolist()
        result['grid_minus'][ctrl]=dict(mse_delta=ds.mean(),ci95=ci)
    return result


def run(root,dest):
    hold=root/'hold_work/results'
    warning=root/'reversal_hazard/results/warnings.csv.gz'
    z=pd.read_csv(hold/'first-decisions.csv.gz')
    z['stamp']=pd.to_datetime(z.bar_start,utc=True)
    z['matures']=pd.to_datetime(z.original_exit_time,utc=True)
    assert z.discretionary.all() and z.eligible.all() and (z.direction*z.forecast>0).all()
    w=pd.read_csv(warning,usecols=['source','stamp','feasibility','laplace','grid','reversal'])
    w['stamp']=pd.to_datetime(w.stamp,utc=True)
    w=w.rename(columns={k:'p_'+k for k in ['feasibility','laplace','grid']})
    t=pd.read_csv(hold/'trades.csv.gz')
    t=t[t.model.eq('original')].copy()
    for frame in [t,z]:
        frame['source']=np.where(frame.panel.eq('external'),'external60','discovery40')
    z=z.merge(w,on=['stamp','source'],how='left',validate='many_to_one')
    stats={}
    out=[]
    for (source,delay),g in z.groupby(['source','delay']):
        pred=evaluate_cohort(g)
        baseline=t[t.source.eq(source)&t.delay.eq(delay)]
        stats.setdefault(source,{})[int(delay)]=summarize(baseline,pred,sorted(baseline.date.unique()))
        out.append(pred)
    dest.mkdir(parents=True,exist_ok=True)
    pd.concat(out).to_csv(dest/'predictions.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    stats['input_sha256']={f.name:hashlib.sha256(f.read_bytes()).hexdigest()
                           for f in [warning,hold/'first-decisions.csv.gz',hold/'trades.csv.gz']}
    (dest/'summary.json').write_text(json.dumps(stats,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('experiments',type=Path)
    p.add_argument('output',type=Path)
    a=p.parse_args();run(a.experiments,a.output)
