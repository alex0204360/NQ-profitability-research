"""Independent raw-label and forecast verification for the frozen hazard run."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
BUNDLE = HERE.parent / "capacity" / "results"
GRID = np.arange(17, dtype=float) / 16.0
PRIOR = 20.0
MINUTE = pd.Timedelta(minutes=1)


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_sources():
    summary = json.loads((RESULTS / "summary.json").read_text())
    for name, expected in summary["source_sha256"].items():
        actual = sha(BUNDLE / name)
        if actual != expected:
            raise AssertionError(f"source digest mismatch for {name}: {actual}")
    scores = pd.read_csv(BUNDLE / "scores.csv.gz",
                         usecols=["panel", "date", "bar_start", "close", "high", "low",
                                  "scale", "stock", "reservoir"])
    activations = pd.read_csv(BUNDLE / "activations.csv.gz",
                              usecols=["bar_start", "panel", "model", "delay"])
    activations = activations.loc[activations.model.eq("original") & activations.delay.eq(0),
                                  ["bar_start", "panel"]].drop_duplicates().assign(held=True)
    scores = scores.merge(activations, on=["bar_start", "panel"], how="left", validate="one_to_one")
    scores["held"] = scores.held.eq(True)
    scores["stamp"] = pd.to_datetime(scores.pop("bar_start"), utc=True).dt.tz_convert("America/New_York")
    return scores, summary


def prior_grid():
    return 0.5 * np.exp(-2.0 * GRID)


def independent_issue(scores):
    rows = []
    scored = scores.copy()
    scored["source"] = np.where(scored.panel.eq("external"), "external60", "discovery40")
    for source_name, frame in scored.groupby("source", sort=True):
        memory_n = memory_reversals = memory_possible = 0
        exceedances = np.zeros(len(GRID), dtype=np.int64)
        for date, day in frame.groupby("date", sort=True):
            day = day.sort_values("stamp").reset_index(drop=True)
            next_scales = []
            previous_stamp = None
            state = None
            for bar in day.itertuples():
                width = float(bar.high - bar.low)
                if previous_stamp is None or bar.stamp - previous_stamp != MINUTE:
                    state = max(0.25, width)
                state = state * (31.0 / 32.0) + width / 32.0
                next_scales.append(max(0.25, state))
                previous_stamp = bar.stamp
            day["next_scale"] = next_scales
            issued = day.loc[
                day.reservoir.notna() & day.reservoir.ne(0)
                & ((day.stamp + MINUTE).dt.strftime("%H:%M") < "15:55")
            ].copy()
            if not len(issued):
                continue
            # Make predictions solely from state settled through the prior date.
            ratio = (issued.reservoir.abs() / issued.scale).div(issued.stock.where(issued.stock.gt(0)))
            ratio = ratio.fillna(np.inf).to_numpy(dtype=float)
            possible = ratio <= 1.0
            h = (exceedances + PRIOR * prior_grid()) / (memory_n + PRIOR)
            issued["ratio"] = ratio
            issued["possible"] = possible
            issued["prior_n"] = memory_n
            issued["prior_possible"] = memory_possible
            issued["constant"] = (memory_reversals + PRIOR / 16.0) / (memory_n + PRIOR)
            issued["feasibility"] = np.where(possible,
                (memory_reversals + PRIOR / 4.0) / (memory_possible + PRIOR), 0.0)
            issued["laplace"] = np.where(possible, 0.5 * np.exp(-2.0 * ratio), 0.0)
            issued["grid"] = np.where(possible, np.interp(ratio, GRID, h), 0.0)
            # Current outcome is read only after forecasts for the day are frozen.
            next_data = day.set_index("stamp")[["reservoir", "close", "scale"]]
            next_keys = pd.DatetimeIndex(issued.stamp) + MINUTE
            future = next_data.reindex(next_keys)
            future.index = issued.index
            issued["resolved"] = future.reservoir.notna()
            issued["reversal"] = (future.reservoir.to_numpy()
                                   * np.sign(issued.reservoir.to_numpy()) <= 0).astype(float)
            issued.loc[~issued.resolved, "reversal"] = np.nan
            issued["adverse"] = (
                -np.sign(issued.reservoir.to_numpy())
                * (future.close.to_numpy() - issued.close.to_numpy())
                / issued.next_scale.to_numpy()
            )
            issued.loc[~issued.resolved, "adverse"] = np.nan
            if issued.resolved.any():
                expected_next_scale = future.loc[issued.resolved, "scale"].to_numpy(dtype=float)
                actual_next_scale = issued.loc[issued.resolved, "next_scale"].to_numpy(dtype=float)
                np.testing.assert_allclose(actual_next_scale, expected_next_scale, rtol=1e-12, atol=1e-12)
                true_reversal = issued.loc[issued.resolved, "reversal"].to_numpy(dtype=bool)
                event_possible = issued.loc[issued.resolved, "possible"].to_numpy(dtype=bool)
                event_adverse = issued.loc[issued.resolved, "adverse"].to_numpy(dtype=float)
                event_ratio = issued.loc[issued.resolved, "ratio"].to_numpy(dtype=float)
                np.testing.assert_array_equal(event_possible & (event_adverse >= event_ratio), true_reversal)
                # Only now settle this completed session into prior memory.
                memory_n += len(event_adverse)
                memory_reversals += int(true_reversal.sum())
                memory_possible += int(event_possible.sum())
                exceedances += (event_adverse[:, None] >= GRID[None, :]).sum(axis=0)
            issued["source"] = source_name
            rows.append(issued)
    return pd.concat(rows, ignore_index=True)


def compare(ours, archive):
    keys = ["source", "stamp"]
    merged = archive.merge(ours, on=keys, how="outer", suffixes=("_archive", "_ours"),
                           indicator=True, validate="one_to_one")
    if not merged._merge.eq("both").all():
        raise AssertionError(f"warning row keys differ: {merged._merge.value_counts().to_dict()}")
    bool_cols = ["held", "possible", "resolved"]
    int_cols = ["prior_n", "prior_possible"]
    float_cols = ["close", "reservoir", "stock", "scale", "next_scale", "ratio",
                  "constant", "feasibility", "laplace", "grid", "reversal", "adverse"]
    for col in bool_cols:
        np.testing.assert_array_equal(merged[f"{col}_archive"], merged[f"{col}_ours"])
    for col in int_cols:
        np.testing.assert_array_equal(merged[f"{col}_archive"], merged[f"{col}_ours"])
    for col in float_cols:
        np.testing.assert_allclose(merged[f"{col}_archive"], merged[f"{col}_ours"],
                                   rtol=1e-12, atol=1e-12, equal_nan=True)


def main():
    scores, summary = parse_sources()
    ours = independent_issue(scores)
    archive = pd.read_csv(RESULTS / "warnings.csv.gz")
    archive["stamp"] = pd.to_datetime(archive.stamp, utc=True).dt.tz_convert("America/New_York")
    ours["stamp"] = pd.to_datetime(ours.stamp, utc=True).dt.tz_convert("America/New_York")
    compare(ours, archive)
    print(f"source hashes verified; recomputed {len(ours):,} warning rows; exact key/count/forecast comparisons passed")

    for source, frame in ours.groupby("source", sort=True):
        resolved = frame.loc[frame.resolved].copy()
        counts = {"issued": len(frame), "resolved": len(resolved),
                  "censored": int((~frame.resolved).sum()),
                  "reversals": int(resolved.reversal.sum()),
                  "reachable": int(resolved.possible.sum()),
                  "held": int(resolved.held.sum()),
                  "held_reachable": int((resolved.held & resolved.possible).sum())}
        expected = summary[source]
        assert counts["issued"] == expected["issued"]
        assert counts["censored"] == expected["censored"]
        for subset, selected in (("all", resolved), ("reachable", resolved[resolved.possible]),
                                 ("held", resolved[resolved.held]),
                                 ("held_reachable", resolved[resolved.held & resolved.possible])):
            assert len(selected) == expected["subsets"][subset]["n"]
            assert int(selected.reversal.sum()) == expected["subsets"][subset]["reversals"]
        print(source, counts)
        # Inspect one representative of each edge case plus a few ordinary cases.
        sample = frame.iloc[[0, min(1, len(frame)-1), min(100, len(frame)-1), len(frame)-1]]
        print(sample[["stamp", "ratio", "possible", "prior_n", "constant", "feasibility",
                      "laplace", "grid", "resolved", "reversal", "adverse", "held"]]
              .to_string(index=False))


if __name__ == "__main__":
    main()
