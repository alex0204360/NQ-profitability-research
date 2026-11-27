"""Chronological evaluation of the frozen matured-label hold-value memory."""

from __future__ import annotations

import argparse
from heapq import heappop, heappush
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .metrics import COSTS, USD_PER_POINT, _spearman

HEADS = ("zero", "raw_volume", "constant", "price", "interaction")
CONTROLS = ("zero", "constant", "price")
KEYS = ["panel", "date", "delay", "trade_id"]
MINUTE = pd.Timedelta(minutes=1)
BOOTSTRAP_DRAWS = 10_000
BLOCK_LENGTH = 5
SEED = 2711


def make_projections(decisions: pd.DataFrame, memory) -> pd.DataFrame:
    """Apply previously matured outcomes, then project and queue this outcome."""
    scheduled = decisions.assign(
        decision_close=pd.to_datetime(decisions["bar_start"], utc=True) + MINUTE,
        exit_maturity=pd.to_datetime(decisions["original_exit_time"], utc=True),
        alternative_time=pd.to_datetime(decisions["next_executable_time"], utc=True),
    ).sort_values(["decision_close", "trade_id"])
    pending = []
    projections = []
    observed = 0
    last_observation = pd.NaT
    for ordinal, row in enumerate(scheduled.itertuples(index=False)):
        while pending and pending[0][0] < row.decision_close:
            maturity, _, inputs, label = heappop(pending)
            assert maturity < row.decision_close
            memory.observe(*inputs, label)
            observed += 1
            last_observation = maturity

        inputs = (row.entry_scale, row.price_score, row.volume_score)
        values = memory.predict(*inputs)
        projections.append({
            "zero": 0.0,
            "raw_volume": row.volume_score,
            **values,
            "prior_labels_observed": observed,
            "latest_observed_exit": last_observation,
            "pending_labels_before_projection": len(pending),
        })
        assert row.exit_maturity >= row.decision_close
        if np.isfinite(row.realized_hold_pts):
            heappush(pending, (row.exit_maturity, ordinal, inputs, row.realized_hold_pts))
    columns = [*HEADS, "prior_labels_observed", "latest_observed_exit",
               "pending_labels_before_projection"]
    return scheduled.join(pd.DataFrame(projections, index=scheduled.index, columns=columns))


def bootstrap_indexes(sessions: int) -> np.ndarray:
    starts = np.random.default_rng(SEED).integers(
        sessions, size=(BOOTSTRAP_DRAWS, (sessions + BLOCK_LENGTH - 1) // BLOCK_LENGTH, 1)
    )
    return ((starts + np.arange(BLOCK_LENGTH)) % sessions).reshape(BOOTSTRAP_DRAWS, -1)[:, :sessions]


def session_metrics(predictions: pd.DataFrame, ledger: pd.DataFrame, dates: list[str]) -> pd.DataFrame:
    """Retain the complete timeline, including sessions without an eligible label."""
    daily = pd.DataFrame(index=pd.Index(dates, name="date"))
    daily["original_trades"] = ledger.groupby("date").size().reindex(dates, fill_value=0)
    daily["scheduled_decisions"] = predictions.groupby("date").size().reindex(dates, fill_value=0)
    labeled = predictions.loc[predictions["realized_hold_pts"].notna()]
    daily["labeled_decisions"] = labeled.groupby("date").size().reindex(dates, fill_value=0)
    for head in HEADS:
        error = labeled[head] - labeled["realized_hold_pts"]
        daily[f"{head}_squared_error_sum"] = error.pow(2).groupby(labeled["date"]).sum().reindex(
            dates, fill_value=0
        )
        daily[f"{head}_policy_delta_usd"] = ledger.groupby("date")[f"{head}_delta_usd"].sum().reindex(
            dates, fill_value=0
        )
    return daily


def fixed_ledger(original: pd.DataFrame, predictions: pd.DataFrame) -> pd.DataFrame:
    """Apply each one-shot policy on the identical baseline-entry timeline."""
    evidence_cols = [*KEYS, "decision_close", "exit_maturity", "alternative_time", "next_open",
                     "realized_hold_pts", *HEADS]
    ledger = original.merge(predictions[evidence_cols], on=KEYS, how="left", validate="one_to_one")
    original_time = pd.to_datetime(ledger["exit_time"], utc=True)
    executable = ledger["next_open"].notna() & ledger["realized_hold_pts"].notna()
    if not (original_time[executable] == ledger.loc[executable, "exit_maturity"]).all():
        raise ValueError("Prediction maturity must match the authoritative original trade exit")
    direction = ledger["side"].map({"long": 1, "short": -1})
    if direction.isna().any():
        raise ValueError("Invalid original position side")
    expected_label = direction[executable] * (
        ledger.loc[executable, "exit"] - ledger.loc[executable, "next_open"]
    )
    np.testing.assert_array_equal(expected_label, ledger.loc[executable, "realized_hold_pts"])
    if (ledger.loc[executable, "alternative_time"] > original_time[executable]).any():
        raise ValueError("An executable discretionary alternative cannot follow the original exit")
    for head in HEADS:
        early = executable & ledger[head].lt(0)
        ledger[f"{head}_alternative_chosen"] = early
        ledger[f"{head}_exit_time"] = original_time.where(~early, ledger["alternative_time"])
        ledger[f"{head}_exit_price"] = ledger["exit"].where(~early, ledger["next_open"])
        ledger[f"{head}_delta_usd"] = USD_PER_POINT * direction * (
            ledger[f"{head}_exit_price"] - ledger["exit"]
        )
    return ledger


def summarize(predictions: pd.DataFrame, ledger: pd.DataFrame, daily: pd.DataFrame) -> dict:
    dates = daily.index
    labeled = predictions.loc[predictions["realized_hold_pts"].notna()]
    label = labeled["realized_hold_pts"].to_numpy()
    draws = bootstrap_indexes(len(dates))
    draw_counts = daily["labeled_decisions"].to_numpy()[draws].sum(axis=1)
    valid_draws = draw_counts > 0
    costs = {str(cost): float((ledger["gross_usd"] - cost).sum()) for cost in COSTS}
    reports = {}
    original_time = pd.to_datetime(ledger["exit_time"], utc=True)
    for head in HEADS:
        scores = labeled[head].to_numpy()
        errors = scores - label
        change = ledger[f"{head}_delta_usd"]
        net_delta = float(change.sum())
        gains = change[change > 0].nlargest(5)
        gain_total = float(change.clip(lower=0).sum())
        positive_sessions = daily[f"{head}_policy_delta_usd"].clip(lower=0)
        intervals = {}
        for control in CONTROLS:
            if control == head:
                continue
            difference = daily[f"{head}_squared_error_sum"] - daily[f"{control}_squared_error_sum"]
            boot = difference.to_numpy()[draws].sum(axis=1)[valid_draws] / draw_counts[valid_draws]
            intervals[control] = {
                "mse_delta_pts_squared": float(difference.sum() / len(label)) if len(label) else None,
                "interval95_pts_squared": np.quantile(boot, [.025, .975]).tolist() if len(boot) else None,
                "valid_draws": int(valid_draws.sum()),
            }
        reports[head] = {
            "mse_pts_squared": float(np.mean(errors ** 2)) if len(label) else None,
            "mae_pts": float(np.mean(np.abs(errors))) if len(label) else None,
            "mean_output_pts": float(np.mean(scores)) if len(label) else None,
            "bias_pts": float(np.mean(errors)) if len(label) else None,
            "spearman": _spearman(scores, label),
            "paired_mse_vs_controls": intervals,
            "policy": {
                "alternative_chosen": int(ledger[f"{head}_alternative_chosen"].sum()),
                "changed_fills": int(((ledger[f"{head}_exit_time"] != original_time)
                                     | (ledger[f"{head}_exit_price"] != ledger["exit"])).sum()),
                "positive_effect_trades": int((change > 0).sum()),
                "negative_effect_trades": int((change < 0).sum()),
                "delta_usd": net_delta,
                "net_by_cost_usd": {cost: original_net + net_delta for cost, original_net in costs.items()},
                "positive_delta_usd": gain_total,
                "negative_delta_usd": float(change.clip(upper=0).sum()),
                "largest_positive_trade_share": float(gains.iloc[0] / gain_total) if gain_total else None,
                "leave_largest_positive_trade_out_delta_usd": net_delta - float(gains.head(1).sum()),
                "leave_largest_five_positive_trades_out_delta_usd": net_delta - float(gains.sum()),
                "leave_largest_positive_session_out_delta_usd": net_delta - float(positive_sessions.max()),
            },
        }
    return {
        "dates": dates.tolist(),
        "original_trades": len(ledger),
        "scheduled_first_decisions": len(predictions),
        "labeled_first_decisions": len(labeled),
        "sessions_without_labels": daily.index[daily["labeled_decisions"] == 0].tolist(),
        "mean_realized_pts": float(label.mean()) if len(label) else None,
        "original_net_by_cost_usd": costs,
        "heads": reports,
    }


def write_table(report: dict, destination: Path) -> None:
    lines = [
        "# Matured-label hold-value memory",
        "",
        "All dates were exposed. Each source and fill schedule has a separate memory.",
        "A label enters memory strictly after its original exit. The decision uses only the first",
        "discretionary close. All original entries count toward fixed-ledger net.",
        "",
        "| Source | Fill | Head | MSE (pts²) | MAE (pts) | Mean (pts) | Bias (pts) | Spearman | Changed fills | Δ USD | Net $3 | Net $6 | Net $9 |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for source, fills in report.items():
        for delay, group in fills.items():
            fill = "Next open" if delay == "0" else "Extra minute"
            for name, head in group["heads"].items():
                rho = head["spearman"]
                rank = f"{rho:.3f}" if rho is not None else "—"
                policy = head["policy"]
                net = policy["net_by_cost_usd"]
                lines.append(
                    f"| {source} | {fill} | {name} | {head['mse_pts_squared']:,.2f} "
                    f"| {head['mae_pts']:,.2f} | {head['mean_output_pts']:,.2f} "
                    f"| {head['bias_pts']:,.2f} | {rank} "
                    f"| {policy['changed_fills']} | {policy['delta_usd']:+,.2f} "
                    f"| {net['3']:,.2f} | {net['6']:,.2f} | {net['9']:,.2f} |"
                )
    lines.extend([
        "",
        "Differences below are interaction MSE minus control MSE. The paired five-session",
        "circular block bootstrap uses 10,000 draws and seed 2711. It resamples whole sessions,",
        "including those with no labels, and divides resampled squared-error totals by resampled trade counts.",
        "",
        "| Source | Fill | Control | Δ MSE (pts²) | Paired 95% interval |",
        "|---|---|---|---:|---:|",
    ])
    for source, fills in report.items():
        for delay, group in fills.items():
            fill = "Next open" if delay == "0" else "Extra minute"
            for control, item in group["heads"]["interaction"]["paired_mse_vs_controls"].items():
                lower, upper = item["interval95_pts_squared"]
                lines.append(f"| {source} | {fill} | {control} | {item['mse_delta_pts_squared']:+,.2f} "
                             f"| [{lower:+,.2f}, {upper:+,.2f}] |")
    destination.write_text("\n".join(lines) + "\n")


def run(bundle: Path, output: Path) -> None:
    from .matured import Memory

    names = ["panel", "date", "delay", "model"]
    dates = pd.read_csv(bundle / "equity.csv.gz", usecols=names).drop_duplicates()
    original_dates = dates.loc[dates["model"] == "original"].copy()
    original = pd.read_csv(bundle / "trades.csv.gz")
    original = original.loc[original["model"] == "original"].copy()
    decisions = pd.read_csv(bundle / "first-decisions.csv.gz", low_memory=False)
    if not decisions["model"].eq("original").all() or decisions.duplicated(KEYS).any():
        raise ValueError("Expected the canonical original first-decision archive")
    if not decisions["eligible"].all() or not decisions["discretionary"].all():
        raise ValueError("A first decision must be eligible and discretionary")

    for frame in (original_dates, original, decisions):
        frame["source"] = np.where(frame["panel"] == "external", "external60", "discovery40")
    report = {}
    predictions, ledgers, daily_frames = [], [], []
    for (source, delay), grid in original_dates.groupby(["source", "delay"], sort=True):
        dates = sorted(grid["date"].unique())
        expected_count = 60 if source == "external60" else 40
        if len(dates) != expected_count or len(grid) != expected_count:
            raise ValueError("Expected the complete source date grid with distinct sessions")
        cohort = decisions.loc[(decisions["source"] == source) & (decisions["delay"] == delay)]
        baseline = original.loc[(original["source"] == source) & (original["delay"] == delay)]
        if not set(cohort["date"]).union(baseline["date"]).issubset(dates):
            raise ValueError("Decisions and entries must fall in their source date grid")
        if not set(cohort[KEYS].itertuples(index=False, name=None)).issubset(
            baseline[KEYS].itertuples(index=False, name=None)
        ):
            raise ValueError("A first decision without an original trade")
        output_rows = make_projections(cohort, Memory())
        ledger = fixed_ledger(baseline, output_rows)
        daily = session_metrics(output_rows, ledger, dates)
        report.setdefault(source, {})[str(delay)] = summarize(output_rows, ledger, daily)
        predictions.append(output_rows)
        ledgers.append(ledger)
        daily_frames.append(daily.reset_index().assign(source=source, delay=delay))

    output.mkdir(parents=True, exist_ok=True)
    (output / "summary.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    compression = {"method": "gzip", "mtime": 0}
    pd.concat(predictions).to_csv(output / "predictions.csv.gz", index=False, compression=compression)
    pd.concat(ledgers).to_csv(output / "fixed-ledger.csv.gz", index=False, compression=compression)
    pd.concat(daily_frames).to_csv(output / "daily.csv", index=False)
    write_table(report, output / "README.md")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, help="packaged V1 results directory")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    run(args.bundle, args.output)
