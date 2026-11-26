"""Replay the first later session on its immutable after-close capture."""
import argparse
import hashlib
import json
from datetime import date
from pathlib import Path
import pandas as pd

from cascade import make
from study import run
from paper_day import prepare,FIELDS
from matched_economics import compute

HASH="35ef63ee44c057016a0edb1b411db80b904207656a3741cc48a07cdf7185b070"


def load_capture(root):
    payload=(root/"raw-chart.json").read_bytes()
    if hashlib.sha256(payload).hexdigest()!=HASH: raise ValueError("post-freeze source mismatch")
    item,=json.loads(payload)["chart"]["result"]
    assert item["meta"]["symbol"]=="MNQZ26.CME"
    f=pd.DataFrame(item["indicators"]["quote"][0])[FIELDS].copy()
    f["timestamp_utc"]=pd.to_datetime(item["timestamp"],unit="s",utc=True)
    f["contract"]="MNQZ26"
    b=prepare(f,date(2026,11,25),"MNQZ26","start")
    assert len(b)==390
    return b


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("capture",type=Path);p.add_argument("out",type=Path)
    a=p.parse_args()
    run({"nov25":load_capture(a.capture)},a.out,make)
    compute(a.out)
    t=pd.read_csv(a.out/"trades.csv.gz").query("model=='original'")
    parent=pd.read_csv(a.capture/"base-trades.csv")
    pd.testing.assert_frame_equal(t[parent.columns].reset_index(drop=True),parent,check_dtype=False)
