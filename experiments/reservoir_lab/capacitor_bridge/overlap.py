"""Four separate exposure clocks sum to one normalized log-width."""
import math
import numpy as np

from risk_head import CFG, H, INITIAL, RiskCapacitor


class ExposureClock(RiskCapacitor):
    def __init__(self):
        super().__init__()
        self.plates=np.full(H,math.log(INITIAL))

    def feedback(self,origin,miss):
        lane=(origin.hour*60+origin.minute)%H
        self.plates[lane]+=CFG["log_gain"]*(float(miss)-(1-CFG["coverage"]))
        self.log_scale=float(np.mean(self.plates))
