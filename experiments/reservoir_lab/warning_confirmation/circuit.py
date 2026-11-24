"""A one-observation price memory attached only to discretionary exit warnings."""
import json
import math
from pathlib import Path

from experiments.reservoir_lab.trade_memory.routing import TradeMemory

WEIGHTS = json.loads(Path(__file__).with_name("weights.json").read_text())


class WarningMemory(TradeMemory):
    def __init__(self, activations, shocks, mode):
        if mode not in ("confirm", "delay"):
            raise ValueError("expected confirm or delay")
        super().__init__(activations, shocks, local_exit=True, fresh_entry=True)
        self.mode = mode
        self.pending = None
        self.events = []

    def close_scores(self, i, close, raw, position, exited, contiguous, long_hold, short_hold):
        entry, immediate = super().close_scores(i, close, raw, position, exited, contiguous,
                                                long_hold, short_hold)
        stamp = self.activation.index[i]
        if self.pending is not None and (position is None or not contiguous):
            self.events.append((stamp, self.pending[0], "forced", None))
            self.pending = None
        if position is None:
            return entry, immediate
        side = position["side"]
        oriented = side * close
        carry = WEIGHTS["carry_weight"] * side * raw
        if not math.isfinite(carry) or carry <= 0:
            if self.pending is not None:
                self.events.append((stamp, self.pending[0], "raw_exit", None))
                self.pending = None
            return entry, immediate

        if self.pending is not None:
            warning_time, level = self.pending
            self.pending = None
            current_weight, stored_weight = WEIGHTS["oriented_displacement"]
            distance = current_weight * oriented + stored_weight * level
            if self.mode == "delay" or distance <= WEIGHTS["confirmation_boundary_points"]:
                self.events.append((stamp, warning_time, "exit", distance))
                return entry, min(0., distance)
            self.events.append((stamp, warning_time, "reclaimed", distance))

        if immediate <= 0:
            retain, write = WEIGHTS["memory_write"]
            self.pending = (stamp, retain * 0.0 + write * oriented)
            self.events.append((stamp, stamp, "warning", None))
            return entry, carry
        return entry, immediate
