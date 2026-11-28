"""Project a probability onto a calibrated slope learned from matured past sessions."""
import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.two_close_warning.run import MASS, PRIOR, score

STREAMS = ("joint", "rotated", "price")
MODELS = ("intercept", "joint", "cal_rotated", "cal_price", "cal_joint")


@dataclass
class Calibration:
    n: int = MASS
    sx: float = MASS * PRIOR
    sy: float = MASS * PRIOR
    sxx: float = MASS * PRIOR**2
    sxy: float = MASS * PRIOR**2

    def predict(self, x):
        intercept = self.sy / self.n
        slope = np.clip((self.sxy-self.sx*intercept)/(1+self.sxx-self.sx**2/self.n),0,1)
        return np.clip(intercept+slope*(x-self.sx/self.n),0,1), slope

    def settle(self, x, y):
        self.n += len(x)
        self.sx += x.sum()
        self.sy += y.sum()
        self.sxx += x @ x
        self.sxy += x @ y


def run(archive, dest):
    frame = pd.read_csv(archive)
    book, report = [], {}
    for source, group in frame.groupby("source"):
        memory = {name:Calibration() for name in STREAMS}
        forecasts = []
        settled = 0
        for _, day in group.groupby("date",sort=True):
            day = day.copy()
            day["prior_resolved"] = settled
            day["intercept"] = memory["joint"].sy / memory["joint"].n
            resolved = day.target.notna()
            for name in STREAMS:
                circuit = memory[name]
                assert circuit.n == MASS+settled
                day["cal_"+name],day["slope_"+name] = circuit.predict(day[name].to_numpy())
                circuit.settle(day.loc[resolved,name].to_numpy(),day.loc[resolved,"target"].to_numpy())
            settled += int(resolved.sum())
            forecasts.append(day)
        panel = pd.concat(forecasts)
        report[source] = score(panel, sorted(group.date.unique()), MODELS, "cal_joint")
        slopes = panel.groupby("date")[["slope_"+name for name in STREAMS]].first()
        report[source]["slopes"] = {name:dict(first=float(val.iloc[0]),last=float(val.iloc[-1]),
            min=float(val.min()),max=float(val.max())) for name,val in slopes.items()}
        book.append(panel)
    dest.mkdir(parents=True,exist_ok=True)
    report["input_sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
    pd.concat(book).to_csv(dest/"calibrated.csv.gz",index=False,compression={"method":"gzip","mtime":0})
    (dest/"summary.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive",type=Path)
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    run(args.archive,args.output)
