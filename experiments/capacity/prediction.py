"""Frozen margin diagnostics on exposed panels.

Run from the capacity worktree with:
    python experiments/capacity/prediction.py --market /workspace/work/market
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.capacity.neuron import A, SHOCK, encode
from experiments.hold_work.sources import load_sources

MARKET_DIR = Path("/workspace/work/market")
CANONICAL = ROOT / "experiments/hold_work/results/first-decisions.csv.gz"
TRADES = ROOT / "experiments/hold_work/results/trades.csv.gz"
OUT = ROOT / "experiments/capacity/results"
OHLCV = ["open", "high", "low", "close", "volume"]
BASE = "parent_raw"
METRICS = (
    "parent_raw",
    "price_raw",
    "price_stress_margin",
    "volume_stress_margin",
    "price_stress_increment",
    "volume_stress_increment",
)
BLOCK = 5
BOOTSTRAP_REPS = 999
SEED = 604
COSTS = (3, 6, 9)
USD_PER_POINT = 2.0


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for part in iter(lambda: f.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def _ny(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, utc=True).dt.tz_convert("America/New_York")


def _encoder_rows(discovery: pd.DataFrame, external: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (panel, date), session in discovery.groupby(["panel", "date"], sort=False):
        z = encode(session[OHLCV])
        z = z.copy()
        z["panel"] = str(panel)
        z["date"] = str(date)
        z["bar_start"] = z.index
        rows.append(z.reset_index(drop=True))
    external = external.sort_index()
    for date, session in external.groupby(external.index.strftime("%Y-%m-%d"), sort=True):
        z = encode(session[OHLCV]).copy()
        z["panel"] = "external"
        z["date"] = str(date)
        z["bar_start"] = z.index
        rows.append(z.reset_index(drop=True))
    if not rows:
        raise ValueError("no source bars encoded")
    states = pd.concat(rows, ignore_index=True)
    if states.duplicated(["panel", "date", "bar_start"]).any():
        raise ValueError("duplicate state key")
    states["bar_start"] = _ny(states.bar_start)

    # Signed, point-valued readouts for the side already chosen by the parent.
    # The true parent margin uses its realized volume-derived stock. The price
    # sibling carries the identical encoder/motion path but marginalizes charge.
    states["parent_raw"] = np.nan
    states["price_raw"] = np.nan
    states["price_stress_margin"] = np.nan
    states["volume_stress_margin"] = np.nan
    states["price_stress_increment"] = np.nan
    states["volume_stress_increment"] = np.nan
    return states


def _add_side_metrics(frame: pd.DataFrame, direction: pd.Series) -> pd.DataFrame:
    """Calculate signed readouts from an encoded bar table and side vector."""
    out = frame.copy()
    side = direction.astype(float).to_numpy()
    f = out.reservoir.to_numpy(dtype=float)
    p = out.price_forecast.to_numpy(dtype=float)
    scale = out.scale.to_numpy(dtype=float)
    stock = out.stock.to_numpy(dtype=float)
    pstock = out.price_stock.to_numpy(dtype=float)
    out["parent_raw"] = side * f
    out["price_raw"] = side * p
    # neuron.encode emits forecast heads in point units (reservoir and
    # price_forecast are already scaled). Only the inventory term receives
    # the current scale, matching hold_long/short and price_long/short.
    out["volume_stress_margin"] = A * (side * f - SHOCK * scale * stock)
    out["price_stress_margin"] = A * (side * p - SHOCK * scale * pstock)
    expected_volume = np.where(side > 0, out.hold_long, out.hold_short).astype(float)
    expected_price = np.where(side > 0, out.price_long, out.price_short).astype(float)
    if not np.allclose(out.volume_stress_margin, expected_volume, rtol=0, atol=1e-10, equal_nan=True):
        raise ValueError("volume stress margin does not match frozen neuron head")
    if not np.allclose(out.price_stress_margin, expected_price, rtol=0, atol=1e-10, equal_nan=True):
        raise ValueError("price stress margin does not match frozen neuron head")
    out["volume_stress_increment"] = out.volume_stress_margin - out.parent_raw
    out["price_stress_increment"] = out.price_stress_margin - out.price_raw
    return out


def _merge_decisions(root: Path, states: pd.DataFrame, canonical_path: Path) -> tuple[pd.DataFrame, dict]:
    decisions = pd.read_csv(canonical_path)
    decisions["bar_start"] = _ny(decisions.bar_start)
    decisions["date"] = decisions.date.astype(str)
    keys = ["panel", "date", "bar_start"]
    joined = decisions.merge(states, on=keys, how="left", validate="many_to_one", suffixes=("", "_state"))
    missing = int(joined.reservoir.isna().sum())
    if missing:
        example = joined.loc[joined.reservoir.isna(), keys].head().to_dict("records")
        raise ValueError(f"encoder state missing for canonical first decisions: {example}")
    max_abs_error = float(np.max(np.abs(joined.reservoir.to_numpy(dtype=float) - joined.forecast.to_numpy(dtype=float))))
    if not np.allclose(joined.reservoir, joined.forecast, rtol=0, atol=1e-9, equal_nan=False):
        raise ValueError(f"frozen encoder forecast differs from canonical first-decision forecast: {max_abs_error}")
    joined = _add_side_metrics(joined, joined.direction)
    for key, group in joined.groupby(["panel", "date", "delay"], sort=False):
        for metric in METRICS + ("realized_hold_pts",):
            joined.loc[group.index, f"rank_{metric}"] = group[metric].rank(method="average", pct=True)
    joined["source"] = np.where(joined.panel.eq("external"), "external", "discovery")
    report = {
        "canonical_first_decisions": str(canonical_path),
        "canonical_sha256": _sha256(canonical_path),
        "rows": int(len(joined)),
        "forecast_verified_rows": int(len(joined)),
        "forecast_max_abs_error_points": max_abs_error,
        "panels": {str(k): int(v) for k, v in joined.panel.value_counts().sort_index().items()},
        "delays": {str(k): int(v) for k, v in joined.delay.value_counts().sort_index().items()},
    }
    return joined, report


def _spearman(x: pd.Series, y: pd.Series) -> float | None:
    pair = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(pair) < 3 or pair.x.nunique() < 2 or pair.y.nunique() < 2:
        return None
    rho = spearmanr(pair.x, pair.y).statistic
    return float(rho) if np.isfinite(rho) else None


def _calibration(group: pd.DataFrame, variable: str, label: str) -> dict:
    pair = group[[variable, label]].dropna()
    if not len(pair):
        return {"n": 0, "mean_output": None, "mean_label": None, "mean_error": None,
                "rmse": None, "calibration_intercept": None, "calibration_slope": None,
                "spearman_rho": None}
    x = pair[variable].to_numpy(dtype=float)
    y = pair[label].to_numpy(dtype=float)
    var = float(np.var(x))
    slope = float(np.cov(x, y, ddof=0)[0, 1] / var) if var > 0 else None
    intercept = float(y.mean() - slope * x.mean()) if slope is not None else None
    return {
        "n": int(len(pair)),
        "mean_output": float(x.mean()),
        "mean_label": float(y.mean()),
        "mean_error": float((x - y).mean()),
        "rmse": float(np.sqrt(np.mean((x - y) ** 2))),
        "calibration_intercept": intercept,
        "calibration_slope": slope,
        "spearman_rho": _spearman(pair[variable], pair[label]),
    }


def _draw_dates(panel_dates: dict[str, list[str]], rng: np.random.Generator) -> list[tuple[str, str]]:
    """Stratified circular 5-session blocks, never crossing a panel boundary."""
    sampled = []
    for panel, dates in panel_dates.items():
        n = len(dates)
        if not n:
            continue
        panel_sample = []
        while len(panel_sample) < n:
            start = int(rng.integers(0, n))
            take = min(BLOCK, n - len(panel_sample))
            panel_sample.extend(dates[(start + j) % n] for j in range(take))
        sampled.extend((panel, d) for d in panel_sample[:n])
    return sampled


def _rank_bootstrap(group: pd.DataFrame, rng: np.random.Generator) -> dict:
    if group.empty:
        return {"n": 0, "sessions": 0, "rho": None, "rho_diff_vs_parent_raw": None,
                "rho_diff_vs_sibling_raw": None, "ci95_diff_vs_parent_raw": [None, None],
                "ci95_diff_vs_sibling_raw": [None, None]}
    panel_dates = {str(panel): sorted(g.date.astype(str).unique())
                   for panel, g in group.groupby("panel", sort=True)}
    keys = list(zip(group.panel.astype(str), group.date.astype(str)))
    grouped = {key: g for key, g in group.groupby([group.panel.astype(str), group.date.astype(str)], sort=False)}
    labels = group.realized_hold_pts
    observed = {v: _spearman(group[v], labels) for v in METRICS}
    sibling_raw = {"price_stress_margin": "price_raw", "price_stress_increment": "price_raw",
                   "volume_stress_margin": "parent_raw", "volume_stress_increment": "parent_raw"}
    diff_parent: dict[str, list[float]] = {v: [] for v in METRICS if v != BASE}
    diff_sibling: dict[str, list[float]] = {v: [] for v in sibling_raw}
    for _ in range(BOOTSTRAP_REPS):
        date_draw = _draw_dates(panel_dates, rng)
        pieces = [grouped[key] for key in date_draw if key in grouped]
        boot = pd.concat(pieces, ignore_index=True) if pieces else group.iloc[0:0]
        boot_rho = {var: _spearman(boot[var], boot.realized_hold_pts) for var in METRICS}
        rho_base = boot_rho[BASE]
        for var in diff_parent:
            rho = boot_rho[var]
            if rho is not None and rho_base is not None:
                diff_parent[var].append(rho - rho_base)
        for var, raw in sibling_raw.items():
            rho, rho_raw = boot_rho[var], boot_rho[raw]
            if rho is not None and rho_raw is not None:
                diff_sibling[var].append(rho - rho_raw)

    def interval(values: list[float]) -> list[float | None]:
        return [float(np.quantile(values, .025)), float(np.quantile(values, .975))] if values else [None, None]

    return {
        "n": int(len(group)),
        "sessions": int(group[["panel", "date"]].drop_duplicates().shape[0]),
        "rho": observed,
        "rho_diff_vs_parent_raw": {v: (observed[v] - observed[BASE]) if observed[v] is not None and observed[BASE] is not None else None
                                    for v in METRICS if v != BASE},
        "ci95_diff_vs_parent_raw": {v: interval(diff_parent[v]) for v in diff_parent},
        "rho_diff_vs_sibling_raw": {v: (observed[v] - observed[sibling_raw[v]]) if observed[v] is not None and observed[sibling_raw[v]] is not None else None
                                    for v in sibling_raw},
        "ci95_diff_vs_sibling_raw": {v: interval(diff_sibling[v]) for v in diff_sibling},
        "bootstrap": {"scheme": "paired, panel-stratified circular 5-session blocks", "replicates": BOOTSTRAP_REPS,
                      "seed": SEED, "blocks_do_not_cross_panel_boundaries": True},
    }


def _first_summary(first: pd.DataFrame) -> dict:
    summary: dict[str, Any] = {"by_panel_delay": {}, "rank_bootstrap_by_source_delay": {}}
    for (panel, delay), group in first.groupby(["panel", "delay"], sort=True):
        label = "realized_hold_pts"
        item = {"n": int(len(group)), "sessions": int(group.date.nunique()),
                "mean_signed_realized_hold_points": float(group[label].mean()),
                "metrics": {var: _calibration(group, var, label) for var in METRICS},
                "mean_within_session_pct_rank": {var: float(group[f"rank_{var}"].mean()) for var in METRICS},
                "mean_within_session_label_pct_rank": float(group["rank_realized_hold_pts"].mean())}
        summary["by_panel_delay"][f"{panel}|delay{delay}"] = item

    rng = np.random.default_rng(SEED)
    for (source, delay), group in first.groupby(["source", "delay"], sort=True):
        summary["rank_bootstrap_by_source_delay"][f"{source}|delay{delay}"] = _rank_bootstrap(group, rng)
    return summary


def _entry_signals(root: Path, states: pd.DataFrame, trades_path: Path) -> tuple[pd.DataFrame, dict]:
    trades = pd.read_csv(trades_path)
    trades = trades.loc[trades.model.eq("original") & trades.delay.isin((0, 1))].copy()
    for col in ("signal_time", "entry_time", "exit_time"):
        trades[col] = _ny(trades[col])
    trades["date"] = trades.signal_time.dt.strftime("%Y-%m-%d")
    trades["side_value"] = np.where(trades.side.astype(str).str.lower().eq("long"), 1,
                                    np.where(trades.side.astype(str).str.lower().eq("short"), -1,
                                             pd.to_numeric(trades.side, errors="coerce")))
    if trades.side_value.isna().any() or not trades.side_value.isin((-1, 1)).all():
        raise ValueError("unrecognized direction in frozen original trade ledger")
    join = states.rename(columns={"bar_start": "signal_time"})
    signals = trades.merge(join, on=["panel", "date", "signal_time"], how="left", validate="many_to_one", suffixes=("", "_state"))
    if signals.reservoir.isna().any():
        missing = signals.loc[signals.reservoir.isna(), ["panel", "date", "signal_time"]].head().to_dict("records")
        raise ValueError(f"encoder state missing at parent signal bar: {missing}")
    if not np.allclose(signals.entry_forecast, signals.reservoir, rtol=0, atol=1e-9):
        raise ValueError("parent encoder forecast differs from original signal ledger")
    signals = _add_side_metrics(signals, signals.side_value)
    signals["signed_gross_parent_points"] = signals.side_value * (signals.exit - signals.entry)
    if "gross_usd" in signals and not np.allclose(signals.signed_gross_parent_points * USD_PER_POINT, signals.gross_usd, atol=1e-8):
        raise ValueError("signed gross points disagree with original ledger USD")
    signals["fixed_filter_kept"] = signals.volume_stress_margin > 0.0
    signals["source"] = np.where(signals.panel.eq("external"), "external", "discovery")

    economics = {}
    for source, panel, delay in signals[["source", "panel", "delay"]].drop_duplicates().itertuples(index=False, name=None):
        for kept in (True, False):
            group = signals.loc[
                signals.source.eq(source) & signals.panel.eq(panel) & signals.delay.eq(delay)
                & signals.fixed_filter_kept.eq(kept)
            ]
            points = group.signed_gross_parent_points
            key = f"{source}|{panel}|delay{delay}|{'kept' if kept else 'rejected'}"
            gross = float(group.gross_usd.sum())
            economics[key] = {
                "n": int(len(group)),
                "mean_true_volume_stress_margin_points": float(group.volume_stress_margin.mean()) if len(group) else None,
                "mean_signed_gross_parent_points": float(points.mean()) if len(group) else None,
                "sum_signed_gross_parent_points": float(points.sum()),
                "median_signed_gross_parent_points": float(points.median()) if len(group) else None,
                "positive_gross_rate": float((points > 0).mean()) if len(group) else None,
                "gross_usd": gross,
                "net_usd_by_round_trip_cost": {str(cost): gross - cost * len(group) for cost in COSTS},
            }
    return signals, economics


def _frozen_file_receipts(root: Path) -> dict:
    paths = ("experiments/capacity/neuron.py", "experiments/capacity/protocol.md")
    result = {}
    for rel in paths:
        frozen_blob = subprocess.check_output(
            ["git", "rev-parse", f"546800e:{rel}"], cwd=root, text=True
        ).strip()
        current_blob = subprocess.check_output(
            ["git", "hash-object", rel], cwd=root, text=True
        ).strip()
        result[rel] = {"frozen_blob": frozen_blob, "current_blob": current_blob,
                       "matches_frozen_commit": frozen_blob == current_blob,
                       "sha256": _sha256(root / rel)}
    if not all(item["matches_frozen_commit"] for item in result.values()):
        raise ValueError("capacity neuron/protocol source differs from frozen commit 546800e")
    return result


def run(out_dir: Path = OUT, market_dir: Path = MARKET_DIR) -> dict:
    discovery, external, source_provenance = load_sources(ROOT, market_dir)
    states = _encoder_rows(discovery, external["MNQ.csv"])
    first, first_provenance = _merge_decisions(ROOT, states, CANONICAL)
    first["source"] = np.where(first.panel.eq("external"), "external", "discovery")
    summary = _first_summary(first)
    entries, entry_economics = _entry_signals(ROOT, states, TRADES)

    # Detailed per-session aggregate keeps the original panel distinction and
    # lets reviewers see the within-date ranks carried by the CSV.
    session_summary = {}
    for (source, panel, date, delay), group in first.groupby(["source", "panel", "date", "delay"], sort=True):
        key = f"{source}|{panel}|{date}|delay{delay}"
        session_summary[key] = {
            "n": int(len(group)),
            "mean_signed_realized_hold_points": float(group.realized_hold_pts.mean()),
            "mean_output": {var: float(group[var].mean()) for var in METRICS},
            "spearman_vs_realized_hold": {var: _spearman(group[var], group.realized_hold_pts) for var in METRICS},
            "mean_rank_pct": {var: float(group[f"rank_{var}"].mean()) for var in METRICS},
        }

    result = {
        "description": "Frozen, post-freeze diagnostics on exposed first-eligible observations and original parent entry opportunities; no threshold search.",
        "freeze_commit": "546800e",
        "run_command": "python experiments/capacity/prediction.py --market /workspace/work/market",
        "frozen_model_files": _frozen_file_receipts(ROOT),
        "sources": source_provenance,
        "state_encoder": "experiments.capacity.neuron.encode(bars), run independently per New York session.",
        "forecast_verification": first_provenance,
        "first_eligible_method": {
            "input_rows": "Canonical experiments/hold_work/results/first-decisions.csv.gz; all reference labels, first eligible per trade/delay.",
            "join": "panel, date, decision bar_start; original replay forecast must equal fresh neuron reservoir output within 1e-9 points.",
            "label": "realized_hold_pts from the canonical file, signed in MNQ points from the alternate executable open to frozen original exit.",
            "metrics": {
                "parent_raw": "side * observed parent reservoir forecast (points).",
                "price_raw": "side * identical-charge-marginalized price sibling forecast (points).",
                "price_stress_margin": "A * (side * price_forecast - SHOCK * scale * price_stock); matches the frozen price_long/short output.",
                "volume_stress_margin": "A * (side * parent_forecast_points - SHOCK * scale * observed_volume_stock); true observed-charge margin, matching frozen hold_long/short.",
                "price_stress_increment": "price_stress_margin - price_raw.",
                "volume_stress_increment": "volume_stress_margin - parent_raw.",
            },
            "ranks": "Percentile ranks within panel/date/delay, retained per observation in first-decisions.csv.gz.",
        },
        "first_eligible_summary": summary,
        "per_session_summary": session_summary,
        "entry_signal_method": {
            "input_rows": "All frozen original parent trades, both delays and both source families.",
            "join": "Encoder states at each original signal_time, before entry fill.",
            "label": "signed_gross_parent_points = side * (original exit - original entry), independently verified against gross_usd at $2/point.",
            "fixed_filter": "keep iff true parent volume_stress_margin > 0 on the original signal bar; rejected iff <= 0; no threshold sweep.",
            "costs_usd_round_trip": list(COSTS),
        },
        "entry_opportunities": {
            "n": int(len(entries)),
            "rank_associations": {
                f"{source}|{panel}|delay{delay}": {
                    var: _spearman(group[var], group.signed_gross_parent_points)
                    for var in METRICS
                }
                for (source, panel, delay), group in entries.groupby(["source", "panel", "delay"], sort=True)
            },
            "fixed_filter_economics": entry_economics,
        },
        "paired_block_bootstrap": {
            "scheme": "paired source-level trade-weighted Spearman rank differences; 5-session circular blocks sampled within each panel, with a common resample for all metrics.",
            "block_sessions": BLOCK,
            "replicates": BOOTSTRAP_REPS,
            "seed": SEED,
            "interval": "percentile 95% CI for rho differences.",
        },
        "artifacts": {
            "first_decisions_csv_gz": "experiments/capacity/results/first-decisions.csv.gz",
            "prediction_json": "experiments/capacity/results/prediction.json",
            "entry_trade_source_sha256": _sha256(TRADES),
        },
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    first.to_csv(out_dir / "first-decisions.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    (out_dir / "prediction.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--market", type=Path, default=MARKET_DIR)
    args = parser.parse_args()
    result = run(args.out, args.market)
    print(json.dumps({"first_decision_rows": result["forecast_verification"]["rows"],
                      "entries": result["entry_opportunities"]["n"],
                      "output": str(args.out)}, indent=2))


if __name__ == "__main__":
    main()
