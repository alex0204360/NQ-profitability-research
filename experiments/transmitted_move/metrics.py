"""Evaluate frozen transmitted-move opportunities and their matched execution ledger."""

from __future__ import annotations

import argparse
from collections.abc import Iterable
import json
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.hold_work.metrics import _svg_series
from experiments.intraminute.run import load

DELAYS = (0, 1, 9, 60)
COSTS = (3, 6, 9)
SECONDS = pd.Timedelta(seconds=1)
POINT_VALUE = 2.0
SIDES = {
    "candidate": "action", "leader": "direction", "always_long": "always_long",
    "mnq_body": "body", "anchor_midpoint": "anchor_direction",
}


def block_indexes(n: int) -> np.ndarray:
    """Five-session circular blocks with one shared draw for every comparison."""
    starts = np.random.default_rng(604).integers(n, size=(10_000, (n + 4) // 5, 1))
    return ((starts + np.arange(5)) % n).reshape(10_000, -1)[:, :n]


def interval(daily_delta: pd.Series, blocks: np.ndarray) -> dict:
    sample = daily_delta.to_numpy()[blocks].mean(axis=1)
    return {"total_usd": float(daily_delta.sum()), "mean_daily_usd": float(daily_delta.mean()),
            "interval95_daily_usd": np.quantile(sample, [.025, .975]).tolist()}


def tape_for_fills(fills: pd.DataFrame, tape: pd.DataFrame) -> list[np.ndarray]:
    slices = []
    for row in fills.itertuples():
        entry = tape.index.get_loc(row.entry_time)
        exit_ = tape.index.get_loc(row.exit_time)
        if exit_ <= entry or tape.open.iat[entry] != row.entry or tape.open.iat[exit_] != row.exit:
            raise ValueError("Fill disagrees with observed MNQ open")
        slices.append(tape.iloc[entry:exit_][["open", "high", "low", "close"]].to_numpy().T)
    return slices


def exposure(fills: pd.DataFrame, slices: list[np.ndarray], sides: pd.Series, cost: int) -> dict:
    """Use open fills and intratrade OHLC, with no imputation on missing seconds."""
    marked_bars = []
    realized = 0.0
    missing_seconds = 0
    gapped_trades = 0
    for row, tape, side in zip(fills.itertuples(), slices, sides, strict=True):
        if not side:
            continue
        duration = int((row.exit_time - row.entry_time) / SECONDS)
        missing = duration - tape.shape[1]
        if missing < 0:
            raise ValueError("Trade duration shorter than its observed tape")
        missing_seconds += missing
        gapped_trades += bool(missing)
        open_, high, low, close = (
            realized - cost / 2 + POINT_VALUE * side
            * (tape - row.entry)
        )
        marked_bars.append(np.column_stack(
            [open_, np.minimum(high, low), np.maximum(high, low), close,
             np.ones(tape.shape[1], dtype=bool)]
        ))
        exit_mark = realized + POINT_VALUE * side * (row.exit - row.entry) - cost / 2
        realized = exit_mark - cost / 2
        marked_bars.append(np.array([
            [exit_mark, exit_mark, exit_mark, exit_mark, False],
            [realized, realized, realized, realized, True],
        ]))
    marked = lower = upper = 0.0
    if marked_bars:
        opened, low, high, close, close_mark = np.concatenate(marked_bars).T
        close_marks = np.r_[0.0, close[close_mark.astype(bool)]]
        marked = float(np.max(np.maximum.accumulate(close_marks) - close_marks))
        previous_high = np.maximum.accumulate(np.r_[0.0, high])[:-1]
        peak_at_open = np.maximum(previous_high, opened)
        lower = float(np.maximum(peak_at_open - low, high - close).max())
        upper = float((np.maximum(peak_at_open, high) - low).max())
    return {
        "observed_close_drawdown_usd": marked,
        "observed_intrabar_drawdown_lower_usd": lower,
        "observed_intrabar_drawdown_upper_usd": upper,
        "trades_with_missing_held_seconds": gapped_trades,
        "missing_held_seconds": missing_seconds,
        "observed_fill_net_usd": realized,
    }


def describe_overlapping(rows: pd.DataFrame) -> dict:
    filled = rows.loc[rows["entry"].notna() & rows["exit"].notna()]
    returns = filled["exit"] - filled["entry"]
    signed = {}
    for model, column in SIDES.items():
        points = filled[column] * returns
        signed[model] = {
            "mean_signed_points": float(points.mean()) if len(points) else None,
            "median_signed_points": float(points.median()) if len(points) else None,
            "positive_fraction": float(points.gt(0).mean()) if len(points) else None,
        }
    return {
        "signals": len(rows), "sessions": int(rows["date"].nunique()), "priced_labels": len(filled),
        "missing_entries": int(rows["entry"].isna().sum()), "late_exits": int(rows["late_exit"].sum()),
        "unresolved_exits": int(rows["unresolved"].sum()), "after_cutoff": int(rows["after_cutoff"].sum()),
        "matched_open_to_open_returns": signed,
    }


def independent_acceptance(rows: pd.DataFrame) -> pd.Series:
    """Replay occupancy from each date's immutable requests and priced outcomes."""
    accepted = pd.Series(False, index=rows.index)
    for (date, _), day in rows.groupby(["date", "delay"], sort=False):
        busy_until = pd.Timestamp(f"{date} 09:30", tz="America/New_York")
        cutoff = pd.Timestamp(f"{date} 15:55", tz="America/New_York")
        for row in day.sort_values("signal").itertuples():
            if row.signal < busy_until:
                continue
            accepted.at[row.Index] = True
            if pd.isna(row.entry_time):
                busy_until = row.requested_entry + 2 * SECONDS
            elif row.unresolved:
                busy_until = cutoff
            else:
                busy_until = row.exit_time
    return accepted


def evaluate_portfolio(rows: pd.DataFrame, tape: pd.DataFrame, dates: list[str],
                       blocks: np.ndarray) -> tuple[dict, pd.DataFrame]:
    accepted = rows.loc[rows["accepted"]].sort_values(["entry_time", "signal"])
    fills = accepted.loc[accepted["entry"].notna() & accepted["exit"].notna()].copy()
    unresolved = accepted.loc[accepted["unresolved"]]
    slices = tape_for_fills(fills, tape)
    if not fills.empty and (
        fills["entry_time"].iloc[1:].to_numpy() < fills["exit_time"].iloc[:-1].to_numpy()
    ).any():
        raise ValueError("Accepted ledger contains overlapping positions")
    daily = pd.DataFrame(index=pd.Index(dates, name="date"))
    daily["accepted_orders"] = accepted.groupby("date").size().reindex(dates, fill_value=0)
    daily["filled_round_trips"] = fills.groupby("date").size().reindex(dates, fill_value=0)
    daily["unresolved_exits"] = unresolved.groupby("date").size().reindex(dates, fill_value=0)
    report = {
        "accepted_orders": len(accepted), "filled_round_trips": len(fills),
        "active_sessions": int(fills["date"].nunique()), "missed_while_busy": len(rows) - len(accepted),
        "missing_entries_after_acceptance": int(accepted["entry"].isna().sum()),
        "late_accepted_exits": int(accepted["late_exit"].sum()),
        "accepted_exits_after_cutoff": int(accepted["after_cutoff"].sum()),
        "unresolved_accepted_exits": len(unresolved),
        "unresolved_dates": sorted(unresolved["date"].unique().tolist()),
        "max_entry_lag_seconds": float((fills["entry_time"] - fills["requested_entry"]).max() / SECONDS)
        if len(fills) else None,
        "max_exit_lag_seconds": float(((fills["exit_time"] - fills["entry_time"]).max() / SECONDS) - 60)
        if len(fills) else None,
        "costs": {},
    }
    for cost in COSTS:
        models = {}
        for model, column in SIDES.items():
            side = fills[column]
            gross = POINT_VALUE * side * (fills["exit"] - fills["entry"])
            net = gross - cost * side.ne(0)
            amounts = net.groupby(fills["date"]).sum().reindex(dates, fill_value=0)
            daily[f"{model}_net_cost_{cost}"] = amounts
            risk = exposure(fills, slices, side, cost) if unresolved.empty else None
            if risk is not None and abs(risk["observed_fill_net_usd"] - net.sum()) > 1e-7:
                raise ValueError("OHLC equity ledger disagrees with realized net")
            top3 = float(net[net > 0].nlargest(3).sum())
            gains = float(net.clip(lower=0).sum())
            models[model] = {
                "trades": int(side.ne(0).sum()), "flat_matched_opportunities": int(side.eq(0).sum()),
                "gross_usd": float(gross.sum()), "friction_usd": cost * int(side.ne(0).sum()),
                "net_usd": float(net.sum()), "positive_net_trades": int(net.gt(0).sum()),
                "negative_net_trades": int(net.lt(0).sum()),
                "net_without_top_three_winners_usd": float(net.sum()) - top3,
                "top_three_winner_share": top3 / gains if gains else None,
                "net_without_best_session_usd": float(net.sum() - amounts.clip(lower=0).max()),
                "risk": risk,
            }
        candidate = daily[f"candidate_net_cost_{cost}"]
        comparisons = {"cash": interval(candidate, blocks)}
        for model in SIDES:
            if model != "candidate":
                comparisons[model] = interval(candidate - daily[f"{model}_net_cost_{cost}"], blocks)
        report["costs"][str(cost)] = {"models": models, "candidate_paired_vs": comparisons}
    return report, daily


def case_chart(candidates: Iterable[pd.DataFrame], tape: pd.DataFrame, path: Path) -> None:
    sections = []
    for fills in candidates:
        if fills.empty:
            continue
        pnl = POINT_VALUE * fills["action"] * (fills["exit"] - fills["entry"]) - 6
        for label, index in (("Best filled trade", pnl.idxmax()), ("Worst filled trade", pnl.idxmin())):
            row = fills.loc[index]
            series = tape.loc[row.signal - 12 * SECONDS:row.exit_time + 5 * SECONDS]["close"]
            markers = [
                (row.entry_time, row.entry, "#166534", f"Entry at {row.entry_time:%H:%M:%S}"),
                (row.exit_time, row.exit, "#a22c29", f"Exit at {row.exit_time:%H:%M:%S}"),
            ]
            title = f"{label}, +{row.delay}s delay, {row.date}, {row.kind}"
            sections.append(
                f"<section><p>{row.signal:%H:%M:%S} New York signal. "
                f"Signed net ${pnl.loc[index]:+,.2f} with $6 friction. "
                f"Contribution score {row.q:+.3f}.</p>"
                + _svg_series(title, [("MNQ second close (pts)", "#233c56", list(series.items()))], markers)
                + "</section>"
            )
    path.write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><title>MNQ second replay cases</title>'
        '<style>body{max-width:960px;margin:24px auto;padding:0 20px;font:16px system-ui;color:#182637}'
        'section{border-top:1px solid #ddd;margin-top:24px}svg{width:100%;height:auto}</style>'
        '<h1>Largest accepted gains and losses</h1><p>Observed MNQ second bars. '
        'Hover over markers for fills. Lines connect successive observed closes.</p>'
        + "".join(sections) + "</html>\n"
    )


def write_readme(summary: dict, destination: Path) -> None:
    lines = [
        "# Transmitted-move replay",
        "",
        "One MNQ on 27 previously exposed sessions. Each control uses the candidate's accepted timings.",
        "A flat control pays no friction. Standalone continuation and fade each manage their own position.",
        "Attribution rows retain only that signal type from the accepted combined ledger.",
        "The overlapping return labels in the JSON use every priced opportunity.",
        "",
        "| Extra seconds | Portfolio | Fills | Gross USD | Net $3 | Net $6 | Net $9 | "
        "$9 net less top 3 | $6 close DD | $6 observed intrabar DD | Missing held seconds |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---|---:|",
    ]
    for delay, cohorts in summary["delays"].items():
        for kind, group in cohorts.items():
            models = [group["executable"]["costs"][str(cost)]["models"]["candidate"] for cost in COSTS]
            low, base, stress = models
            risk = base["risk"]
            close_dd = f"{risk['observed_close_drawdown_usd']:,.2f}" if risk else "Incomplete"
            intrabar_dd = (f"{risk['observed_intrabar_drawdown_lower_usd']:,.2f}–"
                           f"{risk['observed_intrabar_drawdown_upper_usd']:,.2f}") if risk else "Incomplete"
            missing = risk["missing_held_seconds"] if risk else "Incomplete"
            lines.append(
                f"| {delay} | {kind} | {base['trades']} | {base['gross_usd']:,.2f} | "
                f"{low['net_usd']:,.2f} | {base['net_usd']:,.2f} | {stress['net_usd']:,.2f} | "
                f"{stress['net_without_top_three_winners_usd']:,.2f} | {close_dd} | {intrabar_dd} | {missing} |"
            )
    lines.extend([
        "", "The drawdown interval accounts for unknown high–low order inside observed seconds.",
        "It cannot bound prices during gaps or establish a trailing-account drawdown.",
        "Paired intervals use all 27 scheduled days, 10,000 five-session circular-block draws "
        "and seed 604. Values are daily dollars.",
        "", "| Extra seconds | Cost | Control | Candidate difference, total USD | Paired 95% daily interval |",
        "|---:|---:|---|---:|---:|",
    ])
    for delay in ("1", "9"):
        group = summary["delays"][delay]["combined"]["executable"]
        for cost in ("6", "9"):
            for control, data in group["costs"][cost]["candidate_paired_vs"].items():
                low, high = data["interval95_daily_usd"]
                lines.append(f"| {delay} | {cost} | {control} | {data['total_usd']:+,.2f} | "
                             f"[{low:+,.2f}, {high:+,.2f}] |")
    lines.extend(["", "**Frozen promotion gate:** "
                  + ("met." if summary["gate"]["passes"] else "failed."),
                  "", "[Full results](summary.json) · [Daily returns](daily.csv) · "
                  "[Accepted orders](accepted-orders.csv.gz) · [Case chart](cases.html) · [Source checksums](schedule.json)"])
    destination.write_text("\n".join(lines) + "\n")


def run(opportunities: Path, source: Path, schedule: Path, output: Path) -> None:
    schedule_data = json.loads(schedule.read_text())
    dates = sorted(schedule_data["scheduled_dates"])
    if len(set(dates)) != 27 or len(dates) != 27:
        raise ValueError("Expected 27 distinct scheduled dates")
    tape, digest = load(source, "MNQ", True)
    if digest != schedule_data["micro_sha256"]:
        raise ValueError("MNQ tape disagrees with the frozen replay hash")
    rows = pd.read_csv(opportunities)
    if not set(rows["date"]).issubset(dates) or rows.duplicated(["date", "signal", "delay"]).any():
        raise ValueError("Opportunity ledger has an unknown session or a duplicate")
    for field in ("signal", "requested_entry", "entry_time", "exit_time"):
        rows[field] = pd.to_datetime(rows[field], utc=True).dt.tz_convert("America/New_York")
    rows["always_long"] = 1
    for column in SIDES.values():
        if not rows[column].isin((-1, 0, 1)).all():
            raise ValueError("Invalid matched direction")
    if not rows["kind"].isin(("continuation", "fade")).all() or rows["action"].eq(0).any():
        raise ValueError("Only nonabstaining signals are executable opportunities")

    result = {"scheduled_dates": dates, "source_sha256": digest, "delays": {}}
    ledgers = []
    accepted_ledgers = []
    chart_fills = []
    blocks = block_indexes(len(dates))
    for delay in DELAYS:
        at_delay = rows.loc[rows["delay"] == delay]
        if not independent_acceptance(at_delay).equals(at_delay.accepted):
            raise ValueError("Combined order occupancy disagrees with archived replay")
        cohorts = {"combined": at_delay}
        for kind in ("continuation", "fade"):
            group = at_delay.loc[at_delay.kind.eq(kind)]
            cohorts[f"{kind}_standalone"] = group.assign(accepted=independent_acceptance(group))
            cohorts[f"{kind}_attribution"] = group
        delay_metrics = {}
        for kind, cohort in cohorts.items():
            executable, daily = evaluate_portfolio(cohort, tape, dates, blocks)
            delay_metrics[kind] = {"overlapping": describe_overlapping(cohort), "executable": executable}
            ledgers.append(daily.reset_index().assign(delay=delay, portfolio=kind))
            if not kind.endswith("_attribution"):
                accepted_ledgers.append(cohort.loc[cohort.accepted].assign(portfolio=kind))
        result["delays"][str(delay)] = delay_metrics
        if delay in (1, 9):
            chart_fills.append(at_delay.loc[at_delay["accepted"] & at_delay["exit"].notna()])
    gate = {}
    for delay in ("1", "9"):
        execution = result["delays"][delay]["combined"]["executable"]
        base, stress = (execution["costs"][cost] for cost in ("6", "9"))
        risk = base["models"]["candidate"]["risk"]
        gate[delay] = {
            "at_least_50_trades": execution["filled_round_trips"] >= 50,
            "at_least_15_active_sessions": execution["active_sessions"] >= 15,
            "no_unresolved_exits": execution["unresolved_accepted_exits"] == 0,
            "stressed_net_without_top_three_positive":
                stress["models"]["candidate"]["net_without_top_three_winners_usd"] > 0,
            "base_observed_intrabar_upper_below_budget":
                risk is not None and risk["observed_intrabar_drawdown_upper_usd"] < 1500,
            "positive_paired_lower_intervals_by_cost": {
                str(cost): {
                    control: data["interval95_daily_usd"][0] > 0
                    for control, data in execution["costs"][str(cost)]["candidate_paired_vs"].items()
                } for cost in COSTS
            },
        }
    checks = ("at_least_50_trades", "at_least_15_active_sessions", "no_unresolved_exits",
              "stressed_net_without_top_three_positive", "base_observed_intrabar_upper_below_budget")
    result["gate"] = {"per_delay": gate, "passes": all(
        all(row[name] for name in checks)
        and all(row["positive_paired_lower_intervals_by_cost"]["6"].values())
        for row in gate.values()
    )}
    events_path = opportunities.with_name("events.csv.gz")
    if events_path.exists():
        events = pd.read_csv(events_path, usecols=["kind", "date"])
        result["event_counts"] = {
            str(kind): {"events": len(group), "sessions": int(group["date"].nunique())}
            for kind, group in events.groupby("kind")
        }
    output.mkdir(exist_ok=True, parents=True)
    (output / "summary.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    pd.concat(ledgers, ignore_index=True).to_csv(output / "daily.csv", index=False)
    write_readme(result, output / "README.md")
    accepted = pd.concat(accepted_ledgers, ignore_index=True).sort_values(["delay", "portfolio", "signal"])
    accepted["requested_exit"] = accepted["entry_time"] + 60 * SECONDS
    accepted["fill_status"] = np.select(
        [accepted["entry"].isna(), accepted["unresolved"]],
        ["entry_missing", "exit_unresolved"], default="completed_round_trip",
    )
    accepted.to_csv(output / "accepted-orders.csv.gz", index=False,
                    compression={"method": "gzip", "mtime": 0})
    case_chart(chart_fills, tape, output / "cases.html")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("opportunities", type=Path)
    parser.add_argument("mnq_fine", type=Path)
    parser.add_argument("schedule", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    run(args.opportunities, args.mnq_fine, args.schedule, args.output)
