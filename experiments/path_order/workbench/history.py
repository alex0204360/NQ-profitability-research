"""Reproduce the 34 exposed sessions and verify every frozen fill before chart export."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from session import CORE, max_drawdown, run_day, save_chart, verify_brain
from data import discovery, regular_hours


def november(directory, receipt, start, end):
    import hashlib
    path = directory / "bars.csv"
    expected = json.loads((CORE / receipt).read_text())["csv_sha256"]
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError(f"Capture mismatch: {path}")
    return regular_hours(pd.read_csv(path), start, end)


def summary(rows, marks, name):
    days = [r[name] for r in rows]
    path = []
    offset = 0.
    for m in marks:
        path.extend(offset + m.to_numpy())
        offset += m.iloc[-1]
    return dict(trades=sum(d["trades"] for d in days), net=offset, drawdown=max_drawdown(path),
                worst_day=min(d["net"] for d in days), gap_exits=sum(d["gap_exits"] for d in days),
                cutoff_exits=sum(d["cutoff_exits"] for d in days))


def build(scratch, out):
    verify_brain()
    sets = [
        ("discovery", discovery(scratch / "mnq")),
        ("november-extension", pd.concat([
            november(scratch/"mnq-extension1","november-extension/capture-1.json","2026-11-03","2026-11-06"),
            november(scratch/"mnq-extension2","november-extension/capture-2.json","2026-11-09","2026-11-13")])),
        ("november", november(scratch/"mnq-november","november/capture-receipt.json","2026-11-16","2026-11-20"))]
    charts, summary_by_panel, rows, marks = [], {}, [], [[], []]
    for name,bars in sets:
        expected = pd.read_csv(CORE/name/"reservoir-delay0.csv")
        trades = []
        begin = len(rows)
        for _,day in bars.groupby(bars.index.date):
            chart, stats, base, _, equity, guarded, _ = run_day(day)
            charts.append(chart)
            rows.append(stats)
            marks[0].append(equity)
            marks[1].append(guarded)
            trades.append(base)
        actual = pd.concat(trades, ignore_index=True)
        for k in ["signal_time","entry_time","exit_time"]:
            assert pd.to_datetime(actual[k],utc=True).tolist() == pd.to_datetime(expected[k],utc=True).tolist()
        for k in ["entry","exit","gross_usd"]:
            np.testing.assert_allclose(actual[k].astype(float), expected[k])
        assert actual.side.tolist() == expected.side.tolist()
        np.testing.assert_allclose(actual.net_usd.astype(float), expected.net_usd-3)
        summary_by_panel[name] = {n:summary(rows[begin:],m[begin:],n) for n,m in zip(["base","guard"],marks)}
    nov = next(i for i,r in enumerate(rows) if r["date"].startswith("2026-11"))
    summary_by_panel["november_combined"] = {n:summary(rows[nov:],m[nov:],n) for n,m in zip(["base","guard"],marks)}
    out.mkdir(exist_ok=True, parents=True)
    (out/"historical-results.json").write_text(json.dumps(dict(panels=summary_by_panel, sessions=rows), indent=2)+"\n")
    save_chart(charts,out/"MNQ-trade-chart.html")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("scratch", type=Path)
    p.add_argument("out", type=Path)
    args = p.parse_args()
    build(args.scratch,args.out)
