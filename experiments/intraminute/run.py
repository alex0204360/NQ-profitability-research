"""Reconcile pinned second bars, then reprice frozen minute forecasts on a common grid."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

BLOBS = {'MNQ':'d9a91eea5dcd13c4b1af8ea3248937f61db18cce','NQ':'fc9730d2844b487be2f1d77d87ef3ddf664f04fd'}
MINUTE_HASH = {'NQ':'583cd788b035c4b5ca612f8bb0e3e366d627348851c04d68bca295a5db116f61',
               'MNQ':'129623f45308a98a1a345473ac5fe4d03d5d53f7dd177a608d946eb3d3d6ea99'}
FIELDS=['open','high','low','close','volume']
DELAYS=[0,1,9,30,60]
SOURCE=Path(__file__).resolve().parents[1]/'dislocation/results'


def load(path, symbol, fine):
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if fine:
        blob=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        if blob!=BLOBS[symbol]:
            raise ValueError(f'{symbol} fine blob mismatch')
    elif digest!=MINUTE_HASH[symbol]:
        raise ValueError(f'{symbol} minute SHA256 mismatch')
    z=pd.read_csv(path)
    z.index=pd.to_datetime(z.pop('datetime'),utc=True).dt.tz_convert('America/New_York')
    if list(z)!=FIELDS or not z.index.is_unique or not z.index.is_monotonic_increasing:
        raise ValueError('unexpected OHLCV source')
    return z,digest


def reconcile(minute, fine, shift):
    key=(fine.index-pd.Timedelta(seconds=shift)).floor('min')
    groups=fine.groupby(key)
    rolled=groups.agg(dict(open='first',high='max',low='min',close='last',volume='sum')).reindex(minute.index)
    match=rolled.eq(minute)
    exact=match.all(axis=1)
    info=dict(expected=len(minute), present=int(rolled.open.notna().sum()),exact=int(exact.sum()),
              missing=int(rolled.open.isna().sum()), mismatching_present=int((rolled.open.notna()&~exact).sum()),
              fields={k:int(v) for k,v in match.sum().items()})
    return exact,info


def endpoints(stamps,tape):
    targets=pd.DatetimeIndex(stamps)
    indices=tape.index.searchsorted(targets)
    safe=np.minimum(indices,len(tape)-1)
    times=tape.index[safe]
    ok=(indices<len(tape))&(times>=targets)&(times-targets<=pd.Timedelta(seconds=2))
    return times,np.where(ok,tape.open.to_numpy()[safe],np.nan)


def rank(x,y):
    return float(spearmanr(x,y).statistic) if len(x)>1 and x.nunique()>1 and y.nunique()>1 else None


def evaluate(rows,dates):
    summary={}
    if not len(rows):
        return summary
    n=len(dates)
    starts=np.random.default_rng(604).integers(n,size=(10000,(n+4)//5,1))
    blocks=((starts+np.arange(5))%n).reshape(10000,-1)[:,:n]
    counts=rows.groupby('date').size().reindex(dates,fill_value=0).to_numpy()[blocks].sum(axis=1)
    for model in ('volume','equal','age'):
        score=rows[model]
        sign=np.sign(score)
        triggered=rows[score.abs()>3]
        results={}
        for sec in DELAYS:
            e='e'+str(sec); out='x'+str(sec)
            move=rows[out]-rows[e]
            directional=sign*move
            daily=directional.groupby(rows.date).sum().reindex(dates,fill_value=0).to_numpy()
            valid=counts>0
            ci=np.quantile(daily[blocks].sum(axis=1)[valid]/counts[valid],[.025,.975]).tolist()
            busy=None
            profits=[]
            for row in triggered.itertuples():
                issue=row.Index+pd.Timedelta(minutes=1)
                if busy is not None and issue<busy:
                    continue
                busy=getattr(row,out+'_time')
                pnl=2*np.sign(getattr(row,model))*(getattr(row,out)-getattr(row,e))
                profits.append(pnl)
            p=np.array(profits)
            results[sec]=dict(mean_signed_prefill=float((sign*(rows[e]-rows.micro_close)).mean()),
                              mean_signed_open_to_open=float(directional.mean()),interval95=ci,
                              rank_prefill=rank(score,rows[e]-rows.micro_close),rank_open_to_open=rank(score,move),
                              gate_count=len(triggered),nonoverlap_replay_count=len(p),nonoverlap_net={c:float((p-c).sum()) for c in (3,6,9)})
        summary[model]=results
    return summary


def run(market,dest):
    dates=json.loads((SOURCE/'summary.json').read_text())['dates']
    dates=[d for d in dates if '2026-03-09'<=d<='2026-04-15']
    grid=pd.DatetimeIndex([i for day in dates for i in pd.date_range(day+' 09:30',periods=390,freq='min',tz='America/New_York')])
    exacts,raw,reference,lasts,stats={},{},{},{},{}
    for symbol in ['MNQ','NQ']:
        fine,digest=load(market/(symbol+'_fine.csv'),symbol,True)
        minute,refhash=load(market/(symbol+'.csv'),symbol,False)
        reference[symbol]=minute.loc[grid]
        a,st=reconcile(reference[symbol],fine,0)
        b,alt=reconcile(reference[symbol],fine,1)
        exacts[symbol]=(a,b);raw[symbol]=fine
        lasts[symbol]=fine.index.to_series().groupby(fine.index.floor('min')).last()
        rh=fine[fine.index.floor('min').isin(grid)]
        stats[symbol]=dict(sha256=digest,minute_sha256=refhash,git_blob=BLOBS[symbol],
                           schema=list(fine),rows_in_file=len(fine),regular_rows=len(rh),
                           multi_price_regular_rows=int((rh.high>rh.low).sum()),
                           integer_second_grid=bool((rh.index.microsecond==0).all() and (rh.index.nanosecond==0).all()),
                           consecutive_one_second_gaps=int((rh.index.to_series().diff()==pd.Timedelta(seconds=1)).sum()),
                           as_labeled=st,one_second_back=alt)
    joint=exacts['MNQ'][0]&exacts['NQ'][0]
    alt=exacts['MNQ'][1]&exacts['NQ'][1]
    f=pd.read_csv(SOURCE/'decision_bars.csv.gz')
    f.index=pd.to_datetime(f.pop('signal_bar'),utc=True).dt.tz_convert('America/New_York')
    f=f.loc[f.index.isin(grid),['basis','residual','volume','equal']].copy()
    t=f.index+pd.Timedelta(minutes=1)
    f['date']=f.index.strftime('%Y-%m-%d')
    f['micro_close']=reference['MNQ'].close.reindex(f.index)
    for symbol in ['MNQ','NQ']:
        f['age_'+symbol]=(t-lasts[symbol].reindex(f.index)).dt.total_seconds()
    f['age']=f.residual*(1+f.age_MNQ)/(2+f.age_MNQ+f.age_NQ)
    keep=joint.reindex(f.index).to_numpy().copy()
    for m in (1,2):
        keep &= joint.reindex(f.index+pd.Timedelta(minutes=m),fill_value=False).to_numpy()
    initial_keep=int(keep.sum())
    for sec in DELAYS:
        for k,offset in [('e',sec),('x',sec+60)]:
            actual,price=endpoints(t+pd.Timedelta(seconds=offset),raw['MNQ'])
            key=k+str(sec)
            f[key]=price
            f[key+'_time']=actual.where(np.isfinite(price),pd.NaT)
            keep &= np.isfinite(price) & joint.reindex(actual.floor('min'),fill_value=False).to_numpy()
    f['common']=keep
    cohort=f.loc[keep]
    summary=dict(source=stats,scheduled_dates=dates,expected_minutes=len(grid),joint_exact=int(joint.sum()),
                 shifted_joint_exact=int(alt.sum()),joint_exact_dates=int(joint[joint].index.normalize().nunique()),
                 expected_decisions=len(f),initial_joint_window=initial_keep,common_decisions=len(cohort),
                 common_dates=int(cohort.date.nunique()),common_volume_gates=int((cohort.volume.abs()>3).sum()),
                 timing=evaluate(cohort,dates))
    summary['age_groups']={}
    for label,mask in [('micro_older',cohort.age_MNQ>cohort.age_NQ),('equal',cohort.age_MNQ==cohort.age_NQ),
                       ('peer_older',cohort.age_MNQ<cohort.age_NQ)]:
        g=cohort[mask]
        summary['age_groups'][label]=dict(rows=len(g),mean_signed_prefill=float((np.sign(g.age)*(g.e0-g.micro_close)).mean()) if len(g) else None,
                                          rank_paid_1s=rank(g.age,g.x1-g.e1),rank_paid_9s=rank(g.age,g.x9-g.e9))
    event=pd.Timestamp('2026-04-08 10:08',tz='America/New_York')
    summary['april8']={str(t):{'MNQ':bool(exacts['MNQ'][0].loc[t]),'NQ':bool(exacts['NQ'][0].loc[t])}
                       for t in pd.date_range(event,periods=4,freq='min')}
    summary['april8_in_common']=bool(f.loc[event,'common'])
    dest.mkdir(parents=True,exist_ok=True)
    f.to_csv(dest/'timing.csv.gz',index_label='signal_bar',compression={'method':'gzip','mtime':0})
    pd.DataFrame(dict(micro=exacts['MNQ'][0],peer=exacts['NQ'][0],joint=joint)).to_csv(dest/'minute-coverage.csv.gz',index_label='minute',compression={'method':'gzip','mtime':0})
    (dest/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('market',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();run(a.market,a.output)
