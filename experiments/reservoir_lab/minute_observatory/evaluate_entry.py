"""Replay the frozen entry surgery and compute matched-fill sizing scenarios."""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from evidence import EntryOnly, evidence
HERE = Path(__file__).resolve().parent
LAB = HERE.parent
sys.path[:0] = [str(LAB/"tick_exit"), str(LAB/"adverse_impact")]
from experiment import get_panels, metrics
from session import activations, replay, verify_brain
from simulator import simulate


def run(scratch, out):
    verify_brain()
    out.mkdir(parents=True, exist_ok=True)
    trades, marks, traces = {}, {}, []
    for frame in get_panels(scratch).values():
        for day,b in frame.groupby(frame.index.date):
            day = str(day)
            assert day <= "2026-11-20"
            a = activations(b,"reservoir")
            e = evidence(a)
            raw = a.reservoir
            base, m = replay(b,raw,cost=6)
            control, control_marks, _ = simulate(b,raw,raw,-raw,policy=EntryOnly(raw))
            pd.testing.assert_frame_equal(base,control)
            pd.testing.assert_series_equal(m,control_marks)
            edit, changed, _ = simulate(b,raw,raw,-raw,policy=EntryOnly(e.corroborated))
            trades[day] = {"original":base,"corroborated":edit}
            marks[day] = {"original":m,"corroborated":changed}
            traces.append(e.assign(raw=raw))
    groups = {"earlier20":[d for d in trades if d < "2026-11"],"november14":[d for d in trades if d >= "2026-11"],
              "nov19":["2026-11-19"],"other13":[d for d in trades if d >= "2026-11" and d != "2026-11-19"]}
    assert [len(d) for d in groups.values()] == [20,14,1,13]
    result = {}
    for group,days in groups.items():
        dates=sorted(days)
        row={}
        led={}
        for name in ("original","corroborated"):
            led[name]=pd.concat([trades[d][name] for d in dates],ignore_index=True)
            paths=[marks[d][name] for d in dates]
            one=metrics(led[name],paths)
            doubled=led[name].copy()
            doubled[["net_usd","gross_usd"]] *= 2
            assert np.isclose(doubled.net_usd.sum(),doubled.gross_usd.sum()-12*len(doubled))
            two=metrics(doubled,[2*m for m in paths])
            row[name]={"one":one,"two":two}
        paired=led["original"].merge(led["corroborated"],on=["entry_time","side"],how="outer",indicator=True,suffixes=("_base","_edit"))
        shared=paired[paired._merge=="both"]
        assert (shared.net_usd_base==shared.net_usd_edit).all()
        missed=paired[paired._merge=="left_only"]
        added=paired[paired._merge=="right_only"]
        row["effects"]=dict(shared=len(shared),skipped=len(missed),skipped_net=missed.net_usd_base.sum(),
                            added=len(added),added_net=added.net_usd_edit.sum())
        result[group]=row
    result["passes"]=all((g["corroborated"]["one"]["net"]>max(0,g["original"]["one"]["net"])
                          and g["corroborated"]["one"]["marked_drawdown"]<1500)
                         for g in [result["earlier20"],result["november14"]])
    (out/"results.json").write_text(json.dumps(result,indent=2)+"\n")
    pd.concat(traces).to_csv(out/"activations.csv.gz",compression={"method":"gzip","mtime":0})
    pd.concat([t.assign(policy=k) for d in trades.values() for k,t in d.items()]).to_csv(out/"trades.csv",index=False)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("scratch",type=Path)
    p.add_argument("out",type=Path)
    args=p.parse_args()
    run(args.scratch,args.out)
