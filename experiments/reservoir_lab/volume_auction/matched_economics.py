"""Matched timestamps isolate the incremental P&L of volume and calculate native NQ risk."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from transfer import load_year
from study import HERE,paired


def signed_delta(a,b):
    keys=["entry_time","side"]
    cols=keys+["net_usd","exit_time"]
    pairs=a[cols].merge(b[cols],on=keys,how="outer",suffixes=("_edit","_control"),
                         indicator=True,validate="one_to_one")
    same=pairs[pairs._merge=="both"]
    added=pairs[pairs._merge=="left_only"]; skipped=pairs[pairs._merge=="right_only"]
    delta=float(a.net_usd.sum()-b.net_usd.sum())
    shared=float(same.net_usd_edit.sum()-same.net_usd_control.sum())
    assert np.isclose(delta, shared+added.net_usd_edit.sum()-skipped.net_usd_control.sum())
    return dict(shared=len(same),shared_delta=shared,added=len(added),added_net=float(added.net_usd_edit.sum()),
                skipped=len(skipped),skipped_control_net=float(skipped.net_usd_control.sum()),net_delta=delta)


def marked_risk(b,t,pv,cost):
    # Only held marks differ from realized equity. Compute their dollar excursions and
    # join with realized changes at the actual exit opens.
    closed=pd.Series(0.,index=b.index)
    ix=pd.to_datetime(t.exit_time,utc=True)
    gross=pv*t.side.map({"long":1,"short":-1})*(t.exit-t.entry)
    closed.loc[ix]=(gross-cost).to_numpy()
    realized=closed.cumsum().to_numpy()
    offsets=np.zeros((len(b),4))
    for row in t.itertuples():
        start=b.index.get_loc(pd.Timestamp(row.entry_time));stop=b.index.get_loc(pd.Timestamp(row.exit_time))
        side=1 if row.side=="long" else -1
        offsets[start:stop]=(b.iloc[start:stop][["open","low","high","close"]].to_numpy()-row.entry)*pv*side-cost/2
    marks=offsets+realized[:,None]
    low=marks.min(axis=1);high=marks.max(axis=1);closing=marks[:,3]
    peak=np.maximum.accumulate(np.r_[0.,high])
    close_peak=np.maximum.accumulate(np.r_[0.,closing])[1:]
    mindd=float(max(np.max(np.maximum(peak[:-1],marks[:,0])-low),np.max(high-closing)))
    maxdd=float(np.max(peak[1:]-low))
    return dict(net=float(closing[-1]),gross=float(gross.sum()),trades=len(t),round_trip=cost,
                close_dd=float(np.max(close_peak-closing)),intraminute_min_dd=mindd,intraminute_max_dd=maxdd)


def compute(folder,nq=None):
    led=pd.read_csv(folder/"trades.csv.gz")
    day=pd.read_csv(folder/"daily.csv")
    report={}
    existing=json.loads((folder/"summary.json").read_text())
    for panel,t in led.groupby("panel"):
        result={}
        d=day[day.panel==panel].pivot(index="date",columns="model",values="net")
        for name,control in [("volume","equal_volume"),("cascade_volume","cascade_equal_volume"),("pulse_weighted","pulse_equal_mass")]:
            z=signed_delta(t[t.model==name],t[t.model==control])
            z["daily_difference"]=paired(d[name],d[control])
            result[name]=z
        report[panel]={"volume_attribution":result}
        if nq is not None:
            b=load_year(nq)[panel]
            native={}
            for m,group in t.groupby("model"):
                same=marked_risk(b,group,2.,6.)
                for key in ["net","close_dd","intraminute_max_dd"]:
                    assert np.isclose(same[key],existing[panel][m][key])
                native[m]=marked_risk(b,group,20.,14.50)
                native[m]["stressed_net"]=native[m]["net"]-10*len(group)
            report[panel]["native_nq"]=native
    (folder/"attribution.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("directory",type=Path);p.add_argument("--nq",type=Path)
    a=p.parse_args();compute(a.directory,a.nq)
