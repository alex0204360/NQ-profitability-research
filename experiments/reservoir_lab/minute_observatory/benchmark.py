"""Time local CSV ingestion through snapshot publication on all 390 Nov 23 prefixes."""
import argparse
import contextlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import numpy as np
import pandas as pd

from observer import FIELDS, NY, refresh
from verify import check


def run(raw, output):
    item,=json.loads(raw.read_bytes())["chart"]["result"]
    b=pd.DataFrame(item["indicators"]["quote"][0],index=pd.to_datetime(item["timestamp"],unit="s",utc=True).tz_convert(NY))[FIELDS]
    reference=check(b)
    f=b.assign(contract="MNQZ26",timestamp_utc=b.index.tz_convert("UTC"))
    elapsed=[]
    with TemporaryDirectory() as tmp:
        root=Path(tmp)
        args=argparse.Namespace(day=b.index[0].date(),contract="MNQZ26",csv=root/"incoming.csv")
        for i,row in enumerate(reference):
            f.iloc[i:i+1].to_csv(args.csv,index=False,mode="a",header=i==0)
            start=perf_counter()
            with contextlib.redirect_stdout(io.StringIO()):
                refresh(args,root)
            elapsed.append((perf_counter()-start)*1000)
            state=json.loads((root/"state.json").read_text())
            seen=state["rows"][-1]
            for key in ("bar","decision","forecast","side","fill","net","equity"):
                assert seen[key]==row[key], (i,key)
    times=dict(prefixes=len(elapsed),median_ms=round(float(np.median(elapsed)),2),
               p95_ms=round(float(np.percentile(elapsed,95)),2),maximum_ms=round(max(elapsed),2))
    output.write_text(json.dumps(times,indent=2)+"\n")
    print(times)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("raw",type=Path)
    p.add_argument("output",type=Path)
    a=p.parse_args()
    run(a.raw,a.output)
