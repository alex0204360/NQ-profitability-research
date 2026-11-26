"""Decompose the specific 10:45 trade from its original entry to original exit."""
import json
from pathlib import Path
import sys
from run import ExitHead, RestartHead, inputs, panels
import pandas as pd


def trace(scratch, out):
    b = panels(scratch,"discovery")["november14"].loc["2026-11-19"]
    ledger = pd.read_csv(out/"discovery"/"trades.csv.gz")
    t, = ledger[(ledger.model=="original") & ledger.entry_time.str.startswith("2026-11-19 10:45")].itertuples()
    w = b[(b.index>=pd.Timestamp(t.entry_time))&(b.index<pd.Timestamp(t.exit_time))]
    sampled = inputs(b)
    result = dict(entry=t.entry,exit=t.exit,net=t.net_usd,highest_held_close=float(w.close.max()),
                  highest_close_time=w.close.idxmax().isoformat(),closetoopen_gaps_points=float(t.exit-t.entry-(w.close-w.open).sum()),
                  summed_bodies_points=float((w.close-w.open).sum()))
    for cls in (ExitHead,RestartHead):
        head=cls(sampled,True)
        for i in b.index.get_indexer(w.index):
            head.close_scores(i,0.,1.,{"side":1},None,True,0.,0.)
        row = max(head.activations,key=lambda row:row[2])
        result[cls.__name__]={"peak_evidence":row[2],"peak_time":b.index[row[0]].isoformat()}
    (out/"nov19-long.json").write_text(json.dumps(result,indent=2)+"\n")


if __name__=="__main__":
    trace(Path(sys.argv[1]),Path(sys.argv[2]))
