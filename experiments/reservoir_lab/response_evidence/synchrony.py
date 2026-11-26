"""Two separate reservoirs measuring the same index on different contracts."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from run import activations, bounds, comparison, replay, simulate


from agreement import Agreement


def evaluate_pair(frame, root, out):
    path = root/"NQ.csv"
    assert hashlib.sha256(path.read_bytes()).hexdigest()=="583cd788b035c4b5ca612f8bb0e3e366d627348851c04d68bca295a5db116f61"
    nq = pd.read_csv(path)
    nq.index = pd.DatetimeIndex(pd.to_datetime(nq.pop("datetime"),utc=True)).tz_convert(frame.index.tz)
    assert nq.index.is_unique and nq.index.is_monotonic_increasing
    assert np.isfinite(nq.to_numpy()).all() and (nq.volume>=0).all()
    assert ((nq.high>=nq[["close","open"]].max(axis=1)) & (nq.low<=nq[["close","open"]].min(axis=1))).all()
    kept, dropped, daily, ledgers = [], [], [], {}
    for date, micro in frame.groupby(frame.index.date):
        if not micro.index.isin(nq.index).all():
            dropped.append(str(date))
            continue
        kept.append(micro)
        raw = activations(micro,"reservoir").reservoir
        peer = activations(nq.loc[micro.index],"reservoir")
        models = {}
        for name, score, veto in (("both",peer.reservoir,True),("entry_only",peer.reservoir,False),
                                  ("peer_price",peer.trend,True),("self_check",raw,True)):
            t,_,_ = simulate(micro,raw,raw,-raw,policy=Agreement(score,veto))
            models[name] = t
        models["micro"],_ = replay(micro,raw,cost=6.)
        models["nq_only"],_ = replay(micro,peer.reservoir,cost=6.)
        for name,t in models.items():
            ledgers.setdefault(name,[]).append(t)
            daily.append(dict(date=str(date),model=name,net=t.net_usd.sum(),trades=len(t)))
        pd.testing.assert_frame_equal(models["self_check"].drop(columns="reason"),models["micro"].drop(columns="reason"),check_dtype=False)
    day = pd.DataFrame(daily).pivot(index="date",columns="model",values="net")
    b = pd.concat(kept)
    stats = {"included_dates":list(day.index),"missing_nq_dates":dropped,"models":{}}
    for name,parts in ledgers.items():
        t = pd.concat([t for t in parts if len(t)],ignore_index=True)
        row = bounds(b,t)
        row.update(trades=len(t),expectancy=row["net"]/len(t),net_at_9=row["net"]-3*len(t),
                   daily_interval_vs_cash=comparison(day[name],0),without_best_day=row["net"]-day[name].max())
        for other in ("micro","nq_only","peer_price","entry_only"):
            row["daily_interval_vs_"+other]=comparison(day[name],day[other])
        stats["models"][name]=row
    main=stats["models"]["both"]
    stats["passes"]=bool(len(day)>=20 and main["trades"]>=50 and main["net_at_9"]>0 and main["intraminute_max_dd"]<1500
                         and all(main["daily_interval_vs_"+name][0]>0 for name in ("cash","micro","nq_only","peer_price")))
    (out/"cross-market.json").write_text(json.dumps(stats,indent=2)+"\n")
    pd.DataFrame(daily).to_csv(out/"cross-market-daily.csv",index=False)
    pd.concat([t.assign(model=m) for m,parts in ledgers.items() for t in parts if len(t)]).to_csv(out/"cross-market-trades.csv.gz",index=False,compression={"method":"gzip","mtime":0})
