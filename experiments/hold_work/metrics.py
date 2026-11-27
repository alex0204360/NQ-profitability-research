"""Trade, mark-to-market, and first-decision metrics for exposed research."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd
from scipy.stats import rankdata

USD_PER_POINT = 2.0
COSTS = (3, 6, 9)
DRAWDOWN_BUDGET = 1500.0
ENTRY_KEY = ["session", "entry_index", "side"]


def _mean(values: np.ndarray | pd.Series) -> float | None:
    return float(np.mean(values)) if len(values) else None


def _gross(trades: pd.DataFrame) -> pd.Series:
    return USD_PER_POINT * trades["side"] * (trades["exit_price"] - trades["entry_price"])


def _keys(trades: pd.DataFrame) -> set[tuple]:
    return set(trades[ENTRY_KEY].itertuples(index=False, name=None))


def paired_effects(original: pd.DataFrame, candidate: pd.DataFrame) -> dict:
    """Compare exactly paired entries, classifying original P&L at each cost."""
    original = original.set_index(ENTRY_KEY, verify_integrity=True)
    candidate = candidate.set_index(ENTRY_KEY, verify_integrity=True)
    if set(original.index) != set(candidate.index):
        raise ValueError("Fixed-entry ledgers have different entries")
    candidate = candidate.reindex(original.index)
    if not original["entry_price"].equals(candidate["entry_price"]):
        raise ValueError("Fixed-entry ledgers have different entry prices")
    side = original.index.get_level_values("side")
    base_gross = USD_PER_POINT * side * (original["exit_price"] - original["entry_price"])
    candidate_gross = USD_PER_POINT * side * (candidate["exit_price"] - candidate["entry_price"])
    delta = candidate_gross - base_gross
    gains = delta[delta > 0].sort_values(ascending=False)
    sessions = delta.groupby(level="session", sort=False).sum()
    favorable_sessions = sessions[sessions > 0].sort_values(ascending=False)
    delta_usd = float(delta.sum())

    by_cost = {}
    for cost in COSTS:
        losing = base_gross < cost
        winning = base_gross > cost
        neutral = base_gross == cost
        by_cost[str(cost)] = {
            "original_net": float((base_gross - cost).sum()),
            "candidate_net": float((candidate_gross - cost).sum()),
            "net_improvement": delta_usd,
            "original_losers": int(losing.sum()),
            "original_winners": int(winning.sum()),
            "original_breakeven": int(neutral.sum()),
            "losses_saved": float(delta[losing].clip(lower=0).sum()),
            "losses_added": float(-delta[losing].clip(upper=0).sum()),
            "loser_net_change": float(delta[losing].sum()),
            "winner_gains_added": float(delta[winning].clip(lower=0).sum()),
            "winner_gains_surrendered": float(-delta[winning].clip(upper=0).sum()),
            "winner_net_change": float(delta[winning].sum()),
            "breakeven_net_change": float(delta[neutral].sum()),
        }

    return {
        "entries": len(delta),
        "changed_exit_count": int((original["exit_index"] != candidate["exit_index"]).sum()),
        "positive_effect_count": len(gains),
        "negative_effect_count": int((delta < 0).sum()),
        "positive_effect_sum": float(gains.sum()),
        "negative_effect_sum": float(delta[delta < 0].sum()),
        "top_gain_share": {str(k): float(gains.head(k).sum() / gains.sum()) if len(gains) else None
                           for k in (1, 3, 5)},
        "leave_best_trade_out": {str(k): delta_usd - float(gains.head(k).sum())
                                 for k in (1, 3, 5)},
        "leave_best_session_out": delta_usd - float(favorable_sessions.head(1).sum()),
        "session_delta": {str(day): float(value) for day, value in sessions.items()},
        "costs": by_cost,
    }


def drawdown_bounds(equity: pd.DataFrame) -> dict:
    """Return exact close-mark DD and bounds with unknown within-bar high/low order.

    The event stream is chronological. Point events have equal open, low, high,
    and close. A full held bar has all four marks. Bounds account for both
    possible orderings of its extremes, since each bar's ending peak is fixed.
    """
    peak = peak_close = lower = upper = marked = 0.0
    columns = ["open", "low", "high", "close", "is_close"]
    equity = equity.assign(is_close=True) if "is_close" not in equity else equity
    for start, low, high, close, is_close in equity[columns].itertuples(index=False, name=None):
        if not low <= min(start, close) <= max(start, close) <= high:
            raise ValueError("Equity path contains an invalid range")
        if is_close:
            peak_close = max(peak_close, close)
            marked = max(marked, peak_close - close)
        peak = max(peak, start)
        lower = max(lower, peak - low, high - close)
        upper = max(upper, max(peak, high) - low)
        peak = max(peak, high)
    return {"marked_drawdown": marked, "intrabar_drawdown_lower": lower,
            "intrabar_drawdown_upper": upper, "marked_budget_margin": DRAWDOWN_BUDGET - marked,
            "intrabar_upper_budget_margin": DRAWDOWN_BUDGET - upper,
            "drawdown_budget": DRAWDOWN_BUDGET}


def summarize_strategy(
    trades: pd.DataFrame,
    equity: pd.DataFrame,
    session_minutes: int,
    cost: float,
) -> dict:
    gross = _gross(trades)
    net = gross - cost
    hold_minutes = trades["exit_index"] - trades["entry_index"]
    hold_total = int(hold_minutes.sum())
    losses = -net[net < 0].sum()
    winners = net[net > 0].sort_values(ascending=False)
    session_net = net.groupby(trades["session"]).sum()
    occupied_bars = int(equity["occupied"].sum()) if "occupied" in equity else hold_total
    return {
        "trades": len(trades),
        "gross": float(gross.sum()),
        "transaction_cost": len(trades) * cost,
        "net": float(net.sum()),
        "net_winners": int((net > 0).sum()),
        "net_losers": int((net < 0).sum()),
        "net_breakeven": int((net == 0).sum()),
        "mean_net": _mean(net),
        "profit_factor": float(net[net > 0].sum() / losses) if losses > 0 else None,
        "hold_minutes": hold_total,
        "mean_hold_minutes": _mean(hold_minutes),
        "available_minutes": session_minutes,
        "occupied_observed_bars": occupied_bars,
        "occupancy": occupied_bars / session_minutes if session_minutes else None,
        "leave_best_winning_trades_out_net": {
            str(k): float(net.sum() - winners.head(k).sum()) for k in (1, 3, 5)
        },
        "leave_best_winning_session_out_net": float(
            net.sum() - session_net[session_net > 0].nlargest(1).sum()
        ),
        **drawdown_bounds(equity),
    }


def full_effects(original: pd.DataFrame, candidate: pd.DataFrame) -> dict:
    """Describe realized changes when exits alter eligibility for subsequent entries."""
    before = _keys(original)
    after = _keys(candidate)
    added = candidate.loc[[key not in before for key in candidate[ENTRY_KEY].itertuples(index=False,
                                                                                       name=None)]]
    missed = original.loc[[key not in after for key in original[ENTRY_KEY].itertuples(index=False,
                                                                                     name=None)]]
    early_release = []
    same_side = []
    original_sessions = dict(tuple(original.groupby("session", sort=False)))
    for row in added.itertuples(index=False):
        original_session = original_sessions.get(row.session)
        if original_session is None:
            continue
        occupying = original_session.loc[
            (original_session["entry_index"] < row.entry_index)
            & (row.entry_index < original_session["exit_index"])
        ]
        if len(occupying):
            early_release.append(row)
            if row.side == occupying.iloc[0]["side"]:
                same_side.append(row)
    original_gross = _gross(original)
    candidate_gross = _gross(candidate)
    session_gross_delta = candidate_gross.groupby(candidate["session"]).sum().subtract(
        original_gross.groupby(original["session"]).sum(), fill_value=0
    )
    session_trade_delta = candidate.groupby("session").size().subtract(
        original.groupby("session").size(), fill_value=0
    )
    return {
        "matched_entries": len(before & after),
        "added_entries": len(added),
        "missed_entries": len(missed),
        "added_while_original_held": len(early_release),
        "same_side_reentries_while_original_held": len(same_side),
        "costs": {
            str(cost): {
                "added_entry_net": float((_gross(added) - cost).sum()),
                "missed_original_entry_net": float((_gross(missed) - cost).sum()),
                "incremental_transaction_cost": (len(candidate) - len(original)) * cost,
                "net_improvement": float(candidate_gross.sum() - original_gross.sum()
                                         - (len(candidate) - len(original)) * cost),
                "leave_best_improving_session_out": float(
                    (session_gross_delta - cost * session_trade_delta).sum()
                    - (session_gross_delta - cost * session_trade_delta).clip(lower=0).nlargest(1).sum()
                ),
            }
            for cost in COSTS
        },
    }


def _spearman(first: np.ndarray, second: np.ndarray) -> float | None:
    if len(first) < 2:
        return None
    x = rankdata(first)
    y = rankdata(second)
    x -= x.mean()
    y -= y.mean()
    denominator = np.linalg.norm(x) * np.linalg.norm(y)
    return float(np.dot(x, y) / denominator) if denominator else None


def _correlations(
    target: np.ndarray, scores: Mapping[str, np.ndarray], control: str
) -> dict[str, float | None]:
    results = {name: _spearman(values, target) for name, values in scores.items()}
    control_stat = results[control]
    for name in scores:
        if name != control:
            statistic = results[name]
            results[f"{name}_minus_{control}"] = (
                statistic - control_stat if statistic is not None and control_stat is not None else None
            )
    return results


def predictive_metrics(
    observations: pd.DataFrame,
    scores: Sequence[str],
    control: str,
    *,
    bootstrap_draws: int = 999,
    seed: int = 42,
) -> dict:
    """Score independent first-decision rows with a paired session bootstrap.

    Supply the original exit price even for trades a policy would have ended
    early. Discard only rows with missing common scores or an unavailable label.
    """
    if control not in scores:
        raise ValueError("The control score must be specified in scores")
    if observations.duplicated(ENTRY_KEY).any():
        raise ValueError("Predictive observations must contain at most one row per original trade")
    common = observations.copy()
    common["label"] = common["side"] * (common["original_exit_price"] - common["next_open"])
    numeric = common[["label", *scores]].to_numpy(dtype=float)
    common = common.loc[np.isfinite(numeric).all(axis=1)].reset_index(drop=True)
    target = common["label"].to_numpy(dtype=float)
    score_arrays = {name: common[name].to_numpy(dtype=float) for name in scores}
    results = _correlations(target, score_arrays, control)
    clusters = [group.index.to_numpy() for _, group in common.groupby("session", sort=False)]
    bootstrap: dict[str, list[float]] = {name: [] for name in results}
    if len(clusters) >= 2:
        rng = np.random.default_rng(seed)
        for draw in rng.integers(len(clusters), size=(bootstrap_draws, len(clusters))):
            indices = np.concatenate([clusters[cluster] for cluster in draw])
            sampled = {name: values[indices] for name, values in score_arrays.items()}
            for name, value in _correlations(target[indices], sampled, control).items():
                if value is not None:
                    bootstrap[name].append(value)

    statistics = {}
    for name, values in score_arrays.items():
        bins = []
        for low, high in ((-np.inf, -10), (-10, 0), (0, 10), (10, np.inf)):
            selected = (values >= low) & (values < high)
            bins.append({
                "score_lower_inclusive": low if np.isfinite(low) else None,
                "score_upper_exclusive": high if np.isfinite(high) else None,
                "trades": int(selected.sum()),
                "mean_score_pts": _mean(values[selected]),
                "mean_realized_hold_pts": _mean(target[selected]),
                "positive_realized_fraction": _mean(target[selected] > 0),
            })
        hold = values > 0
        nonzero = (values != 0) & (target != 0)
        statistics[name] = {
            "mean_score_pts": _mean(values),
            "mean_error_pts": _mean(values - target),
            "mean_abs_error_pts": _mean(np.abs(values - target)),
            "sign_agreement_nonzero": _mean(np.sign(values[nonzero]) == np.sign(target[nonzero])),
            "sign_agreement_nonzero_trades": int(nonzero.sum()),
            "positive_score_trades": int(hold.sum()),
            "mean_label_positive_score_pts": _mean(target[hold]),
            "mean_label_nonpositive_score_pts": _mean(target[~hold]),
            "mean_holding_policy_increment_pts": _mean(np.where(hold, target, 0)),
            "calibration_bins": bins,
        }
    return {
        "observations": len(observations),
        "trades_with_all_scores_and_label": len(common),
        "sessions_with_all_scores_and_label": len(clusters),
        "mean_realized_hold_pts": _mean(target),
        "positive_realized_fraction": _mean(target > 0),
        "scores": statistics,
        "spearman_and_paired_differences": {
            name: {
                "estimate": value,
                "session_bootstrap_percentile_95": np.percentile(bootstrap[name], [2.5, 97.5]).tolist()
                if bootstrap[name] else None,
                "defined_bootstrap_draws": len(bootstrap[name]),
            }
            for name, value in results.items()
        },
    }


def normalize_trades(trades: pd.DataFrame) -> pd.DataFrame:
    """Translate a replay CSV ledger to the common metrics schema."""
    result = trades.rename(columns={"date": "session", "entry_time": "entry_index",
                                    "exit_time": "exit_index", "entry": "entry_price",
                                    "exit": "exit_price"}).copy()
    result["session"] = result["session"].astype(str)
    result["side"] = result["side"].map({"long": 1, "short": -1})
    if result["side"].isna().any():
        raise ValueError("Unrecognized trade direction")
    for name in ("entry_index", "exit_index"):
        result[name] = pd.to_datetime(result[name], utc=True).dt.as_unit("ns").astype("int64") // 60_000_000_000
    return result


def first_decisions(activations: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Choose one discretionary observation before the cutoff on each original trade."""
    original = activations.loc[activations["model"] == "original"].copy()
    original["session"] = original["date"].astype(str)
    original["side"] = original["direction"].astype(int)
    original["entry_index"] = pd.to_datetime(original["entry_time"], utc=True).dt.as_unit("ns").astype("int64") // 60_000_000_000
    original["next_open"] = original["next_executable_price"]
    eligible = original.loc[original["eligible"]]
    discretionary = eligible.loc[eligible["discretionary"]]
    first = discretionary.sort_values("bar_start").drop_duplicates(ENTRY_KEY).copy()
    executable = (first["next_executable_time"].str.slice(11, 16).lt("15:55")
                  & first["next_open"].notna())
    first.loc[~executable, "next_open"] = np.nan
    first["realized_hold_pts"] = first["side"] * (first["original_exit_price"] - first["next_open"])
    return first, {
        "original_trades": len(_keys(original)),
        "trades_ever_eligible": len(_keys(eligible)),
        "trades_eligible_with_discretion": len(_keys(discretionary)),
        "trades_with_first_decision": len(first),
        "eligible_rows_without_discretion": len(eligible) - len(discretionary),
        "first_decisions_without_executable_pre_cutoff_open": int((~executable).sum()),
    }


def equity_events(trades: pd.DataFrame, bars: pd.DataFrame, cost: float) -> pd.DataFrame:
    """Construct equity OHLC for each held bar, plus open-fill equity events."""
    events = []
    realized = 0.0
    position = None
    previous_sessions_net = 0.0
    for session, tape in bars.groupby("date", sort=True):
        ledger = trades.loc[trades["session"] == str(session)]
        entries = {trade.entry_index: trade for trade in ledger.itertuples(index=False)}
        tape = tape.sort_values("bar_start")
        times = pd.to_datetime(tape["bar_start"], utc=True).dt.as_unit("ns").astype("int64") // 60_000_000_000
        for index, bar in zip(times, tape.itertuples(index=False), strict=True):
            if position is not None and index == position.exit_index:
                if bar.open != position.exit_price:
                    raise ValueError("Expected a bar-open exit")
                gross = USD_PER_POINT * position.side * (position.exit_price - position.entry_price)
                pre_exit = realized + gross - cost / 2
                events.append((pre_exit, pre_exit, pre_exit, pre_exit, False, False))
                realized += gross - cost
                events.append((realized, realized, realized, realized, False, False))
                position = None
            if index in entries:
                if position is not None or bar.open != entries[index].entry_price:
                    raise ValueError("Expected one position and a bar-open entry")
                position = entries[index]
            if position is None:
                events.append((realized, realized, realized, realized, True, False))
            else:
                prices = np.array([bar.open, bar.low, bar.high, bar.close])
                marks = (realized - cost / 2
                         + USD_PER_POINT * position.side * (prices - position.entry_price))
                events.append((marks[0], min(marks[1:3]), max(marks[1:3]), marks[3], True, True))
            expected = float(events[-1][3])
            recorded = bar.gross_equity_usd - cost * (bar.completed_trades + bar.occupancy / 2)
            if abs(expected - (previous_sessions_net + recorded)) > 1e-7:
                raise ValueError("Reconstructed bar mark disagrees with replay")
        if position is not None:
            raise ValueError(f"Unclosed position in session {session}")
        previous_sessions_net = realized
    return pd.DataFrame(events, columns=["open", "low", "high", "close", "is_close", "occupied"])


def analyze_directory(replay_dir, output_dir) -> dict:
    """Create economic and predictive summaries from an archived replay bundle."""
    import json

    output_dir.mkdir(parents=True, exist_ok=True)
    raw = pd.read_csv(replay_dir / "trades.csv.gz")
    trades = normalize_trades(raw)
    activations = pd.read_csv(replay_dir / "activations.csv.gz", low_memory=False)
    equity = pd.read_csv(replay_dir / "equity.csv.gz")
    # Discovery archives use the same feed across their disjoint dates.
    discovery_panels = ("earlier20", "november14", "replication5", "nov25")
    discovery_dates = equity.loc[equity["panel"].isin(discovery_panels), ["panel", "date"]]
    if discovery_dates["panel"].nunique() == len(discovery_panels):
        if discovery_dates.drop_duplicates()["date"].duplicated().any():
            raise ValueError("Discovery panels overlap")
        def pooled(frame):
            selected = frame.loc[frame["panel"].isin(discovery_panels)]
            return pd.concat([frame, selected.assign(panel="discovery40")], ignore_index=True)
        trades, activations, equity = (pooled(frame) for frame in (trades, activations, equity))
    report = {}
    all_first = []
    for (panel, delay), bar_group in equity.groupby(["panel", "delay"], sort=True):
        subset = trades.loc[(trades["panel"] == panel) & (trades["delay"] == delay)]
        traces = activations.loc[(activations["panel"] == panel) & (activations["delay"] == delay)]
        tape = dict(tuple(bar_group.groupby("model", sort=True)))
        by_model = {model: subset.loc[subset["model"] == model] for model in tape}
        original = by_model["original"]
        scores = tuple(name for name in ("volume_score", "price_score", "trail_score") if name in traces)
        first, eligibility = first_decisions(traces)
        if panel != "discovery40":
            all_first.append(first)
        report.setdefault(str(panel), {})[str(delay)] = {
            "delay_additional_minutes": int(delay),
            "sessions": int(tape["original"]["date"].nunique()),
            "strategy": {
                model: {
                    str(cost): summarize_strategy(
                        by_model[model], equity_events(by_model[model], bars, cost), len(bars), cost
                    ) for cost in COSTS
                } for model, bars in tape.items()
            },
            "paired": {model: paired_effects(original, subset)
                       for model, subset in by_model.items() if model.startswith("fixed_")},
            "full_vs_original": {model: full_effects(original, subset)
                                 for model, subset in by_model.items() if model.startswith("full_")},
            "predictive": {"eligibility": eligibility,
                           **predictive_metrics(first, scores, "price_score")},
        }

    for panel in report.values():
        if "0" in panel and "1" in panel:
            initial, delayed = (panel[delay]["strategy"] for delay in ("0", "1"))
            panel["1"]["additional_delay_effect_vs_next_open"] = {
                model: {
                    cost: {
                        field: delayed[model][cost][field] - initial[model][cost][field]
                        for field in ("net", "trades", "marked_drawdown", "intrabar_drawdown_upper",
                                      "transaction_cost", "occupancy")
                    } for cost in initial[model]
                } for model in initial
            }

    (output_dir / "metrics.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    pd.concat(all_first, ignore_index=True).to_csv(
        output_dir / "first-decisions.csv.gz", index=False, compression={"method": "gzip", "mtime": 0}
    )
    for cost, name in ((3, "hold-value-cases.html"), (6, "hold-value-cases-cost6.html")):
        chart_cases(raw, activations, equity, output_dir / name, cost)
    return report


def _svg_series(title, series, markers=()):
    """Render self-contained vector lines with timestamp tooltips."""
    import html

    samples = [(time, value) for _, _, points in series for time, value in points
               if np.isfinite(value)]
    samples += [(time, value) for time, value, _, _ in markers]
    if not samples:
        return ""
    first, last = min(time for time, _ in samples), max(time for time, _ in samples)
    minimum, maximum = min(value for _, value in samples), max(value for _, value in samples)
    spread = max(maximum - minimum, 1)
    width, height = 900, 255

    def x(time):
        return 68 + 809 * (time - first).total_seconds() / max((last - first).total_seconds(), 60)

    def y(value):
        return 214 - 185 * (value - minimum + 0.08 * spread) / (1.16 * spread)

    svg = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(title)}">']
    for number in range(5):
        value = minimum + number * (maximum - minimum) / 4
        svg.append(f'<path d="M68,{y(value):.1f} H877" stroke="#e2e9f0"/>')
        svg.append(f'<text x="62" y="{y(value) + 4:.1f}" text-anchor="end">{value:,.1f}</text>')
        time = first + (last - first) * number / 4
        svg.append(f'<text x="{x(time):.1f}" y="238" text-anchor="middle">{time:%H:%M}</text>')
    for name, color, points in series:
        coordinates = " ".join(f"{x(time):.1f},{y(value):.1f}" for time, value in points
                               if np.isfinite(value))
        svg.append(f'<polyline points="{coordinates}" fill="none" stroke="{color}" stroke-width="2.3">'
                   f'<title>{html.escape(name)}</title></polyline>')
    for time, value, color, label in markers:
        svg.append(f'<circle cx="{x(time):.1f}" cy="{y(value):.1f}" r="5" fill="{color}" stroke="white">'
                   f'<title>{html.escape(label)} · {time:%H:%M} · {value:,.2f}</title></circle>')
    svg.append("</svg>")
    legend = "".join(f'<span style="color:{color}">{html.escape(name)}</span>' for name, color, _ in series)
    return f"<h3>{html.escape(title)}</h3><div class=legend>{legend}</div>" + "".join(svg)


def chart_cases(trades, activations, equity, destination, cost):
    """Plot fixed-volume cases at the requested next-open cost and Nov 19."""
    import html

    base = trades.loc[(trades["delay"] == 0) & (trades["model"] == "original")]
    volume = trades.loc[(trades["delay"] == 0) & (trades["model"] == "fixed_volume")]
    join = ["panel", "date", "trade_id"]
    paired = base.merge(volume[join + ["exit_time", "exit", "net_usd"]],
                        on=join, suffixes=("_base", "_volume"), validate="one_to_one")
    paired["net_usd_base"] += 6 - cost
    paired["net_usd_volume"] += 6 - cost
    paired["delta"] = paired["net_usd_volume"] - paired["net_usd_base"]
    cases = []
    saved = paired.loc[paired["delta"] > 0]
    harmed = paired.loc[(paired["net_usd_base"] > 0) & (paired["delta"] < 0)]
    if len(saved):
        cases.append(("Largest fixed-entry gain", saved.loc[saved["delta"].idxmax()]))
    if len(harmed):
        cases.append(("Largest loss of an original winner’s profit", harmed.loc[harmed["delta"].idxmin()]))
    parts = ["""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MNQ hold value case studies</title>
<style>
body{margin:auto;max-width:980px;padding:24px;font:16px system-ui;color:#182637;background:#f7f9fc}
section{background:white;padding:22px;margin:18px 0;border:1px solid #e2e9f0;border-radius:12px}
h1,h2,h3{margin:0 0 6px} h3{margin-top:22px;font-size:1em}
p{line-height:1.5} svg{width:100%;height:auto} svg text{font:12px system-ui;fill:#435468}
.legend{font-size:.86em;display:flex;flex-wrap:wrap;gap:16px}
</style><h1>MNQ hold value case studies</h1>
<p>Original reservoir and fixed-entry volume exit on replayed one-minute bars. Fills use the next
open. P&amp;L includes $COST per round trip. Times are New York time. Hold scores use points.</p>
<p>Markers show fill prices. Hover over a marker for the time and price.</p>
""".replace("$COST", f"${cost}")]
    for name, row in cases:
        tape = equity.loc[(equity["panel"] == row["panel"]) & (equity["date"] == row["date"])
                          & (equity["delay"] == 0) & (equity["model"] == "original")].copy()
        time = pd.to_datetime(tape["bar_start"], utc=True).dt.tz_convert("America/New_York")
        entry, exit_base, exit_vol = [
            pd.Timestamp(row[column]) for column in ("entry_time", "exit_time_base", "exit_time_volume")
        ]
        period = time.between(entry - pd.Timedelta(minutes=3), exit_base + pd.Timedelta(minutes=3))
        trace = activations.loc[(activations["panel"] == row["panel"])
                                & (activations["date"] == row["date"])
                                & (activations["delay"] == 0) & (activations["model"] == "original")
                                & (activations["trade_id"] == row["trade_id"])]
        trace_time = pd.to_datetime(trace["bar_start"], utc=True).dt.tz_convert("America/New_York")
        parts.append(f"<section><h2>{html.escape(name)} · {row['date']}</h2>"
                     f"<p>{html.escape(row['side'].title())} at {entry:%H:%M} in "
                     f"{html.escape(row['panel'])}. Original net ${row['net_usd_base']:,.2f} "
                     f"and volume exit net ${row['net_usd_volume']:,.2f}. "
                     f"Paired change ${row['delta']:,.2f}.</p>")
        parts.append(_svg_series("MNQ price (pts)", [
            ("Minute close", "#233c56", list(zip(time[period], tape.loc[period, "close"])))
        ], [
            (entry, row["entry"], "#166534", "Shared entry"),
            (exit_base, row["exit_base"], "#b83a39", "Original exit"),
            (exit_vol, row["exit_volume"], "#5b3bb6", "Volume exit"),
        ]))
        parts.append(_svg_series("Forecast and signed hold scores (pts)", [
            ("Forecast (pts)", "#233c56", list(zip(trace_time, trace["forecast"]))),
            ("Hold value (pts), volume", "#5b3bb6", list(zip(trace_time, trace["volume_score"]))),
            ("Hold value (pts), price", "#9a4f00", list(zip(trace_time, trace["price_score"]))),
        ]))
        parts.append("</section>")

    nov = paired.loc[paired["date"] == "2026-11-19"]
    if len(nov):
        panel = "november14" if "november14" in set(nov["panel"]) else nov["panel"].iloc[0]
        nov = nov.loc[nov["panel"] == panel]
        tape = equity.loc[(equity["panel"] == panel) & (equity["date"] == "2026-11-19")
                          & (equity["delay"] == 0)]
        lines = []
        for model, name, color in (
            ("original", "Original exit", "#233c56"), ("fixed_volume", "Volume exit", "#5b3bb6"),
            ("fixed_price", "Price exit", "#9a4f00"), ("fixed_trail", "Volatility trail", "#166534"),
        ):
            data = tape.loc[tape["model"] == model]
            times = pd.to_datetime(data["bar_start"], utc=True).dt.tz_convert("America/New_York")
            marks = data["gross_equity_usd"] - cost * (data["completed_trades"] + data["occupancy"] / 2)
            lines.append((name, color, list(zip(times, marks))))
        parts.append(f"<section><h2>November 19, 2026</h2>"
                     f"<p>{len(nov)} original entries in {html.escape(panel)}. This is an exposed "
                     "session selected for explanation.</p>")
        parts.append(_svg_series("Identical-entry marked equity (USD)", lines))
        parts.append("</section>")
    parts.append("</html>\n")
    destination.write_text("".join(parts))


def main():
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("replay", type=Path, help="directory containing archived replay ledgers")
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    analyze_directory(arguments.replay, arguments.output)


if __name__ == "__main__":
    main()
