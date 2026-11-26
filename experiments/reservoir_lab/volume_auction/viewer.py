"""Build a standalone inspector for unmodified ledgers and opposing network heads."""
import json
from pathlib import Path
import pandas as pd

from study import HERE,panels

NAMES={"original":"Original reservoir","volume":"Inventory discharge","cascade_volume":"Forward cascade",
       "pulse_weighted":"Volume-weighted launch","pulse_equal_mass":"Equal-mass launch","pulse_v08_sym":"Price-only launch"}
CONTROL={"volume":"equal_volume","cascade_volume":"cascade_equal_volume","pulse_weighted":"pulse_equal_mass",
         "pulse_equal_mass":"pulse_equal_mass","pulse_v08_sym":"pulse_v08_long","original":"original"}


def build(scratch,out):
    data={}
    for track in ["discovery","disjoint","transfer","postfreeze"]:
        folder=HERE/"results"/track
        report=json.loads((folder/"summary.json").read_text())
        attribution=json.loads((folder/"attribution.json").read_text())
        days=pd.read_csv(folder/"daily.csv")
        for panel,r in report.items():
            dq=days[days.panel==panel];nq=track=="transfer";native=attribution[panel].get("native_nq",{})
            g=data[panel]=dict(nq=nq,names=NAMES,models={},sessions={})
            for name in NAMES:
                x=dq[dq.model==name]
                g["models"][name]=dict(days=x.date.tolist(),trades=x.trades.tolist(),gross=(x.net+x.trades*6).mul(10 if nq else 1).tolist(),
                                      dd=(native.get(name) or r[name])["intraminute_max_dd"],
                                      control=CONTROL[name],control_net=(native.get(CONTROL[name]) or r[CONTROL[name]])["net"])
        if track=="transfer":continue
        if track=="postfreeze":
            from postfreeze import load_capture
            tape={"nov25":load_capture(scratch/"nov25-auction-original")}
        else:
            tape=panels(scratch,"replication" if track=="disjoint" else "discovery")
        trace=pd.read_csv(folder/"activations.csv.gz",index_col=0)
        trades=pd.read_csv(folder/"trades.csv.gz")
        for panel,b in tape.items():
            for day,frame in b.groupby(b.index.date):
                tid=frame.index.map(str)
                local=trace.loc[tid].copy()
                # Cascade has a proposed move only on a qualified event.
                local["cascade_score"]=local.volume_event*local.volume_reward
                local["cascade_control"]=local.equal_volume_event*local.equal_volume_reward
                rows=frame[["open","high","low","close","volume"]].copy()
                cols=["original","score","equal_score","cascade_score","cascade_control","pulse_weighted","pulse_equal_mass","pulse_v08_sym","pulse_v08_long"]
                for col in cols:rows[col]=local[col].to_numpy()
                day_trades=trades[trades.entry_time.str.startswith(str(day))]
                ledger={name:[[q.entry_time[11:16],q.exit_time[11:16],q.side,q.net_usd] for q in group.itertuples()]
                        for name,group in day_trades.groupby("model")}
                data[panel]["sessions"][str(day)]=dict(t=frame.index.strftime("%H:%M").tolist(),rows=json.loads(rows.to_json(orient="values",double_precision=3)),ledger=ledger)
    out.write_text((HERE/"template.html").read_text().replace("__DATA__",json.dumps(data,separators=(",",":"),allow_nan=False)))


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser();p.add_argument("scratch",type=Path);p.add_argument("out",type=Path)
    args=p.parse_args();build(args.scratch,args.out)
