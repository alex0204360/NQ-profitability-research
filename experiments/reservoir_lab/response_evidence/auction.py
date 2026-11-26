"""Track retention of the first half-hour move into the closing auction."""
from datetime import time
import numpy as np
import pandas as pd

from simulator import TRADE_COLUMNS

OPEN = time(9,30)
LOCK = time(9,59)
DECIDE = time(15,29)
ENTER = time(15,30)
EXIT = time(15,55)
COST_POINTS = 3.
HORIZON_RATIO = 25/30


def states(b):
    """Emit decisions only at the close of 15:29 and require an unbroken prefix."""
    memory = []
    opening = displacement = None
    mass = work = equal_work = count = 0.
    previous = None
    for row in b.itertuples():
        now = row.Index.time()
        if previous is not None and (row.Index-previous).total_seconds()!=60:
            opening = displacement = None
        previous = row.Index
        if now==OPEN:
            opening = row.open
        if now==LOCK and opening is not None:
            displacement = row.close-opening
        if LOCK < now <= DECIDE and displacement is not None:
            # +1 at or beyond the launch endpoint; -1 at or behind its origin.
            typical = (row.high+row.low+row.close)/3
            support = float(np.clip(2*(typical-opening)/displacement-1,-1,1)) if displacement else 0.
            work += row.volume*support
            mass += row.volume
            equal_work += support
            count += 1
            if now==DECIDE:
                terminal = 2*(row.close-opening)/displacement-1 if displacement else 0.
                score = HORIZON_RATIO*displacement
                for name,mean in (("auction",work/mass if mass else 0.),("auction_equal",equal_work/count)):
                    memory.append((name,score*max(0., min(1., terminal, mean))))
                memory.extend([("open_only",score),("always_long",float("inf"))])
    return memory


def strategies(b):
    result = {n:pd.DataFrame(columns=TRADE_COLUMNS) for n in ("auction","auction_equal","open_only","always_long")}
    for name,score in states(b):
        if abs(score)<=COST_POINTS:
            continue
        ts = b.index[b.index.time==DECIDE][0]
        next_ts = ts + pd.Timedelta(minutes=1)
        if next_ts not in b.index:
            continue
        exit_ts = next_ts
        while exit_ts.time()<EXIT:
            i = b.index.get_loc(exit_ts)+1
            if i>=len(b):
                raise ValueError("open position at end of data")
            new_ts = b.index[i]
            gap = new_ts-exit_ts!=pd.Timedelta(minutes=1)
            exit_ts = new_ts
            if gap:
                break
        entry, exit_price = b.at[next_ts,"open"], b.at[exit_ts,"open"]
        side = 1 if score>0 else -1
        gross = side*2*(exit_price-entry)
        result[name] = pd.DataFrame([(ts,next_ts,exit_ts,"long" if side==1 else "short",entry,exit_price,gross,gross-6,
                                      "gap" if gap else "time")],columns=TRADE_COLUMNS)
    return result
