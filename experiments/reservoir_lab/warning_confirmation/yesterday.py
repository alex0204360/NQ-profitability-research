"""Rebuild the original scorecard and frozen Nov 23 counterfactuals from retained bytes."""
import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import sys

import pandas as pd

HERE = Path(__file__).resolve().parent
LAB = HERE.parent
sys.path[:0] = [str(LAB.parents[1]), str(LAB/"tick_exit"), str(LAB/"adverse_impact")]
from experiment import metrics
from paper_day import FIELDS, prepare, run_day
from session import activations, verify_brain
from simulator import simulate
from experiments.reservoir_lab.failed_recovery.circuit import directional_state
from experiments.reservoir_lab.trade_memory.routing import TradeMemory


def score(source, out):
    ref = LAB/"paper_sessions/2026-11-23"
    frozen = json.loads((ref/"scorecard.json").read_text())
    payload = source.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == frozen["source_sha256"]
    item, = json.loads(payload)["chart"]["result"]
    assert item["meta"]["symbol"] == "MNQZ26.CME"
    q, = item["indicators"]["quote"]
    rows = pd.DataFrame({k:q[k] for k in FIELDS})
    rows["timestamp_utc"] = pd.to_datetime(item["timestamp"], unit="s", utc=True)
    rows["contract"] = "MNQZ26"
    verify_brain()
    b = prepare(rows, date(2026,11,23), "MNQZ26", "start")
    _, stats, base, guard, equity, guarded, _ = run_day(b)
    assert all(frozen[k] == v for k,v in stats.items())
    for name,t in [("base",base), ("guard",guard)]:
        assert t.to_csv(index=False) == (ref/f"{name}-trades.csv").read_text()
    a = activations(b, "reservoir")
    states = {s: directional_state(b,a,s) for s in (1,-1)}
    previous = TradeMemory(a,{s:t.new_shock.to_numpy() for s,t in states.items()}, True,True)
    t, m, _ = simulate(b, a.reservoir, states[1].hold, states[-1].hold, policy=previous)
    out.mkdir(exist_ok=True,parents=True)
    t.to_csv(out/"previous-combined-trades.csv",index=False)
    result = {}
    for name,trades,marks in [("original",base,equity),("daily_guard",guard,guarded),("previous_combined",t,m)]:
        result[name] = dict(**metrics(trades,[marks]), winners=int((trades.net_usd>0).sum()),
                            gross=float(trades.gross_usd.sum()), friction=6*len(trades))
        assert result[name]["gross"] - result[name]["friction"] == result[name]["net"]
    (out/"as-is.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print(json.dumps(result,indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    score(args.source,args.out)
