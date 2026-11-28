"""Independent vectorized policy-table replay and scalar spot checks.

Reads only the archived transmitted_move opportunities and policy_bound table
receipt. It does not rebuild or alter the episode model.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "transmitted_move" / "results"
DELAYS = (0, 1, 9, 60)
COSTS = (3, 6, 9)


def load_inputs():
    opportunities = pd.read_csv(SOURCE / "opportunities.csv.gz")
    tables = pd.read_csv(HERE / "results" / "tables.csv.gz")
    for name in ("signal", "requested_entry", "entry_time", "exit_time"):
        opportunities[name] = pd.to_datetime(opportunities[name], utc=True)
    schedule = json.loads((SOURCE / "schedule.json").read_text())
    return opportunities, tables, schedule


def cells_from_code(codes: list[str]) -> np.ndarray:
    # Independent decode of F / R / . columns to signed table actions.
    return np.asarray([[{"F": 1, "R": -1, ".": 0}[letter] for letter in code]
                       for code in codes], dtype=np.int8)


def vectorized_replay(opportunities: pd.DataFrame, cells: np.ndarray):
    n_tables = len(cells)
    gross = np.zeros((len(DELAYS), n_tables), dtype=np.float64)
    counts = np.zeros((len(DELAYS), n_tables), dtype=np.int64)
    # Each day owns a fresh busy clock for every counterfactual table.
    for (date, delay), day in opportunities.groupby(["date", "delay"], sort=True):
        j = DELAYS.index(int(delay))
        busy = np.full(n_tables, -1, dtype=np.int64)
        for row in day.sort_values("signal").itertuples():
            cell = (4 * int(row.leader) + 2 * int(int(row.direction) > 0)
                    + int(row.kind == "continuation"))
            action = cells[:, cell]
            signal_ns = row.signal.value
            selected = (action != 0) & (signal_ns >= busy)
            if pd.isna(row.entry_time):
                # Cancellation releases occupancy at the schedule's first known
                # following timestamp, matching the archived opportunity clock.
                busy[selected] = (row.requested_entry + pd.Timedelta(seconds=2)).value
                continue
            if pd.isna(row.exit_time):
                raise ValueError(f"unresolved opportunity on {date}, delay {delay}")
            entry_ns, exit_ns = row.entry_time.value, row.exit_time.value
            busy[selected] = exit_ns
            counts[j, selected] += 1
            pnl = 2.0 * int(row.direction) * action * (float(row.exit) - float(row.entry))
            gross[j, selected] += pnl[selected]
    return gross, counts


def scalar_replay(opportunities: pd.DataFrame, code: str, delay: int):
    """One-table event replay; deliberately not using the vector subset method."""
    action_for = [{"F": 1, "R": -1, ".": 0}[c] for c in code]
    count = 0
    gross = 0.0
    for _, day in opportunities.loc[opportunities.delay.eq(delay)].groupby("date", sort=True):
        busy_until = None
        for row in day.sort_values("signal").itertuples():
            cell = (4 * int(row.leader) + 2 * int(int(row.direction) > 0)
                    + int(row.kind == "continuation"))
            action = action_for[cell]
            if not action or (busy_until is not None and row.signal < busy_until):
                continue
            if pd.isna(row.entry_time):
                busy_until = row.requested_entry + pd.Timedelta(seconds=2)
                continue
            if pd.isna(row.exit_time):
                raise ValueError(f"unresolved opportunity on {row.date}, delay {delay}")
            count += 1
            gross += 2.0 * int(row.direction) * action * (float(row.exit) - float(row.entry))
            busy_until = row.exit_time
    return count, gross


def main():
    opportunities, archived, schedule = load_inputs()
    dates = schedule["scheduled_dates"]
    if len(dates) != 27 or not set(opportunities.date).issubset(dates):
        raise AssertionError("opportunity sessions fall outside the archived 27-date schedule")
    if len(archived) != 3 ** 8:
        raise AssertionError(f"expected 6561 tables, found {len(archived)}")
    codes = archived.code.astype(str).tolist()
    cells = cells_from_code(codes)
    gross, counts = vectorized_replay(opportunities, cells)

    # Full all-table reconciliation to archived counts and net at every friction.
    mismatches = []
    for j, delay in enumerate(DELAYS):
        target_counts = archived[f"trades_{delay}"].to_numpy(dtype=np.int64)
        if not np.array_equal(counts[j], target_counts):
            mismatch = np.flatnonzero(counts[j] != target_counts)
            mismatches.append(f"delay={delay} trade counts mismatch in {len(mismatch)} tables")
        for cost in COSTS:
            net = gross[j] - cost * counts[j]
            target = archived[f"net_{delay}_{cost}"].to_numpy(dtype=float)
            if not np.allclose(net, target, rtol=0, atol=1e-8):
                mismatch = np.flatnonzero(np.abs(net-target) > 1e-8)
                mismatches.append(f"delay={delay} cost={cost} net mismatch in {len(mismatch)} tables")
    if mismatches:
        raise AssertionError("; ".join(mismatches))

    # Scalars independently replay all-follow, all-fade, cash, every best
    # exposed table at each delay/cost, and a deterministic 32-code stratum.
    stratified = set(np.linspace(0, len(codes)-1, 32, dtype=int).tolist())
    special_codes = {"FFFFFFFF", "RRRRRRRR", "........"}
    for delay in DELAYS:
        j = DELAYS.index(delay)
        for cost in COSTS:
            net = gross[j] - cost * counts[j]
            exposed = counts[j] > 0
            best_index = np.flatnonzero(exposed)[np.argmax(net[exposed])]
            special_codes.add(codes[int(best_index)])
        special_codes.update(codes[i] for i in stratified)
    scalar_checks = 0
    for code in sorted(special_codes):
        idx = codes.index(code)
        for j, delay in enumerate(DELAYS):
            n, g = scalar_replay(opportunities, code, delay)
            if n != counts[j, idx] or abs(g - gross[j, idx]) > 1e-8:
                raise AssertionError(
                    f"scalar mismatch {code} delay={delay}: {(n,g)} vs "
                    f"{(counts[j,idx],gross[j,idx])}")
            scalar_checks += 1
    mixed_checked = sum(len(set(code)) > 1 for code in special_codes)
    if mixed_checked < 30:
        raise AssertionError(f"only {mixed_checked} mixed table codes scalar-checked")

    print(f"full table reconciliation: {len(codes)} codes x {len(DELAYS)} delays x {len(COSTS)} costs matched")
    print(f"independent scalar replay: {len(special_codes)} table codes x {len(DELAYS)} delays = {scalar_checks} checks matched; {mixed_checked} mixed codes")
    for delay in DELAYS:
        j = DELAYS.index(delay)
        for cost in COSTS:
            net = gross[j] - cost * counts[j]
            exposed = counts[j] > 0
            best_index = np.flatnonzero(exposed)[np.argmax(net[exposed])]
            print(f"delay={delay}s cost=${cost}: best noncash {codes[best_index]} "
                  f"trades={counts[j,best_index]} net=${net[best_index]:.2f}; "
                  f"all-follow={net[codes.index('FFFFFFFF')]:.2f}, "
                  f"all-fade={net[codes.index('RRRRRRRR')]:.2f}, "
                  f"cash={net[codes.index('........')]:.2f}")
    for cost in (6, 9):
        robust = np.minimum((gross[1] - cost * counts[1]),
                            (gross[2] - cost * counts[2]))
        both_exposed = (counts[1] > 0) & (counts[2] > 0)
        best = float(robust.max())
        best_active = float(robust[both_exposed].max())
        positive = int((robust > 0).sum())
        print(f"worse of 1s/9s at ${cost}: maximum=${best:.2f}; "
              f"best exposed=${best_active:.2f}; positive tables={positive}")
    unresolved = int(opportunities.exit_time.isna().sum())
    if unresolved:
        raise AssertionError(f"{unresolved} opportunity exits are unresolved")
    print(f"archived opportunities={len(opportunities)}; unresolved exits={unresolved}")


if __name__ == "__main__":
    main()
