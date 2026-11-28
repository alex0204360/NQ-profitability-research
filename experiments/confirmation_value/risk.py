"""Reconstruct fixed-entry risk from the archived capacity ledger and OHLC."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.hold_work.metrics import COSTS, drawdown_bounds, normalize_trades, paired_effects

KEY = ["source", "delay", "trade_id"]
OHLC = ["open", "low", "high", "close"]


def tag_source(frame):
    return frame.assign(source=np.where(frame.panel.eq("external"), "external60", "discovery40"))


def outcomes(path, score):
    data = pd.read_csv(path)
    data["issue"] = pd.to_datetime(data.issue, utc=True)
    if data.duplicated(KEY).any():
        raise ValueError(f"Multiple decision rows for one fixed entry in {path}")
    usable = data[score].lt(0)
    common = ["reversal", "y"]
    if score == "survival_grid":
        common += ["remaining", "previous_grid", "unweighted", "survival_feasibility", "survival_laplace"]
    usable &= data[common].notna().all(axis=1)
    retained = KEY + ["issue"] + [name for name in ("early_time", "early_price") if name in data]
    return data.loc[usable, retained].copy()


def edit(original, decisions, fills):
    joined = decisions.merge(fills, on=KEY + ["issue"], validate="one_to_one", how="left", indicator=True)
    if not joined["_merge"].eq("both").all():
        raise ValueError("Selected decision is absent from the original open-position path")
    if {"early_price", "early_time"} <= set(decisions):
        recorded_time = pd.to_datetime(joined.early_time, utc=True)
        if not recorded_time.equals(joined.next_executable_time):
            raise ValueError("Recorded decision and original tape disagree on executable time")
        np.testing.assert_array_equal(joined.early_price, joined.next_executable_price)
    joined = joined.dropna(subset=["next_executable_time", "next_executable_price"])
    edit_rows = joined.set_index(KEY, verify_integrity=True)
    target = original.set_index(KEY, verify_integrity=True).copy()
    if not edit_rows.index.isin(target.index).all():
        raise ValueError("Selected decision is absent from the original trade ledger")
    chosen = target.loc[edit_rows.index]
    if not (
        chosen.entry_time.le(edit_rows.issue) & edit_rows.next_executable_time.ge(edit_rows.issue)
        & chosen.exit_time.ge(edit_rows.next_executable_time)
    ).all():
        raise ValueError("Edited exit is outside the original trade")
    target.loc[edit_rows.index, "exit_time"] = edit_rows.next_executable_time
    target.loc[edit_rows.index, "exit"] = edit_rows.next_executable_price
    sign = target.side.map({"long": 1, "short": -1})
    target["gross_usd"] = 2*sign*(target.exit-target.entry)
    target["net_usd"] = target.gross_usd-6
    return target.reset_index(), len(edit_rows)


def risk(ledger, tape, cost):
    realized, rows = 0., []
    previous_exit = tape.index[0]
    for t in ledger.sort_values("entry_time").itertuples():
        if t.entry_time < previous_exit:
            raise ValueError("Fixed ledger has overlapping positions")
        start, finish = tape.index.get_loc(t.entry_time), tape.index.get_loc(t.exit_time)
        if finish <= start or tape.open.iat[start] != t.entry or tape.open.iat[finish] != t.exit:
            raise ValueError("Ledger execution does not match the OHLC open")
        direction = 1 if t.side == "long" else -1
        points = tape.iloc[start:finish][OHLC].to_numpy()-t.entry
        marked = realized-cost/2+2*direction*points
        for open_, low, high, close in marked:
            rows.append((open_, min(low, high), max(low, high), close, True))
        pre_exit = realized + t.gross_usd-cost/2
        realized = pre_exit-cost/2
        rows.extend([(pre_exit,)*4+(False,), (realized,)*4+(True,)])
        previous_exit = t.exit_time
    np.testing.assert_allclose(realized, (ledger.gross_usd-cost).sum(), rtol=0, atol=1e-9)
    return drawdown_bounds(pd.DataFrame(rows, columns=[*OHLC, "is_close"]))


def run(experiments, output):
    capacity = experiments/"capacity/results"
    decisions_path = experiments/"confirmation_value/results/decisions.csv.gz"
    paths = {
        "original_trades": capacity/"trades.csv.gz",
        "original_activations": capacity/"activations.csv.gz",
        "market_tape": capacity/"scores.csv.gz",
        "prior_grid": experiments/"reachable_value/results/predictions.csv.gz",
        "confirmation": decisions_path,
    }
    original = tag_source(pd.read_csv(paths["original_trades"]).query("model == 'original'").copy())
    for field in ("entry_time", "exit_time"):
        original[field] = pd.to_datetime(original[field], utc=True)
    fills = tag_source(pd.read_csv(paths["original_activations"], usecols=[
        "panel", "delay", "trade_id", "bar_start", "next_executable_time", "next_executable_price",
    ]))
    fills["issue"] = pd.to_datetime(fills.pop("bar_start"), utc=True) + pd.Timedelta(minutes=1)
    fills["next_executable_time"] = pd.to_datetime(fills.next_executable_time, utc=True)
    tape = tag_source(pd.read_csv(paths["market_tape"], usecols=["panel", "bar_start", *OHLC]))
    tape["bar_start"] = pd.to_datetime(tape.bar_start, utc=True)
    tapes = {source: group.set_index("bar_start")[OHLC].sort_index() for source, group in tape.groupby("source")}
    if not all(frame.index.is_unique for frame in tapes.values()):
        raise ValueError("Duplicate candle in source archive")
    models = {"original": original}
    chosen = {}
    for name, score in (("prior_grid", "grid"), ("survival_grid", "survival_grid")):
        path = paths["prior_grid" if name == "prior_grid" else "confirmation"]
        ledger, count = edit(original, outcomes(path, score), fills)
        models[name] = ledger
        chosen[name] = count

    report = {}
    for (source, delay), base in original.groupby(["source", "delay"]):
        normalized = normalize_trades(base)
        cell = report.setdefault(source, {})[str(delay)] = {}
        for name, ledger in models.items():
            trades = ledger.loc[ledger.source.eq(source) & ledger.delay.eq(delay)].copy()
            effects = paired_effects(normalized, normalize_trades(trades))
            gains = trades.set_index("trade_id").gross_usd-base.set_index("trade_id").gross_usd
            model = cell[name] = dict(
                trades=len(trades), changed_exits=effects["changed_exit_count"],
                gross_improvement_usd=float(gains.sum()),
                without_three_best_improvements_usd=float(gains.sum()-gains.nlargest(3).clip(lower=0).sum()),
                costs={},
            )
            for cost in COSTS:
                net = trades.gross_usd-cost
                model["costs"][str(cost)] = dict(
                    **effects["costs"][str(cost)],
                    candidate_net_without_three_best_trades_usd=float(net.sum()-net.nlargest(3).clip(lower=0).sum()),
                    **risk(trades, tapes[source], cost),
                )
    result = {
        "inputs_sha256": {label: hashlib.sha256(path.read_bytes()).hexdigest() for label, path in paths.items()},
        "selected_with_executable_price": chosen,
        "results": report,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("experiments", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    run(args.experiments, args.output)
