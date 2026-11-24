"""Trade-boundary interventions on the frozen failed-recovery circuit."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from chart import render
from routing import TradeMemory

HERE=Path(__file__).resolve().parent
LAB=HERE.parent
CORE=LAB.parent/"path_order"
sys.path[:0]=[str(LAB),str(LAB/"tick_exit"),str(LAB/"adverse_impact")]
from experiment import get_panels, metrics
from session import verify_brain, activations, ledger, minute, replay
from simulator import simulate
from failed_recovery.circuit import directional_state
from data import regular_hours
from evaluate import paired
from study import case, classify, fixed_stats, full_stats, match

CELLS={"continuous":(False,False),"local":(True,False),"fresh":(False,True),"both":(True,True)}
MODES=["original",*CELLS,"fixed_continuous","fixed_local"]
SIX=["2026-10-26","2026-10-27","2026-10-28","2026-10-29","2026-10-30","2026-11-02"]


def extension(path):
    receipt=json.loads((HERE/"capture_receipt.json").read_text())
    if not receipt["panel_ready"]:
        raise ValueError("registered six-date capture incomplete; see capture_receipt.json")
    if hashlib.sha256(path.read_bytes()).hexdigest()!=receipt["normalized_csv_sha256"]:
        raise ValueError("six-date capture checksum mismatch")
    b=regular_hours(pd.read_csv(path),SIX[0],SIX[-1])
    sizes=b.groupby(b.index.strftime("%Y-%m-%d")).size().to_dict()
    if sizes!=dict.fromkeys(SIX,390):
        raise ValueError(f"incomplete replication panel {sizes}")
    return b


def setup_origins(b,state):
    """Start-of-bar timestamp containing the shock's preceding close."""
    origin=None
    previous_low=np.nan
    pulses={}
    for i,(ts,low,pulse) in enumerate(zip(b.index,state.shock_end,state.failure_points,strict=True)):
        if pulse>0:
            assert origin is not None
            pulses[ts]=origin
        if np.isnan(low):
            origin=None
        elif low!=previous_low:
            origin=b.index[i-1]
        previous_low=low
    return pulses


def attribute(ref,edited):
    m=ref.merge(edited,on=["entry_time","side"],how="outer",indicator=True,
                suffixes=("_base","_new"),validate="one_to_one")
    shared=m[m._merge=="both"]
    added=m[m._merge=="right_only"]; skipped=m[m._merge=="left_only"]
    delta=shared.net_usd_new-shared.net_usd_base
    return dict(shared=len(shared), shared_delta=float(delta.sum()),
                shared_losers_delta=float(delta[shared.net_usd_base<0].sum()),
                shared_winners_delta=float(delta[shared.net_usd_base>0].sum()),
                added=len(added),added_net=float(added.net_usd_new.sum()),
                skipped=len(skipped),skipped_base_net=float(skipped.net_usd_base.sum()))


def run(scratch,out,panel):
    verify_brain()
    out.mkdir(exist_ok=True,parents=True)
    sources=get_panels(scratch)
    if panel:
        sources["replication"]=extension(panel)
    marks={}; trades={}; groups={}; charts=[]; checks=[]; event_audits=[]
    for key,frame in sources.items():
        for day,b in frame.groupby(frame.index.date):
            day=str(day)
            groups[day]="six" if key=="replication" else ("earlier20" if key=="discovery" else "november14")
            a=activations(b,"reservoir"); raw=a.reservoir
            states={s:directional_state(b,a,s) for s in (1,-1)}
            shocks={s:states[s].new_shock.to_numpy() for s in states}
            origins={s:setup_origins(b,states[s]) for s in states}
            chart={"date":day,"bars":[[minute(ts),*ohlcv,*[None if pd.isna(x) else float(x) for x in neuron]]
                for ts,ohlcv,neuron in zip(b.index,b.to_numpy().tolist(),
                           a[["reservoir","stock","charge","signed_release"]].to_numpy(),strict=True)],"layers":{}}
            for mode in MODES:
                if mode=="original":
                    t,m=replay(b,raw,cost=6.)
                    fixed={x.signal_time:(1 if x.side=="long" else -1) for x in t.itertuples()}
                    h=pd.Series(np.nan,index=b.index)
                else:
                    matched=mode.startswith("fixed_")
                    cell=mode.removeprefix("fixed_")
                    agent=TradeMemory(a,shocks,*CELLS[cell])
                    t,m,h=simulate(b,raw,states[1].hold,states[-1].hold,
                                   fixed_signals=fixed if matched else None,policy=agent)
                    audits=pd.DataFrame(agent.audit,index=b.index,
                                        columns=["gate_side","fresh_points","blocked","local_pulse"])
                    if matched:
                        ref=trades[day,"original"]
                        assert list(zip(t.entry_time,t.side))==list(zip(ref.entry_time,ref.side))
                        assert (t.exit_time.to_numpy()<=ref.exit_time.to_numpy()).all()
                    for row in t.itertuples():
                        if cell=="continuous" and row.reason=="hold":
                            signal=row.exit_time-pd.Timedelta(minutes=1)
                            start=origins[1 if row.side=="long" else -1][signal]
                            checks.append(dict(date=day,mode=mode,entry=row.entry_time,exit=row.exit_time,
                                               setup=start,predates=bool(start<row.entry_time)))
                    if not matched and cell!="continuous":
                        mask=audits.blocked | (audits.local_pulse>0) | (audits.gate_side!=0)
                        event_audits.append(audits.loc[mask].assign(mode=mode,raw=raw[mask]))
                assert np.isclose(m.iloc[-1],t.net_usd.sum())
                trades[day,mode],marks[day,mode]=classify(t,raw),m
                if mode != "fixed_continuous":
                    chart["layers"][mode]={"trades":ledger(t),"hold":[None if pd.isna(x) else float(x) for x in h]}
            charts.append(chart)
    for mode,old in [("continuous","full_volume"),("fixed_continuous","fixed_volume"),("original","original")]:
        expected=pd.read_csv(LAB/"failed_recovery/results"/f"{old}-trades.csv")
        actual=pd.concat([trades[d,mode] for d,g in groups.items() if g!="six"],ignore_index=True)
        for col in ["entry_time","exit_time","signal_time"]:
            assert pd.to_datetime(expected[col],utc=True).equals(pd.to_datetime(actual[col],utc=True))
        assert expected.side.tolist()==actual.side.tolist() and expected.reason.tolist()==actual.reason.tolist()
        np.testing.assert_array_equal(actual.net_usd,expected.net_usd)
    report={}
    days_by_group={g:[d for d in groups if groups[d]==g] for g in sorted(set(groups.values()))}
    days_by_group["nov19"]=["2026-11-19"]
    days_by_group["other13"]=[d for d in days_by_group["november14"] if d!="2026-11-19"]
    for group,dates in days_by_group.items():
        daily=pd.DataFrame({mode:[float(marks[d,mode].iloc[-1]) for d in dates] for mode in MODES},index=dates)
        led={mode:pd.concat([trades[d,mode] for d in dates],ignore_index=True) for mode in MODES}
        rows={}
        for mode in MODES:
            rows[mode]=metrics(led[mode],[marks[d,mode] for d in dates])
            if mode not in ("continuous","original"):
                reference="original" if mode.startswith("fixed_") else "continuous"
                rows[mode]["attribution"]=attribute(led[reference],led[mode])
        original_pairs = match(led["original"], led["both"])
        rows["both"]["against_original"] = full_stats(original_pairs)
        rows["both"]["against_prior"] = full_stats(match(led["continuous"], led["both"]))
        rows["fixed_local"]["paired_original_outcomes"] = fixed_stats(match(led["original"], led["fixed_local"]))
        delta=daily.both-daily.continuous
        provenance=[c for c in checks if c["date"] in dates and c["mode"]=="continuous"]
        report[group]=dict(rows=rows, factorial=dict(local_alone=float((daily.local-daily.continuous).sum()),
            fresh_alone=float((daily.fresh-daily.continuous).sum()),
            interaction=float((daily.both-daily.local-daily.fresh+daily.continuous).sum())),
            prior_exit_pulses=len(provenance),pulse_began_before_fill=sum(c["predates"] for c in provenance),
            combined_delta=float(delta.sum()),combined_delta_without_best_date=float(delta.sum()-delta.max()),
            best_increment_date=str(delta.idxmax()),paired_delta=paired(daily.both,daily.continuous))
    for mode in MODES:
        pd.concat([trades[d,mode] for d in sorted(groups)]).to_csv(out/f"{mode}.csv",index=False)
    pd.DataFrame(checks).to_csv(out/"exit-memory-audit.csv",index=False)
    pd.concat(event_audits).to_csv(out/"routing-events.csv.gz",compression={"method":"gzip","mtime":0})
    pd.DataFrame([{"date":d,"group":groups[d],**{m:marks[d,m].iloc[-1] for m in MODES}}
                  for d in sorted(groups)]).to_csv(out/"daily.csv",index=False)
    pairs = match(pd.concat([trades[d,"original"] for d in sorted(groups)], ignore_index=True),
                  pd.concat([trades[d,"fixed_local"] for d in sorted(groups)], ignore_index=True))
    winners = pairs[pairs.net_usd_base > 0]
    extremes = {"improvement":case(pairs.loc[pairs.delta.idxmax()]),
                "damaged_winner":case(winners.loc[winners.delta.idxmin()])}
    report["fixed_entry_examples"] = extremes
    (out/"results.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    render(sorted(charts,key=lambda c:c["date"]),extremes,out/"trade-memory.html")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("scratch",type=Path);p.add_argument("output",type=Path)
    p.add_argument("--panel",type=Path)
    args=p.parse_args()
    run(args.scratch,args.output,args.panel)
