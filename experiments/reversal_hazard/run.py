"""Score the frozen probabilities on chronological sessions with a one-bar delay."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata

from .neuron import Hazard

MODELS = ('constant','feasibility','laplace','grid')
BINS = np.array([0., .05, .1, .2, .35, .5, 1.])
MINUTE = pd.Timedelta(minutes=1)


def issue(day, memory):
    day = day.sort_values('stamp').copy()
    # Compute tomorrow's normalizer from the current completed bar and the parent's
    # exact EMA initialization; no next-bar value is available to the predictors.
    last = None
    scales = []
    for b in day.itertuples():
        width = b.high - b.low
        if last is None or b.stamp-last != MINUTE:
            state = max(.25,width)
        state = state*31/32 + width/32
        scales.append(max(.25,state))
        last = b.stamp
    day['next_scale'] = scales
    issued = day.reservoir.notna() & day.reservoir.ne(0) & (day.stamp+MINUTE).dt.strftime('%H:%M').lt('15:55')
    z = day.loc[issued,['stamp','date','close','reservoir','stock','scale','next_scale','held']].copy()
    z['ratio'] = (z.reservoir.abs()/z.scale).div(z.stock.where(z.stock.gt(0))).fillna(np.inf)
    z['possible'] = z.ratio.le(1)
    z['prior_n'] = memory.n
    z['prior_possible'] = memory.possible
    for k,p in memory.predict(z.ratio).items():
        z[k]=p
    actual = day.set_index('stamp').reindex(pd.DatetimeIndex(z.stamp)+MINUTE)
    actual.index=z.index
    z['resolved'] = actual.reservoir.notna()
    z['reversal'] = (actual.reservoir*np.sign(z.reservoir)<=0).where(z.resolved).astype(float)
    z['adverse'] = (-np.sign(z.reservoir)*(actual.close-z.close)/z.next_scale).where(z.resolved)
    resolved=z[z.resolved]
    np.testing.assert_allclose(z.loc[z.resolved,'next_scale'],actual.loc[z.resolved,'scale'],rtol=1e-12)
    np.testing.assert_array_equal(resolved.possible & resolved.adverse.ge(resolved.ratio),resolved.reversal)
    memory.settle_session(resolved.adverse,resolved.possible,resolved.reversal)
    return z


def rank_metrics(y,p):
    if len(np.unique(y))<2 or len(np.unique(p))<2:
        return {'spearman':None,'auc':0.5 if len(np.unique(y))==2 else None}
    ranks=rankdata(p)
    pos=y==1
    a=pos.sum()
    return {'spearman':float(np.corrcoef(rankdata(y),ranks)[0,1]),
            'auc':float((ranks[pos].sum()-a*(a+1)/2)/(a*(len(y)-a)))}


def statistics(z, dates):
    n=len(dates)
    starts=np.random.default_rng(604).integers(n,size=(10000,(n+4)//5,1))
    blocks=((starts+np.arange(5))%n).reshape(10000,-1)[:,:n]
    counts=z.groupby('date').size().reindex(dates,fill_value=0).to_numpy()
    total=counts[blocks].sum(axis=1)
    daily={}
    out={'n':len(z),'reversals':int(z.reversal.sum()),'prevalence':float(z.reversal.mean()),'models':{},'paired':{}}
    for model in MODELS:
        p=z[model]
        y=z.reversal
        error=(p-y)**2
        daily[model]=error.groupby(z.date).sum().reindex(dates,fill_value=0).to_numpy()
        clip=p.clip(1e-6,1-1e-6)
        bins=[]
        for i,(lo,hi) in enumerate(zip(BINS[:-1],BINS[1:])):
            mask=p.ge(lo)&(p.lt(hi) if i<len(BINS)-2 else p.le(hi))
            bins.append(dict(low=lo,high=hi,n=int(mask.sum()),mean_predicted=float(p[mask].mean()) if mask.any() else None,
                             observed=float(y[mask].mean()) if mask.any() else None))
        out['models'][model]=dict(brier=float(error.mean()),
                                  log_loss=float(-(y*np.log(clip)+(1-y)*np.log1p(-clip)).mean()),
                                  mean_probability=float(p.mean()),**rank_metrics(y.to_numpy(),p.to_numpy()),bins=bins)
    for other in MODELS[:-1]:
        diff=daily['grid']-daily[other]
        vals=diff[blocks].sum(axis=1)[total>0]/total[total>0]
        out['paired'][other]=dict(grid_minus_control=float(diff.sum()/len(z)),ci95=np.quantile(vals,[.025,.975]).tolist())
    return out


def run(bundle, destination):
    df=pd.read_csv(bundle/'scores.csv.gz',usecols=['panel','date','bar_start','close','high','low','scale','stock','reservoir'])
    held=pd.read_csv(bundle/'activations.csv.gz',usecols=['bar_start','panel','model','delay'])
    held=held[held.delay.eq(0)&held.model.eq('original')][['bar_start','panel']].assign(held=True)
    df=df.merge(held,on=['bar_start','panel'],how='left',validate='one_to_one')
    df['held']=df.held.eq(True)
    df['stamp']=pd.to_datetime(df.bar_start,utc=True).dt.tz_convert('America/New_York')
    df['source']=np.where(df.panel.eq('external'),'external60','discovery40')
    rows=[]; report={}
    for source,part in df.groupby('source'):
        memory=Hazard()
        daily=[issue(day,memory) for _,day in part.groupby('date',sort=True)]
        forecasts=pd.concat(daily).assign(source=source)
        z=forecasts[forecasts.resolved]
        dates=sorted(part.date.unique())
        report[source]=dict(dates=dates,issued=len(forecasts),censored=int((~forecasts.resolved).sum()),
                            subsets={k:statistics(s,dates) for k,s in
                                     [('all',z),('reachable',z[z.possible]),('held',z[z.held]),('held_reachable',z[z.held&z.possible])]})
        rows.append(forecasts)
    report['source_sha256']={f:hashlib.sha256((bundle/f).read_bytes()).hexdigest() for f in ['scores.csv.gz','activations.csv.gz']}
    destination.mkdir(exist_ok=True,parents=True)
    pd.concat(rows).to_csv(destination/'warnings.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    (destination/'summary.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('bundle',type=Path)
    p.add_argument('destination',type=Path)
    a=p.parse_args();run(a.bundle,a.destination)
