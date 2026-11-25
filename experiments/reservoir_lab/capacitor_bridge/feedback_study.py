"""Score separately the predictive and trading behavior of frozen feedback."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from bridge import PRIOR,apply
from replay_lab import panels,run
from evaluate import paired


def forecast_stats(df,models):
    result={}
    truth=np.eye(3)[df.target.to_numpy(dtype=int)]
    pnl=df.move.to_numpy()
    for m in models:
        p=df[[f"{m}_{k}" for k in range(3)]].to_numpy()
        directional=p[:,2]-p[:,0]
        mask=(df.target!=1).to_numpy() & (abs(directional)>1e-12)
        daily=pd.Series(-np.log(df[f"p_{m}"]).to_numpy(),index=df.origin).resample("D").mean().dropna()
        result[m]=dict(n=len(df),logloss=float(-np.log(df[f"p_{m}"]).mean()),
                       brier=float(((p-truth)**2).sum(axis=1).mean()),
                       directional_calls=int(mask.sum()),directional_accuracy=float((directional[mask]*pnl[mask]>0).mean()) if mask.any() else None)
        if m=="bridge":
            for rival in ("original","fixed","zero"):
                other=pd.Series(-np.log(df[f"p_{rival}"]).to_numpy(),index=df.origin).resample("D").mean().dropna()
                result[m]["daily_loss_advantage_vs_"+rival]=paired(other,daily)
    return result


def execute(frames,out):
    records=[]
    date_panel={str(d):name for name,b in frames.items() for d in b.index.date}
    def encode(b,a,f):
        d,rec=apply(b,a,f)
        scores={"bridge":d.bridge,"fixed_bridge":d.fixed_bridge}
        rec["day"]=str(b.index[0].date())
        rec["panel"]=date_panel[rec.day.iloc[0]]
        records.append(rec)
        return d,scores
    run(frames,out,encode)
    labels=pd.concat(records,ignore_index=True)
    reports={}
    guarantees=[]
    for name,z in labels.groupby("panel"):
        models=["original","loaded","zero","fixed","bridge"]
        reports[name]=forecast_stats(z,models)
        for (date,seg,phase),g in z.groupby(["day","segment","phase"]):
            log_evidence=np.log(g[["p_original","p_loaded","p_zero"]]).sum(axis=0).to_numpy()
            marginal=np.logaddexp.reduce(np.log(PRIOR)+log_evidence)
            actual=np.log(g.p_bridge).sum()
            error=abs(actual-marginal)
            regret=max(log_evidence)-actual
            assert error<1e-9 and regret<=np.log(3)+1e-9
            guarantees.append(dict(day=date,segment=int(seg),phase=int(phase),n=len(g),error=error,regret=regret))
    reports["identity"]=dict(groups=len(guarantees),observations=len(labels),upper_bound=float(np.log(3)),
                             max_abs_error=max(g["error"] for g in guarantees),max_regret=max(g["regret"] for g in guarantees))
    (out/"predictive.json").write_text(json.dumps(reports,indent=2,allow_nan=False)+"\n")
    labels.to_csv(out/"predictions.csv.gz",index=False,compression={"method":"gzip","mtime":0})


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("scratch",type=Path);p.add_argument("out",type=Path)
    p.add_argument("--track",choices=["discovery","replication"],default="discovery")
    args=p.parse_args()
    execute(panels(args.scratch,args.track),args.out)
