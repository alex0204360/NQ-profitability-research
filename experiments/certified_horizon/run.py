"""Check the structural horizon on every registered issuance, including censored paths."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .bound import DECAY, earliest_flip


def audit_day(day):
    day = day.sort_values("stamp").reset_index(drop=True)
    f = (day.reservoir / day.scale).to_numpy()
    stock = day.stock.to_numpy()
    charge = day.charge.to_numpy()
    motion = day.motion.clip(-1, 1).to_numpy()
    valid = np.isfinite(f) & (day.stamp.dt.strftime("%H:%M") < "15:55").to_numpy()
    contiguous = day.stamp.diff().eq(pd.Timedelta(minutes=1)).to_numpy()
    rows = []
    for i in np.flatnonzero(day.issued.eq(True)):
        sign = np.sign(f[i])
        h = earliest_flip(f[i], stock[i])
        possible = h == 1
        assert possible == day.possible.iat[i]
        # The held side/sign is fixed at the issued state for this path.
        deficit = abs(f[i]) - stock[i]
        charge_floor = DECAY * max(deficit, 0)
        observed = 0
        first_flip = None
        identity_error = None
        next_reachable = None
        near = None
        for j in range(i + 1, len(day)):
            if not (contiguous[j] and valid[j]):
                break
            observed = j-i
            if j == i+1:
                projected = DECAY*(deficit + 2*stock[i]*max(sign*motion[j], 0)) - charge[j]
                actual = sign*f[j] - stock[j]
                identity_error = abs(projected - actual)
                assert identity_error < 1e-11
                if not possible:
                    assert sign*f[j] > 0
                    next_reachable = abs(f[j]) <= stock[j]
                    if next_reachable:
                        assert charge[j] + 1e-12 >= charge_floor
                near = abs(actual) < 1e-12
            if sign*f[j] <= 0:
                first_flip = observed
                assert first_flip >= h
                break
        # A right-censored long-lived state still supplies every strict-prefix check.
        rows.append(dict(date=day.date.iat[i], source=day.source.iat[i], stamp=day.stamp.iat[i],
                         held=bool(day.held.iat[i]), normalized_forecast=f[i], stock=stock[i],
                         earliest=h, contiguous_observed=observed, first_observed_flip=first_flip,
                         earliest_resolved=observed>=h, flipped_at_earliest=first_flip==h,
                         prefix_checked=min(observed,h-1), next_charge_floor=charge_floor,
                         next_charge=charge[i+1] if observed else None, next_reachable=next_reachable,
                         deficit_identity_error=identity_error, near_next_deficit_zero=near))
    return rows


def describe(group):
    distribution = {}
    for h, rows in group.groupby("earliest"):
        scored = rows[rows.earliest_resolved]
        distribution[int(h)] = dict(issued=len(rows), examined_to_h=len(scored), at_h=int(scored.flipped_at_earliest.sum()),
            rate=float(scored.flipped_at_earliest.mean()) if len(scored) else None)
    transitions = group[group.next_reachable.eq(True)]
    return dict(issued=len(group), by_earliest=distribution,
                guaranteed_unchanged={k:int((group.earliest > k).sum()) for k in (1,2,3)},
                strict_prefix_checks=int(group.prefix_checked.sum()), gaps_or_cutoff_before_h=int((~group.earliest_resolved).sum()),
                first_flip_observed=int(group.first_observed_flip.notna().sum()),
                max_deficit_identity_error=float(group.deficit_identity_error.max()),
                near_next_deficit_zero=int(group.near_next_deficit_zero.eq(True).sum()),
                immune_with_next_observation=int(group.next_reachable.notna().sum()),
                immune_becoming_reachable=len(transitions),
                max_required_charge_on_transition=float(transitions.next_charge_floor.max()) if len(transitions) else None)


def run(root, out):
    scores = root / "capacity/results/scores.csv.gz"
    warnings = root / "reversal_hazard/results/warnings.csv.gz"
    base = pd.read_csv(scores, usecols=["date","panel","bar_start","reservoir","scale","stock","charge","motion"])
    base["stamp"] = pd.to_datetime(base.bar_start, utc=True).dt.tz_convert("America/New_York")
    base["source"] = np.where(base.panel.eq("external"), "external60", "discovery40")
    issued = pd.read_csv(warnings, usecols=["stamp","source","possible","held"])
    issued["stamp"] = pd.to_datetime(issued.stamp, utc=True).dt.tz_convert("America/New_York")
    merged = base.merge(issued.assign(issued=True), on=["source","stamp"], how="left", validate="one_to_one")
    records = []
    for _, day in merged.groupby(["source","date"], sort=True):
        records.extend(audit_day(day))
    frame = pd.DataFrame(records)
    assert len(frame) == len(issued)
    report = {source:{"all":describe(g),"held":describe(g[g.held])} for source,g in frame.groupby("source")}
    report["input_sha256"] = {f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in (scores,warnings)}
    out.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out/"horizons.csv.gz", index=False, compression={"method":"gzip","mtime":0})
    (out/"summary.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("experiments", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    run(args.experiments,args.output)
