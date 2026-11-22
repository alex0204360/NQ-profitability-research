"""Audit frozen reservoir ledgers and the separately scored reissued tape.

The archived path_order CSVs are the baseline. Reissued trades and decision
states come from return_map/score.py's hash-checked results/trades.csv, keeping
the reissued replay distinct and avoiding a second execution of inherited code.
All timestamps are parsed with UTC offsets and normalized to UTC for matching.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RESULTS = Path(__file__).with_name("results")
DEFAULT_OUT = RESULTS / "baseline_audit.csv"
POINT_VALUE = 2.0


def read_ledger(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    for col in ("signal_time", "entry_time", "exit_time"):
        df[col] = pd.to_datetime(df[col], utc=True)
    return df


def read_reissued(trades_path: Path, audit_path: Path) -> pd.DataFrame:
    audit = json.loads(audit_path.read_text())
    expected = ("extension1", "extension2", "november")
    if any(audit.get(window, {}).get("identity") != "reissued" for window in expected):
        raise ValueError("score source audit does not identify all November windows as reissued")
    rows = pd.read_csv(trades_path)
    rows = rows.loc[(rows["head"] == "reservoir") & (rows.cost_usd == 3)].copy()
    rows = rows.loc[rows.panel.isin(["extension", "november"])]
    rows = rows.rename(columns={"state_scale": "scale", "state_reservoir": "forecast"})
    for col in ("signal_time", "entry_time", "exit_time"):
        rows[col] = pd.to_datetime(rows[col], utc=True)
    return rows


def summarize(df: pd.DataFrame, label: str, panel: str, delay: int) -> dict:
    d = df.copy()
    d["gross_usd"] = d.gross_usd.astype(float)
    d["net6_usd"] = d.gross_usd - 6.0
    d["scale"] = d.scale.astype(float)
    forecast_col = "forecast" if "forecast" in d else "reservoir"
    d["abs_forecast_over_scale"] = d[forecast_col].abs() / d.scale
    d["gross_signed_points_over_scale"] = d.gross_usd / POINT_VALUE / d.scale
    local_entry = d.entry_time.dt.tz_convert("America/New_York")
    d["utc_date"] = local_entry.dt.strftime("%Y-%m-%d")
    d["local_hour"] = local_entry.dt.hour
    by_date = d.groupby("utc_date").net6_usd.sum()
    by_side = d.groupby("side").net6_usd.sum().sort_values(ascending=False)
    by_hour = d.groupby("local_hour").net6_usd.sum().sort_values(ascending=False)
    best_date = by_date.idxmax() if len(by_date) else ""
    best_five = d.nlargest(min(5, len(d)), "net6_usd")
    gross_std = d.gross_signed_points_over_scale
    result = {
        "record_type": "panel_summary", "panel": panel, "source": label,
        "delay_minutes": delay, "trade_count": len(d),
        "gross_usd": d.gross_usd.sum(), "breakeven_round_trip_usd": d.gross_usd.mean() if len(d) else None,
        "net_at_6_usd": d.net6_usd.sum(), "median_trade_net_at_6_usd": d.net6_usd.median() if len(d) else None,
        "median_pre_entry_scale_points": d.scale.median() if len(d) else None,
        "mean_abs_forecast_over_scale": d.abs_forecast_over_scale.mean() if len(d) else None,
        "median_abs_forecast_over_scale": d.abs_forecast_over_scale.median() if len(d) else None,
        "mean_gross_signed_points_over_scale": gross_std.mean() if len(d) else None,
        "median_gross_signed_points_over_scale": gross_std.median() if len(d) else None,
        "best_side": by_side.index[0] if len(by_side) else "",
        "best_side_net6_usd": by_side.iloc[0] if len(by_side) else None,
        "best_side_trade_share": (d.side == by_side.index[0]).mean() if len(by_side) else None,
        "best_entry_hour_et": int(by_hour.index[0]) if len(by_hour) else None,
        "best_hour_net6_usd": by_hour.iloc[0] if len(by_hour) else None,
        "best_hour_trade_share": (d.local_hour == by_hour.index[0]).mean() if len(by_hour) else None,
        "best_date_et": best_date,
        "best_date_excluded_net6_usd": d.net6_usd.sum() - by_date.max() if len(by_date) else None,
        "best_5_trades_excluded_net6_usd": d.net6_usd.sum() - best_five.net6_usd.sum(),
    }
    details = []
    for kind, key in (("side_concentration", "side"), ("entry_hour_et_concentration", "local_hour")):
        for value, group in d.groupby(key):
            details.append({
                "record_type": kind, "panel": panel, "source": label,
                "delay_minutes": delay, "subcategory": str(value),
                "trade_count": len(group), "gross_usd": group.gross_usd.sum(),
                "net_at_6_usd": group.net6_usd.sum(),
                "median_trade_net_at_6_usd": group.net6_usd.median(),
            })
    return result, details


def trade_id(df: pd.DataFrame) -> pd.Series:
    return (df.signal_time.dt.tz_convert("UTC").astype(str) + "|" +
            df.entry_time.dt.tz_convert("UTC").astype(str) + "|" + df.side.astype(str))


def comparison(frozen: pd.DataFrame, reissued: pd.DataFrame, delay: int) -> dict:
    a, b = frozen.copy(), reissued.copy()
    a["trade_id"] = trade_id(a)
    b["trade_id"] = trade_id(b)
    if a.trade_id.duplicated().any() or b.trade_id.duplicated().any():
        raise ValueError("trade IDs must be unique for paired comparison")
    joined = a.merge(b, on="trade_id", how="inner", suffixes=("_frozen", "_reissued"))
    only_a, only_b = a[~a.trade_id.isin(joined.trade_id)], b[~b.trade_id.isin(joined.trade_id)]
    diff = joined.gross_usd_reissued - joined.gross_usd_frozen
    return {
        "record_type": "frozen_vs_reissued", "panel": "november_14_sessions",
        "source": "exact_frozen_vs_reissued", "delay_minutes": delay,
        "trade_count": len(joined), "matched_count": len(joined),
        "unmatched_frozen_count": len(only_a), "unmatched_reissued_count": len(only_b),
        "gross_usd": joined.gross_usd_frozen.sum(),
        "reissued_matched_gross_usd": joined.gross_usd_reissued.sum(),
        "paired_gross_delta_reissued_minus_frozen_usd": diff.sum(),
        "mean_paired_gross_delta_usd": diff.mean() if len(diff) else None,
        "unmatched_frozen_gross_usd": only_a.gross_usd.sum(),
        "unmatched_reissued_gross_usd": only_b.gross_usd.sum(),
        "frozen_total_gross_usd": a.gross_usd.sum(),
        "reissued_total_gross_usd": b.gross_usd.sum(),
        "net_at_6_usd": joined.gross_usd_frozen.sum() - 6 * len(joined),
        "frozen_matched_net_at_6_usd": joined.gross_usd_frozen.sum() - 6 * len(joined),
        "reissued_matched_net_at_6_usd": joined.gross_usd_reissued.sum() - 6 * len(joined),
        "frozen_total_net_at_6_usd": a.gross_usd.sum() - 6 * len(a),
        "reissued_net_at_6_usd": b.gross_usd.sum() - 6 * len(b),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--trades", type=Path, default=RESULTS / "trades.csv")
    parser.add_argument("--source-audit", type=Path, default=RESULTS / "source_audit.json")
    args = parser.parse_args()
    base = ROOT / "experiments" / "path_order"
    rows: list[dict] = []
    frozen_nov: dict[int, list[pd.DataFrame]] = {0: [], 1: []}

    for panel, dirs in (("discovery", [base / "discovery"]),
                        ("november_14_sessions", [base / "november-extension", base / "november"])):
        for delay in (0, 1):
            parts = [read_ledger(directory / f"reservoir-delay{delay}.csv") for directory in dirs]
            df = pd.concat(parts, ignore_index=True)
            if panel == "november_14_sessions":
                frozen_nov[delay] = parts
            summary, details = summarize(df, "exact_frozen_archived_ledger", panel, delay)
            rows.append(summary)
            rows.extend(details)

    # This already-scored revision remains separate from the frozen ledger.
    reissued = read_reissued(args.trades, args.source_audit)
    for delay in (0, 1):
        reissued_all = reissued.loc[reissued.delay == delay].copy()
        summary, details = summarize(reissued_all, "reissued_score_trades_csv", "november_14_sessions", delay)
        rows.append(summary)
        rows.extend(details)
        frozen_all = pd.concat(frozen_nov[delay], ignore_index=True)
        rows.append(comparison(frozen_all, reissued_all, delay))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(args.out, index=False, float_format="%.8g")
    print(f"wrote {args.out} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
