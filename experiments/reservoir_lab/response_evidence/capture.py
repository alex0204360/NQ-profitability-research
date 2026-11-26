"""Load the separately reported November 25 after-close capture."""
import hashlib
import json
from datetime import date
import pandas as pd
from paper_day import FIELDS, prepare


def november25(root):
    data = (root/"nov25-auction-original"/"raw-chart.json").read_bytes()
    assert hashlib.sha256(data).hexdigest()=="35ef63ee44c057016a0edb1b411db80b904207656a3741cc48a07cdf7185b070"
    item, = json.loads(data)["chart"]["result"]
    assert item["meta"]["symbol"]=="MNQZ26.CME"
    q = pd.DataFrame(item["indicators"]["quote"][0])[FIELDS].copy()
    q["timestamp_utc"] = pd.to_datetime(item["timestamp"],unit="s",utc=True)
    q["contract"] = "MNQZ26"
    return prepare(q,date(2026,11,25),"MNQZ26","start")
