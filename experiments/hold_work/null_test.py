"""Exhaustive length-12 fair-walk null diagnostic for the frozen hold heads.

No market data is read. Every +/-1 close path has equal probability; exits at a
signal close are valued at that close, the stipulated zero-gap next opening.
"""
from __future__ import annotations

import itertools
import json
from collections import Counter
from pathlib import Path

from .circuit import Head
from .symmetric import SymmetricHead

LENGTH = 12
SCALE = 2.0
VOLUME = 10.0
PRIOR_VOLUME = 10.0
PATHS = 2 ** LENGTH


def branch_pulses(head):
    """Return frozen-circuit evidence for +/- one move from pre-bar state."""
    magnitude = 1.0
    gap = head.peak - head.last
    up = magnitude - 0.5 * min(magnitude, gap)
    down = -magnitude - 0.5 * min(magnitude, head.repair)
    return up, down, (up + down) / 2.0


def run_path(moves):
    heads = {"uncentered": Head(1, 0.0, SCALE),
             "centered": SymmetricHead(1, 0.0, SCALE)}
    close = 0.0
    first_eligible = {name: None for name in heads}
    stop_depth = {name: None for name in heads}
    pulse_rows = []
    prior_rows = {name: [] for name in heads}
    centered_pulses = {name: [] for name in heads}
    score_replay = {name: SCALE for name in heads}

    for depth, move in enumerate(moves, start=1):
        pre = heads["uncentered"]
        up, down, neutral = branch_pulses(pre)
        close += move
        for name, head in heads.items():
            prior_before = head.scale * (0.75 ** (depth - 1))
            state = head.step(close - move, max(close - move, close),
                              min(close - move, close), close, VOLUME, PRIOR_VOLUME)
            pulse = state["evidence"]
            centered_pulse = state.get("centered_pulse", pulse)
            # The initialized score contributes only this geometrically decayed prior.
            prior_rows[name].append(0.75 * prior_before)
            score_replay[name] = 0.75 * score_replay[name] + centered_pulse
            assert abs(head.price - score_replay[name]) < 1e-12
            centered_pulses[name].append(centered_pulse)
            if first_eligible[name] is None and state["eligible"]:
                first_eligible[name] = depth
            if (stop_depth[name] is None and state["eligible"]
                    and state["price"] <= 0):
                stop_depth[name] = depth
            if name == "uncentered":
                raw_pulse = pulse
                assert pulse == (up if move > 0 else down)
            else:
                corrected_pulse = centered_pulse
        assert abs(corrected_pulse - (raw_pulse - neutral)) < 1e-12
        pulse_rows.append((raw_pulse, neutral, corrected_pulse))

    horizon_points = close
    gross = {"horizon": horizon_points}
    for name in heads:
        depth = stop_depth[name]
        # Save the close at each depth while re-walking moves to value the first stop.
        if depth is None:
            gross[name] = horizon_points
        else:
            gross[name] = sum(moves[:depth])
    return first_eligible, stop_depth, gross, pulse_rows, prior_rows


def main():
    pulse_sums = [Counter() for _ in range(LENGTH)]
    prior_sums = {name: [0.0] * LENGTH for name in ("uncentered", "centered")}
    first_eligible_counts = {name: Counter() for name in prior_sums}
    first_stop_counts = {name: Counter() for name in prior_sums}
    stopped = Counter()
    gross_sum = Counter()
    gross_increment_sum = Counter()
    paths_checked = 0

    for moves in itertools.product((-1, 1), repeat=LENGTH):
        eligible, stop_depth, gross, pulse_rows, prior_rows = run_path(moves)
        paths_checked += 1
        for name in prior_sums:
            if eligible[name] is not None:
                first_eligible_counts[name][eligible[name]] += 1
            if stop_depth[name] is not None:
                first_stop_counts[name][stop_depth[name]] += 1
                stopped[name] += 1
            gross_sum[name] += gross[name]
            gross_increment_sum[name] += gross[name] - gross["horizon"]
            for depth, prior in enumerate(prior_rows[name]):
                prior_sums[name][depth] += prior
        gross_sum["horizon"] += gross["horizon"]
        for depth, (raw, neutral, centered) in enumerate(pulse_rows):
            pulse_sums[depth]["raw"] += raw
            pulse_sums[depth]["neutral"] += neutral
            pulse_sums[depth]["centered"] += centered

    assert paths_checked == PATHS
    pulse_by_depth = []
    for i, counts in enumerate(pulse_sums, start=1):
        pulse_by_depth.append({
            "depth": i,
            "raw_mean": counts["raw"] / PATHS,
            "neutral_mean": counts["neutral"] / PATHS,
            "centered_mean": counts["centered"] / PATHS,
        })
    prior_by_depth = {
        name: [{"depth": i + 1, "mean_prior_component": total / PATHS,
                "theoretical": SCALE * (0.75 ** (i + 1))}
               for i, total in enumerate(values)]
        for name, values in prior_sums.items()
    }

    # Exact rational receipts: sums in points over 4096 equally weighted paths.
    result = {
        "protocol": "symmetric_protocol.md",
        "diagnostic": "exhaustive fair symmetric +/-1 paths; no market data",
        "path_length": LENGTH,
        "path_count": PATHS,
        "initial_scale_points": SCALE,
        "volume": VOLUME,
        "prior_mean_volume": PRIOR_VOLUME,
        "normal_participation": 1.0,
        "pulse_checks_by_depth": pulse_by_depth,
        "prior_component_by_depth": prior_by_depth,
        "first_eligible_path_counts": {
            name: {str(k): v for k, v in sorted(counts.items())}
            for name, counts in first_eligible_counts.items()},
        "first_stop_path_counts": {
            name: {str(k): v for k, v in sorted(counts.items())}
            for name, counts in first_stop_counts.items()},
        "stopped_path_count": dict(stopped),
        "gross_points": {
            name: {"sum_over_paths": int(total), "mean": total / PATHS}
            for name, total in gross_sum.items()},
        "gross_increment_vs_horizon_points": {
            name: {"sum_over_paths": int(total), "denominator": PATHS,
                   "mean": total / PATHS}
            for name, total in gross_increment_sum.items()},
    }
    assert all(row["centered_mean"] == 0 for row in pulse_by_depth)
    assert all(row["raw_mean"] == row["neutral_mean"] for row in pulse_by_depth)
    assert all(abs(row["mean_prior_component"] - row["theoretical"]) < 1e-12
               for rows in prior_by_depth.values() for row in rows)
    assert all(total == 0 for total in gross_increment_sum.values())
    output = Path(__file__).resolve().parent / "results" / "null.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "paths": paths_checked,
        "uncentered_stops": stopped["uncentered"],
        "centered_stops": stopped["centered"],
        "gross_increment_sums": dict(gross_increment_sum),
        "output": str(output),
    }, indent=2))


if __name__ == "__main__":
    main()
