"""Score the prespecified return decomposition on the first reachable warning."""
import argparse
import hashlib
import heapq
import json
from pathlib import Path

import numpy as np
import pandas as pd

MINUTE = pd.Timedelta(minutes=1)
KEY = ["source", "delay", "trade_id", "issue"]
MODELS = ["zero", "previous_grid", "unweighted", "survival_feasibility", "survival_laplace", "survival_grid"]


def load_decisions(root):
    prior = pd.read_csv(root / "reachable_value/results/predictions.csv.gz")
    prior["issue"] = pd.to_datetime(prior.issue, utc=True)
    prior = prior.rename(columns={"grid": "previous_grid"})
    activations = pd.read_csv(root / "capacity/results/activations.csv.gz", usecols=[
        "panel", "model", "delay", "trade_id", "bar_start", "direction", "original_exit_time",
        "original_exit_price", "next_executable_time", "next_executable_price"])
    activations = activations[activations.model == "original"].copy()
    activations["issue"] = pd.to_datetime(activations.bar_start, utc=True) + MINUTE
    activations["source"] = np.where(activations.panel == "external", "external60", "discovery40")
    decisions = prior.merge(activations, on=KEY, how="left", validate="one_to_one")
    assert decisions.direction.notna().all()
    decisions = decisions.rename(columns={"next_executable_price": "early_price"})
    decisions["early_time"] = pd.to_datetime(decisions.next_executable_time, utc=True)
    decisions["terminal_time"] = pd.to_datetime(decisions.original_exit_time, utc=True)
    decisions["confirmed"] = decisions.issue + MINUTE
    decisions["response_time"] = decisions.confirmed + pd.to_timedelta(decisions.delay, unit="min")
    decisions["split_time"] = decisions[["response_time", "terminal_time"]].min(axis=1)
    assert (decisions.early_time <= decisions.split_time).all()
    scores = pd.read_csv(root / "capacity/results/scores.csv.gz", usecols=["bar_start", "panel", "open"])
    scores["split_time"] = pd.to_datetime(scores.bar_start, utc=True)
    decisions = decisions.merge(scores[["panel", "split_time", "open"]], on=["panel", "split_time"],
                                how="left", validate="many_to_one")
    ended = decisions.split_time == decisions.terminal_time
    np.testing.assert_array_equal(decisions.loc[ended, "open"], decisions.loc[ended, "original_exit_price"])
    decisions["before_response"] = decisions.direction * (decisions.open - decisions.early_price)
    decisions["remaining"] = decisions.direction * (decisions.original_exit_price - decisions.open)
    known = decisions.remaining.notna()
    np.testing.assert_array_equal((decisions.before_response + decisions.remaining)[known], decisions.y[known])
    warnings = pd.read_csv(root / "reversal_hazard/results/warnings.csv.gz",
                           usecols=["source", "stamp", "grid", "feasibility", "laplace"])
    warnings["issue"] = pd.to_datetime(warnings.stamp, utc=True) + MINUTE
    probabilities = warnings.rename(columns={k: "prob_" + k for k in ("grid", "laplace", "feasibility")})
    return decisions.merge(probabilities.drop(columns="stamp"), on=["source", "issue"], how="left",
                           validate="many_to_one")


def forecast(cohort):
    cohort = cohort.sort_values("issue").copy()
    pending = []
    settled_count, settled_sum = 0, 0.
    forecasts = []
    for row in cohort.itertuples():
        while pending and pending[0][0] < row.issue:
            _, value = heapq.heappop(pending)
            settled_sum += value
            settled_count += 1
        unweighted = row.entry_scale * settled_sum / (16 + settled_count)
        prediction = {"prior_survivals": settled_count, "unweighted": unweighted}
        for name in ("feasibility", "laplace", "grid"):
            probability = getattr(row, "prob_" + name)
            assert 0 <= probability < 1
            prediction["survival_" + name] = (1 - probability) * unweighted
        forecasts.append(prediction)
        if row.reversal == 0 and pd.notna(row.remaining):
            maturity = max(row.terminal_time, row.confirmed)
            heapq.heappush(pending, (maturity, row.remaining / row.entry_scale))
    scores = pd.DataFrame(forecasts, index=cohort.index)
    for name in ("feasibility", "laplace", "grid"):
        np.testing.assert_array_equal(scores["survival_" + name] < 0, scores.unweighted < 0)
    return cohort.join(scores)


def summarize(cohort, baseline):
    valid = cohort.dropna(subset=["remaining", "reversal", "y", *MODELS]).copy()
    dates = sorted(baseline.date.unique())
    n = len(dates)
    starts = np.random.default_rng(604).integers(n, size=(10000, (n + 4) // 5, 1))
    blocks = ((starts + np.arange(5)) % n).reshape(10000, -1)[:, :n]
    counts = valid.groupby("date").size().reindex(dates, fill_value=0).to_numpy()[blocks].sum(axis=1)
    report = dict(original_trades=len(baseline), scheduled=len(cohort), scored=len(valid), branches={}, models={})
    for flip, group in valid.groupby("reversal"):
        report["branches"][int(flip)] = dict(n=len(group), split_at_exit=int((group.split_time == group.terminal_time).sum()),
            mean_pre=group.before_response.mean(), mean_remaining=group.remaining.mean(), mean_total=group.y.mean(),
            nonzero_remaining=int(group.remaining.ne(0).sum()))
    for name in MODELS:
        err = (valid[name] - valid.y) ** 2
        increment = -2 * valid.y.where(valid[name] < 0, 0).sum()
        model = dict(mse=err.mean(), early_exits=int((valid[name] < 0).sum()), increment_usd=increment,
                     net={cost:float((baseline.gross_usd-cost).sum() + increment) for cost in (3,6,9)})
        if name == "survival_grid":
            for control in ("zero", "previous_grid"):
                diff = err - (valid[control] - valid.y) ** 2
                daily = diff.groupby(valid.date).sum().reindex(dates, fill_value=0).to_numpy()
                sums = daily[blocks].sum(axis=1)
                model["mse_minus_" + control] = dict(delta=diff.mean(),
                    ci95=np.quantile(sums[counts>0]/counts[counts>0], [.025,.975]).tolist())
        report["models"][name] = model
    report["always_exit_increment_usd"] = -2 * valid.y.sum()
    return report


def run(root, dest):
    decisions = load_decisions(root)
    trades = pd.read_csv(root / "capacity/results/trades.csv.gz")
    trades = trades[trades.model == "original"].copy()
    trades["source"] = np.where(trades.panel == "external", "external60", "discovery40")
    output, report = [], {}
    for (source, delay), cohort in decisions.groupby(["source", "delay"]):
        rows = forecast(cohort)
        baseline = trades[trades.source.eq(source) & trades.delay.eq(delay)]
        report.setdefault(source, {})[int(delay)] = summarize(rows, baseline)
        output.append(rows)
    report["input_sha256"] = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [
        root / "reachable_value/results/predictions.csv.gz", root / "capacity/results/activations.csv.gz",
        root / "capacity/results/scores.csv.gz", root / "capacity/results/trades.csv.gz",
        root / "reversal_hazard/results/warnings.csv.gz"]}
    dest.mkdir(parents=True, exist_ok=True)
    pd.concat(output).to_csv(dest / "decisions.csv.gz", index=False, compression={"method":"gzip", "mtime":0})
    (dest / "summary.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("experiments", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    run(args.experiments, args.output)
