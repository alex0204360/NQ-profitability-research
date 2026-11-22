"""Price-addressed participation cohorts with a recurrent phase latch per seed."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "path_order"))
from brain import area_activations


def weights():
    return json.loads((HERE / "weights.json").read_text())


def trace(closes, encoded, cfg):
    """Advance slots from completed closes. A slot can enter the active phase once."""
    size = cfg["age_limit_bars"]
    # 0 empty, 1 deposited, 2 departed, 3 live. Overwrite on the 32nd new bar.
    phase = np.zeros(size, dtype=int)
    anchor = np.zeros(size)
    width = np.ones(size)
    side = np.zeros(size)
    mass = np.zeros(size)
    confirmed = np.zeros(size, dtype=bool)
    previous_oriented = np.zeros(size)
    turn_weights = np.array(cfg["confirmation"])
    charge_weights = np.array(cfg["charge"])
    surfaces = np.array(cfg["surfaces"])
    target_weights = np.array(cfg["target"])
    rows = []
    for i, (close, fields) in enumerate(zip(closes, encoded.itertuples(), strict=True)):
        if fields.age == 1:
            phase.fill(0)
            confirmed.fill(False)
        slot = i % size
        phase[slot] = 0
        confirmed[slot] = False
        offset = (close - anchor) / width
        oriented = side * offset
        coordinates = np.stack([oriented, np.ones(size)])
        at_target, at_contact, on_original_side = surfaces @ coordinates
        # Evaluate old phases first. Departure and return require distinct closes.
        live = phase == 3
        phase[live & ((at_target >= 0) | (on_original_side < 0))] = 0
        touch = (phase == 2) & (at_contact >= 0)
        phase[touch] = np.where(on_original_side[touch] >= 0, 3, 0)
        departed = (phase == 1) & (np.abs(offset) >= cfg["departure_ranges"])
        side[departed] = np.sign(offset[departed])
        phase[departed] = 2

        active = phase == 3
        outbound = turn_weights @ np.stack([oriented, previous_oriented]) > 0
        new_confirmations = live & active & ~confirmed & outbound
        confirmed |= new_confirmations
        previous_oriented = oriented
        residual = side * width * (target_weights @ coordinates)
        active_mass = mass * active
        equal = cfg["equal_mass"] * active
        def readout(votes):
            return (votes @ residual) / max(cfg["mass_floor"], votes.sum())

        charge = max(0., charge_weights @ [fields.effort, max(0., fields.motion),
                                            max(0., -fields.motion)])
        if charge > 0:
            phase[slot] = 1
            anchor[slot], width[slot], mass[slot], side[slot] = close, fields.scale, charge, 0.
        eligible = fields.age >= 32
        rows.append((charge, int(departed.sum()), int(touch.sum()), int((touch & (on_original_side < 0)).sum()),
                     int(active.sum()), active_mass.sum(), readout(active_mass) if eligible else np.nan,
                     readout(equal) if eligible else np.nan, int(new_confirmations.sum()),
                     int((active & confirmed).sum()), readout(active_mass * confirmed) if eligible else np.nan,
                     readout(equal * confirmed) if eligible else np.nan))
    return pd.DataFrame(rows, index=encoded.index, columns=[
        "charge", "departures", "contacts", "crossed_at_contact", "live_sites",
        "live_mass", "return_map", "equal_mass", "confirmations", "confirmed_sites",
        "confirmed", "confirmed_equal"])


def encode(bars):
    return trace(bars.close, area_activations(bars), weights())
