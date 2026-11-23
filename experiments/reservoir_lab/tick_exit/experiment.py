"""Replay registered discovery tape; net is one MNQ after $6 modeled friction."""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from neuron import tick_exit

HERE = Path(__file__).resolve().parent
CORE = HERE.parents[1] / "path_order"
sys.path.insert(0, str(CORE / "workbench"))
from history import november
from session import FRICTION, activations, ledger, max_drawdown, minute, replay, verify_brain
from data import discovery

FOCUS = "2026-11-19"


def get_panels(scratch):
    return {
        "discovery": discovery(scratch / "mnq"),
        "november-extension": pd.concat([
            november(scratch/"mnq-extension1", "november-extension/capture-1.json", "2026-11-03", "2026-11-06"),
            november(scratch/"mnq-extension2", "november-extension/capture-2.json", "2026-11-09", "2026-11-13")]),
        "november": november(scratch/"mnq-november", "november/capture-receipt.json", "2026-11-16", "2026-11-20"),
    }


def compare_entries(base, candidate):
    merged = base.merge(candidate, how="outer", on=["entry_time","side"], suffixes=("_ref","_edit"),
                        indicator=True, validate="one_to_one")
    shared = merged[merged._merge == "both"]
    earlier = shared[shared.exit_time_edit < shared.exit_time_ref]
    removed = merged[merged._merge == "left_only"]
    added = merged[merged._merge == "right_only"]
    def outcome(g):
        return {"count":len(g), "net_delta":float((g.net_usd_edit-g.net_usd_ref).sum())}
    return dict(common=len(shared), earlier_on_original_winners=outcome(earlier[earlier.net_usd_ref>0]),
                earlier_on_original_nonwinners=outcome(earlier[earlier.net_usd_ref<=0]),
                common_net_delta=float((shared.net_usd_edit-shared.net_usd_ref).sum()),
                original_only=len(removed), original_only_net=float(removed.net_usd_ref.sum()),
                candidate_only=len(added), candidate_only_net=float(added.net_usd_edit.sum()))


def metrics(trades, daily_marks):
    offset = 0.
    path = []
    for marks in daily_marks:
        path.extend(offset + marks.to_numpy())
        offset += marks.iloc[-1]
    return dict(trades=len(trades), net=offset, net_per_trade=offset/len(trades) if len(trades) else None,
                marked_drawdown=max_drawdown(path), gap_exits=int((trades.reason=="gap").sum()),
                profitable_sessions=sum(float(m.iloc[-1])>0 for m in daily_marks))


def render(charts, target):
    # Reuse the frozen offline viewer. Its second trade layer displays this candidate.
    page = (CORE/"workbench/viewer.html").read_text()
    for old, new in [
        (">Guarded</button>", ">Tick exit</button>"),
        ("MNQ Reservoir Replay", "MNQ Reservoir · Tick Exit Study"),
        ("The plot shows the forecast", "Tick exit adds four ReLUs that zero evidence within one tick and copy forecasts of two ticks or more. The selected model supplies the forecast"),
        ("let sessionIndex = sessions.length - 1;", 'let sessionIndex = sessions.findIndex(s => s.date === "2026-11-19");'),
        ("return current()?.bars || [];", 'return current()?.[mode === "guard" ? "editedBars" : "bars"] || [];'),
    ]:
        if old not in page:
            raise ValueError(f"viewer mismatch: {old}")
        page = page.replace(old,new)
    payload = json.dumps({"sessions":charts}, separators=(",",":"), allow_nan=False)
    target.write_text(page.replace("__REPLAY_DATA__",payload))


def run(scratch, out):
    verify_brain()
    out.mkdir(parents=True, exist_ok=True)
    charts, days, trades, marks = [], [], {}, {}
    for panel,bars in get_panels(scratch).items():
        for day,b in bars.groupby(bars.index.date):
            date = str(day)
            a = activations(b,"reservoir")
            edited = tick_exit(a.reservoir)
            chart = {"date":date,"lock":None}
            day_stats = {"date":date,"panel":panel}
            for name,s,layer,bars_key in [("original",a.reservoir,"base","bars"),("candidate",edited,"guard","editedBars")]:
                t,m = replay(b,s,delay=0,cost=FRICTION)
                trades[name,date],marks[name,date] = t,m
                chart[layer] = ledger(t)
                chart[bars_key] = [[minute(i),*row,None if pd.isna(score) else round(score,8),*neurons]
                    for i,row,score,neurons in zip(b.index,b.to_numpy().tolist(),s,
                        a[["stock","charge","signed_release"]].round(8).to_numpy().tolist(),strict=True)]
                day_stats[name] = float(m.iloc[-1])
            if date == FOCUS:
                trace = b.join(a[["reservoir","scale","stock","charge","signed_release"]]).join(edited)
                trace.to_csv(out/"nov19-trace.csv", index_label="bar_start_et")
            days.append(day_stats)
            charts.append(chart)
        ref = pd.read_csv(CORE/panel/"reservoir-delay0.csv")
        actual = pd.concat([trades["original",d["date"]] for d in days if d["panel"] == panel],ignore_index=True)
        for c in ["entry_time","exit_time","signal_time"]:
            assert pd.to_datetime(ref[c],utc=True).equals(pd.to_datetime(actual[c],utc=True))
        np.testing.assert_array_equal(actual.side,ref.side)
        np.testing.assert_allclose(actual.net_usd.astype(float),ref.net_usd-3)
    masks = {
        "discovery":[d["date"] for d in days if d["panel"]=="discovery"],
        "november":[d["date"] for d in days if d["date"].startswith("2026-11")],
        "november_except_focus":[d["date"] for d in days if d["date"].startswith("2026-11") and d["date"]!=FOCUS],
        "focus":[FOCUS],
    }
    results = {}
    for group,dates in masks.items():
        block = {name:pd.concat([trades[name,day] for day in dates],ignore_index=True)
                 for name in ["original","candidate"]}
        results[group] = {name:metrics(t,[marks[name,d] for d in dates]) for name,t in block.items()}
        results[group]["attribution"] = compare_entries(block["original"],block["candidate"])
    for name in ["original","candidate"]:
        pd.concat([trades[name,d["date"]] for d in days]).to_csv(out/f"{name}-trades.csv",index=False)
    pd.DataFrame(days).to_csv(out/"daily.csv",index=False)
    (out/"results.json").write_text(json.dumps(results,indent=2,allow_nan=False)+"\n")
    render(charts,out/"comparison.html")


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scratch",type=Path)
    parser.add_argument("out",type=Path)
    args=parser.parse_args()
    run(args.scratch,args.out)
