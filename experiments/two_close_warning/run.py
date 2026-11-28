"""Project prior-session input paths through the two-step parent recurrence."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.reversal_hazard.run import rank_metrics

DECAY = 7 / 8
PRIOR = 1 / 32
MASS = 20
MINUTE = pd.Timedelta(minutes=1)
MODELS = ("fixed", "rate", "price", "rotated", "joint")


def paths(day):
    """Index templates by their origin. Skip missing minutes at either step."""
    minute = day.stamp.diff().eq(MINUTE)
    valid = (day.reservoir.notna() & day.reservoir.ne(0)
             & minute.shift(-1, fill_value=False) & minute.shift(-2, fill_value=False)
             & day.reservoir.shift(-1).notna() & day.reservoir.shift(-2).notna()
             & (day.stamp+2*MINUTE).dt.strftime("%H:%M").lt("15:55"))
    ix = np.flatnonzero(valid)
    sign = np.sign(day.reservoir.iloc[ix].to_numpy())
    motion = day.motion.clip(-1,1).to_numpy()
    u1, u2 = sign*motion[ix+1], sign*motion[ix+2]
    magnitude = np.abs(day.motion.to_numpy()[ix+1])
    effort = day.effort.to_numpy()[ix+1]
    original_charge = day.charge.to_numpy()[ix+1]
    np.testing.assert_allclose(original_charge, np.maximum(0,effort-magnitude), atol=1e-14)
    rotated = effort.copy()
    bins = np.minimum(4,np.floor(np.abs(u1)*5).astype(int))
    for key in np.unique(bins):
        select = bins == key
        rotated[select] = np.roll(effort[select],int(select.sum())//2)
    return pd.DataFrame(dict(direction_effect=u1+(1-np.abs(u1))*u2,
        joint=original_charge*u2, price=.25*np.maximum(0,1-magnitude)**2*u2,
        rotated=np.maximum(0,rotated-magnitude)*u2,
        target=(sign*day.reservoir.to_numpy()[ix+2] <= 0).astype(int)), index=ix)


def issue(day, prior_paths, rate):
    day = day.sort_values("stamp").reset_index(drop=True)
    template = paths(day)
    issuable = day.earliest.eq(2) & (day.stamp+2*MINUTE).dt.strftime("%H:%M").lt("15:55")
    queries = day.loc[issuable].copy()
    magnitude = (queries.reservoir.abs()/queries.scale).to_numpy()
    stock = queries.stock.to_numpy()
    queries["templates"] = len(prior_paths)
    queries["fixed"], queries["rate"] = PRIOR, rate
    if len(prior_paths):
        base = DECAY**2*(magnitude[:,None]+stock[:,None]*prior_paths.direction_effect.to_numpy())
    for name in ("price","rotated","joint"):
        count = (base + DECAY*prior_paths[name].to_numpy() <= 0).sum(axis=1) if len(prior_paths) else 0
        queries[name] = (count+MASS*PRIOR)/(len(prior_paths)+MASS)
    truth = template.reindex(queries.index)
    queries["target"] = truth.target
    realized_margin = DECAY**2*(magnitude+stock*truth.direction_effect)+DECAY*truth.joint
    normalized = (day.reservoir.shift(-2)/day.scale.shift(-2)).reindex(queries.index)*np.sign(queries.reservoir)
    resolved = queries.target.notna()
    np.testing.assert_allclose(realized_margin[resolved],normalized[resolved],atol=1e-12,rtol=1e-12)
    queries["sign_disagreement"] = resolved & ((realized_margin <= 0) != queries.target.eq(1))
    queries["near_boundary"] = resolved & realized_margin.abs().lt(1e-12)
    assert not (queries.sign_disagreement & ~queries.near_boundary).any()
    next_rate = (queries.target.sum()+MASS*PRIOR)/(resolved.sum()+MASS)
    return queries[["source","date","stamp","held","templates",*MODELS,"target","sign_disagreement","near_boundary"]], template,next_rate


def score(rows, dates):
    resolved = rows.dropna(subset=["target"])
    n = len(dates)
    starts = np.random.default_rng(604).integers(n,size=(10000,(n+4)//5,1))
    select=((starts+np.arange(5))%n).reshape(10000,-1)[:,:n]
    totals = resolved.groupby("date").size().reindex(dates,fill_value=0).to_numpy()[select].sum(axis=1)
    out = dict(issued=len(rows),resolved=len(resolved),events=int(resolved.target.sum()),models={},paired={},
               sign_disagreements=int(resolved.sign_disagreement.sum()),near_zero=int(resolved.near_boundary.sum()))
    for name in MODELS:
        p,y = resolved[name],resolved.target
        error = (p-y)**2
        bins = []
        for low,high in zip((0,.01,.025,.05,.1,.2),(.01,.025,.05,.1,.2,1.000001)):
            sel = p.ge(low)&p.lt(high)
            bins.append(dict(low=low,high=min(high,1.),n=int(sel.sum()),
                mean_prediction=float(p[sel].mean()) if sel.any() else None,
                observed=float(y[sel].mean()) if sel.any() else None))
        out["models"][name]=dict(brier=error.mean(),mean=p.mean(),**rank_metrics(y.to_numpy(),p.to_numpy()),bins=bins)
        if name != "joint":
            diff = (resolved.joint-y)**2-error
            daily = diff.groupby(resolved.date).sum().reindex(dates,fill_value=0).to_numpy()
            sampled = daily[select].sum(axis=1)
            out["paired"][name]=dict(delta=diff.mean(),
                ci95=np.quantile(sampled[totals>0]/totals[totals>0],[.025,.975]).tolist())
    return out


def run(root,out):
    scores = root/"capacity/results/scores.csv.gz"
    horizons = root/"certified_horizon/results/horizons.csv.gz"
    data = pd.read_csv(scores,usecols=["bar_start","panel","date","reservoir","stock","scale","motion","effort","charge"])
    data["stamp"]=pd.to_datetime(data.bar_start,utc=True).dt.tz_convert("America/New_York")
    data["source"]=np.where(data.panel.eq("external"),"external60","discovery40")
    h=pd.read_csv(horizons,usecols=["source","stamp","earliest","held"])
    h["stamp"]=pd.to_datetime(h.stamp,utc=True).dt.tz_convert("America/New_York")
    data=data.merge(h,on=["source","stamp"],how="left",validate="one_to_one")
    book, report = [], {}
    for source,g in data.groupby("source"):
        prior_paths,rate,rows=pd.DataFrame(),PRIOR,[]
        for _,day in g.groupby("date",sort=True):
            q,prior_paths,rate=issue(day,prior_paths,rate)
            rows.append(q)
        archive=pd.concat(rows)
        report[source]=score(archive,sorted(g.date.unique()))
        book.append(archive)
    report["sha256"]={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [scores,horizons]}
    out.mkdir(parents=True,exist_ok=True)
    pd.concat(book).to_csv(out/"forecasts.csv.gz",index=False,compression={"method":"gzip","mtime":0})
    (out/"summary.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("experiments",type=Path)
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    run(args.experiments,args.output)
