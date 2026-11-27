"""Post-hoc, exposed-only horizons for the frozen V1 external replay.

This is a label diagnostic.  It does not change entries, exits, eligibility,
or the parent hold policy.  All event rows are selected from the recorded
causal activations before reading any future executable open.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

NY = "America/New_York"
HORIZONS = (1, 4, 8)
BOOTSTRAP_REPS = 10_000
BOOTSTRAP_SEED = 604
REPLAY_FILES = ("trades.csv.gz", "activations.csv.gz", "source.json")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _aware(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True).dt.tz_convert(NY)


def _select_events(activations: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    """Select first eligibility and first disagreement without future prices."""
    tr = trades.loc[
        trades.panel.eq("external") & trades.model.eq("original") & trades.delay.isin((0, 1))
    ].copy()
    if not len(tr):
        raise ValueError("pinned replay has no original external V1 trades")
    a = activations.loc[
        activations.panel.eq("external")
        & activations.model.eq("original")
        & activations.delay.isin((0, 1))
        & activations.trade_id.isin(tr.trade_id)
    ].copy()
    if not len(a):
        raise ValueError("pinned replay has no external V1 activations")
    a["bar_start"] = _aware(a.bar_start)
    a["entry_time"] = _aware(a.entry_time)
    a["date"] = a.bar_start.dt.strftime("%Y-%m-%d")
    a.sort_values(["delay", "trade_id", "bar_start"], inplace=True)

    selections: list[dict[str, Any]] = []
    for (delay, trade_id), rows in a.groupby(["delay", "trade_id"], sort=False):
        rows = rows.reset_index(drop=True)
        first = rows.loc[rows.eligible.astype(bool) & rows.discretionary.astype(bool)]
        if len(first):
            row = first.iloc[0]
            selections.append(_event_row(row, "first_eligible", "first_eligible"))

        # Each readout begins alive.  At the first live split, the score at or
        # below zero would request an exit on that policy; both were still
        # holding immediately before that request.  Once either would have
        # requested earlier, there is no later disagreement opportunity.
        for _, row in rows.iterrows():
            if not bool(row.eligible):
                continue
            if not bool(row.discretionary):
                break
            volume_holds = float(row.volume_score) > 0.0
            price_holds = float(row.price_score) > 0.0
            if volume_holds != price_holds:
                kind = "volume_holds" if volume_holds else "volume_exits"
                selections.append(_event_row(row, "first_disagreement", kind))
                break
            if not volume_holds and not price_holds:
                break

    selected = pd.DataFrame(selections)
    if not len(selected):
        raise ValueError("no eligible diagnostic events selected")
    return selected.sort_values(["date", "entry_time", "delay", "event"], kind="stable").reset_index(drop=True)


def _event_row(row: pd.Series, event: str, group: str) -> dict[str, Any]:
    # Intentionally retain the executable time but not its price during event
    # selection. Price labels are joined in a later pass.
    return {
        "event": event,
        "group": group,
        "trade_id": str(row.trade_id),
        "panel": str(row.panel),
        "date": str(row.date),
        "delay": int(row.delay),
        "side": int(row.direction),
        "entry_time": row.entry_time,
        "bar_start": row.bar_start,
        "eligible": bool(row.eligible),
        "discretionary": bool(row.discretionary),
        "volume_score": float(row.volume_score),
        "price_score": float(row.price_score),
        "entry_forecast": float(row.forecast),
        "original_exit_time": row.original_exit_time,
        "original_exit_price": float(row.original_exit_price),
        "alternate_open_time": row.next_executable_time,
    }


def _label_events(events: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    """Add open-to-open labels; missing exact endpoints stay missing."""
    result = events.copy()
    result["alternate_open_price"] = np.nan
    result["alternate_open_missing"] = False
    for h in HORIZONS:
        result[f"label_{h}m_points"] = np.nan
        result[f"end_{h}m_time"] = pd.Series(pd.NaT, index=result.index, dtype=f"datetime64[ns, {NY}]")
        result[f"capped_{h}m_by_original_exit"] = False
        result[f"missing_{h}m_endpoint"] = False
    result["label_original_exit_points"] = np.nan
    result["original_exit_missing"] = False

    for idx, row in result.iterrows():
        start = row.alternate_open_time
        if pd.isna(start) or start not in bars.index:
            result.at[idx, "alternate_open_missing"] = True
            continue
        start_px = float(bars.at[start, "open"])
        result.at[idx, "alternate_open_price"] = start_px
        exit_time = row.original_exit_time
        exit_px = float(row.original_exit_price)
        if pd.isna(exit_time) or exit_time not in bars.index:
            result.at[idx, "original_exit_missing"] = True
        elif exit_time < start:
            result.at[idx, "original_exit_missing"] = True
        else:
            result.at[idx, "label_original_exit_points"] = row.side * (exit_px - start_px)

        for h in HORIZONS:
            wanted = start + pd.Timedelta(minutes=h)
            capped = not pd.isna(exit_time) and exit_time in bars.index and exit_time <= wanted
            endpoint = exit_time if capped else wanted
            if capped:
                endpoint_px = exit_px
            elif endpoint in bars.index:
                endpoint_px = float(bars.at[endpoint, "open"])
            else:
                result.at[idx, f"missing_{h}m_endpoint"] = True
                continue
            if endpoint < start:
                result.at[idx, f"missing_{h}m_endpoint"] = True
                continue
            result.at[idx, f"label_{h}m_points"] = row.side * (endpoint_px - start_px)
            result.at[idx, f"end_{h}m_time"] = endpoint
            result.at[idx, f"capped_{h}m_by_original_exit"] = bool(capped)
    return result


def _mean(values: pd.Series) -> float | None:
    clean = values.dropna().to_numpy(dtype=float)
    return float(clean.mean()) if len(clean) else None


def _session_bootstrap(values: pd.DataFrame, label_col: str, dates: list[str], draws: np.ndarray) -> dict:
    sub = values.loc[values[label_col].notna(), ["date", label_col]]
    if not len(sub):
        return {"n": 0, "sessions": 0, "mean": None, "ci95": [None, None]}
    sums = np.zeros(len(dates), dtype=float)
    counts = np.zeros(len(dates), dtype=float)
    ix = {date: i for i, date in enumerate(dates)}
    for date, group in sub.groupby("date", sort=False):
        sums[ix[str(date)]] = group[label_col].sum()
        counts[ix[str(date)]] = len(group)
    numer = sums[draws].sum(axis=1)
    denom = counts[draws].sum(axis=1)
    valid = denom > 0
    boot = numer[valid] / denom[valid]
    return {
        "n": int(len(sub)),
        "sessions": int(sub.date.nunique()),
        "mean": float(sub[label_col].mean()),
        "ci95": [float(np.quantile(boot, .025)), float(np.quantile(boot, .975))] if len(boot) else [None, None],
    }


def _summary(events: pd.DataFrame, dates: list[str]) -> dict:
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    draws = rng.integers(0, len(dates), size=(BOOTSTRAP_REPS, len(dates)))
    groups = ("first_eligible", "volume_holds", "volume_exits")
    summary: dict[str, Any] = {}
    for delay in (0, 1):
        delay_key = str(delay)
        summary[delay_key] = {}
        for group_name in groups:
            subset = events.loc[events.delay.eq(delay) & events.group.eq(group_name)]
            if not len(subset):
                summary[delay_key][group_name] = {"n": 0, "horizons": {}}
                continue
            entry: dict[str, Any] = {"n": int(len(subset)), "horizons": {}}
            label_fields = [(f"{h}m", f"label_{h}m_points") for h in HORIZONS]
            label_fields.append(("original_exit", "label_original_exit_points"))
            for horizon, label_col in label_fields:
                labels = subset[label_col].dropna()
                stat: dict[str, Any] = {
                    "mean_signed_label_points": _mean(subset[label_col]),
                    "valid_n": int(len(labels)),
                    "capped_by_original_exit_n": int(subset[f"capped_{horizon[:-1]}m_by_original_exit"].sum()) if horizon.endswith("m") else None,
                    "paired_session_bootstrap_95": _session_bootstrap(subset, label_col, dates, draws),
                }
                if group_name == "first_eligible":
                    pair = subset[["volume_score", "price_score", label_col]].dropna()
                    stat["mean_volume_score"] = _mean(subset.volume_score)
                    stat["mean_price_score"] = _mean(subset.price_score)
                    if len(pair) >= 2 and pair.volume_score.nunique() > 1 and pair[label_col].nunique() > 1:
                        stat["spearman_volume_score_rho"] = float(spearmanr(pair.volume_score, pair[label_col]).statistic)
                    else:
                        stat["spearman_volume_score_rho"] = None
                    if len(pair) >= 2 and pair.price_score.nunique() > 1 and pair[label_col].nunique() > 1:
                        stat["spearman_price_score_rho"] = float(spearmanr(pair.price_score, pair[label_col]).statistic)
                    else:
                        stat["spearman_price_score_rho"] = None
                entry["horizons"][horizon] = stat
            summary[delay_key][group_name] = entry
    return summary


def run(replay_dir: str | Path = "/workspace/work/hold-replay", market_dir: str | Path = "/workspace/work/market", out_dir: str | Path | None = None) -> tuple[dict, pd.DataFrame]:
    replay_dir = Path(replay_dir).resolve()
    out_dir = Path(out_dir).resolve() if out_dir is not None else Path(__file__).resolve().parent / "results"
    root = Path(__file__).resolve().parents[2]

    # Load the verified public source bars using the existing common loader.
    try:
        from .sources import load_sources
    except ImportError:  # direct script invocation
        import importlib.util
        source_path = Path(__file__).resolve().with_name("sources.py")
        spec = importlib.util.spec_from_file_location("hold_work_sources", source_path)
        if spec is None or spec.loader is None:
            raise ImportError("cannot load hold_work.sources")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        load_sources = module.load_sources
    _, external, source_provenance = load_sources(root, market_dir)
    bars = external["MNQ.csv"].sort_index()
    allowed_dates = source_provenance["external"]["included_dates"]

    replay_source_path = replay_dir / "source.json"
    replay_source = json.loads(replay_source_path.read_text(encoding="utf-8"))
    if replay_source.get("external_hashes") != source_provenance["external_hashes"]:
        raise ValueError("pinned replay external source does not match verified public hashes")
    if replay_source.get("external", {}).get("included_dates") != allowed_dates:
        raise ValueError("pinned replay date panel does not match the verified external60 panel")
    trades_path = replay_dir / "trades.csv.gz"
    activations_path = replay_dir / "activations.csv.gz"
    trades = pd.read_csv(trades_path)
    activations = pd.read_csv(activations_path)
    for col in ("signal_time", "entry_time", "exit_time", "exit_signal_time"):
        if col in trades:
            trades[col] = _aware(trades[col])
    for col in ("entry_time", "next_executable_time", "original_exit_time"):
        if col in activations:
            activations[col] = _aware(activations[col])
    # Exit timestamps are retained from the pinned per-bar trace. Verify those
    # label-only fields agree with the trade ledger before label construction.
    original = trades.loc[trades.panel.eq("external") & trades.model.eq("original") & trades.delay.isin((0, 1))]
    exit_map = original.set_index(["trade_id", "delay"])[["exit_time", "exit"]]
    selected = _select_events(activations, trades)
    for idx, row in selected.iterrows():
        t = exit_map.loc[(row.trade_id, row.delay)]
        if row.original_exit_time != t.exit_time or float(row.original_exit_price) != float(t.exit):
            raise ValueError("activation original-exit labels disagree with frozen original trade ledger")

    # Selection above never reads next_executable_price. Labels are constructed
    # only now, by exact expected timestamps with no nearest-bar replacement.
    events = _label_events(selected, bars)
    summary = _summary(events, allowed_dates)
    provenance = {
        "description": "Post-hoc horizon diagnostic on the exposed V1 external60 panel; descriptive only.",
        "source": "pinned /workspace/work/hold-replay V1 replay; verified public MNQ source at archived commit.",
        "external_hashes": source_provenance["external_hashes"],
        "external_source_commit": source_provenance["external_source_commit"],
        "panel": "external60",
        "included_dates": allowed_dates,
        "selection": {
            "trade_scope": "model=original, panel=external, delays 0 and 1",
            "first_eligible": "first row per original trade with eligible=true and discretionary=true",
            "first_disagreement": "first eligible/discretionary row where one score is positive and the other is nonpositive, before either head had an earlier exit request",
            "groups": {"volume_holds": "volume_score>0 and price_score<=0", "volume_exits": "volume_score<=0 and price_score>0"},
            "selected_before_future_prices": True,
            "missing_data": "Exact expected timestamps only; missing next open/endpoints remain missing and are never replaced by a later observation.",
        },
        "label": "side * (endpoint open - alternate executable open), in MNQ points.",
        "alternate_executable_open": "one minute after signal bar for delay 0; two minutes after signal bar for delay 1.",
        "horizons_minutes": list(HORIZONS),
        "horizon_cap": "If the original exit occurs at or before the requested endpoint, use the original exit open and timestamp.",
        "original_exit_label": "alternate executable open to eventual frozen original exit open.",
        "bootstrap": {"method": "paired session cluster bootstrap; same sampled dates used for all delays, groups, and horizons", "replicates": BOOTSTRAP_REPS, "seed": BOOTSTRAP_SEED, "interval": "percentile 95%"},
        "replay_file_sha256": {name: _sha256(replay_dir / name) for name in REPLAY_FILES},
        "selection_counts": {
            "events": int(len(events)),
            "first_eligible": int(events.event.eq("first_eligible").sum()),
            "first_disagreement": int(events.event.eq("first_disagreement").sum()),
            "alternate_open_missing": int(events.alternate_open_missing.sum()),
        },
        "summary": summary,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    events.to_csv(out_dir / "horizon_trades.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    (out_dir / "horizon.json").write_text(json.dumps(provenance, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return provenance, events


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay", type=Path, default=Path(__file__).resolve().parent / "results")
    parser.add_argument("--market", type=Path, default=Path("market"))
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "results")
    args = parser.parse_args()
    result, events = run(args.replay, args.market, args.out)
    print(json.dumps({"events": len(events), "output": str(args.out), "counts": result["selection_counts"]}, indent=2))


if __name__ == "__main__":
    main()
