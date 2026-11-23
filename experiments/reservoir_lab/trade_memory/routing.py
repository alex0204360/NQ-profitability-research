"""Two boundary-gated recurrent state adjustments; raw market encoder is frozen."""
from pathlib import Path
import json
import math
import numpy as np

CFG = json.loads(Path(__file__).with_name("weights.json").read_text())


class TradeMemory:
    def __init__(self, activation, shocks, local_exit, fresh_entry):
        self.activation = activation
        self.shocks = shocks
        self.local_exit = local_exit
        self.fresh_entry = fresh_entry
        self.matrix = np.asarray(CFG["shadow_state_weights"])
        self.reset_matrix = np.asarray(CFG["flat_reset_weights"])
        self.hold_weights = np.asarray(CFG["local_pulse_readout"])
        self.audit = []
        self.flat_side = 0
        self.stock = self.forecast = 0.
        self.previous_close = math.nan
        self.low = self.high = self.peak = math.nan
        self.armed = False

    def close_scores(self, i, close, raw, position, exited, contiguous, long_hold, short_hold):
        """Invoked after open fills, at completed bar close; returns entry and selected hold score."""
        row = self.activation.iloc[i]
        ts = self.activation.index[i]
        side = 0 if position is None else position["side"]
        if not contiguous:
            self.flat_side = 0
        if self.fresh_entry and exited and exited["reason"] == "hold":
            self.flat_side = 1 if exited["side"] == "long" else -1
            self.stock,self.forecast = self.reset_matrix @ [self.stock,self.forecast]
        if side or not math.isfinite(raw) or self.flat_side * raw <= 0:
            self.flat_side = 0
        entry = raw
        fresh_score = math.nan
        if self.flat_side:
            u = np.clip(row.motion,-1,1)
            self.stock,self.forecast = self.matrix @ [
                (1-abs(u))*self.stock, u*self.stock,self.forecast,row.charge]
            fresh_score = row.scale*self.forecast
            entry = self.flat_side*max(0., min(self.flat_side*raw, self.flat_side*fresh_score))

        hold = long_hold if side == 1 else short_hold
        pulse = 0.
        if self.local_exit and side:
            x = side*close
            if position["entry_time"] == ts:
                self.low = self.high = self.peak = math.nan
                self.armed = False
            else:
                if math.isfinite(self.low):
                    if x >= self.high:
                        self.low = self.high = self.peak = math.nan
                        self.armed = False
                    elif self.armed and x < self.low:
                        pulse = self.peak-x
                        self.low = self.high = self.peak = math.nan
                        self.armed = False
                    elif x >= self.low+(self.high-self.low)*0.5:
                        self.armed = True
                        self.peak = max(self.peak,x)
                if self.shocks[side][i] and not self.armed and pulse == 0 and (
                        not math.isfinite(self.low) or x < self.low):
                    self.low,self.high,self.peak = x,side*self.previous_close,x
            hold = self.hold_weights @ [side*raw,pulse]
        self.previous_close=close
        blocked=bool(self.flat_side and abs(raw)>CFG["hurdle"] and abs(entry)<=CFG["hurdle"])
        self.audit.append((self.flat_side,fresh_score,blocked,pulse))
        return entry,hold
