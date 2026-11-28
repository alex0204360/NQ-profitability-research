#!/usr/bin/env python3
"""Single-file admission audit for the frozen MNQ historical transport protocol.

Fetches only the pinned January 4 file into memory; never writes vendor bars.
Run: python experiments/historical_warning/audit_20210104.py
"""
from __future__ import annotations
import csv, hashlib, io, json, math, urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path

COMMIT = "fc5508e2c152938d6d9eb70a36b888ae26107176"
PATH = "plaintext_csv/MNQ 03-21/20210104.Last.csv"
URL = f"https://raw.githubusercontent.com/mbytes21/MNQ_DATA/{COMMIT}/" + urllib.parse.quote(PATH)
EXPECTED_GIT_BLOB = "0f8c70f116fc4a2edaaa31ebf94f270ace2b6b71"
EXPECTED_SHA256 = "67f695599d168b0b5926ebe283f4f0b45364b342812bb5917224dfb24e8324b0"
OUT = Path(__file__).resolve().parent / "audit_20210104.json"


def audit():
    with urllib.request.urlopen(URL, timeout=30) as response:
        raw = response.read()
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    sha256 = hashlib.sha256(raw).hexdigest()
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    header = reader.fieldnames or []
    rows = list(reader)
    times = [datetime.strptime(r["datetime"], "%Y-%m-%d %H:%M:%S") for r in rows]
    deltas = Counter(int((b-a).total_seconds()) for a,b in zip(times,times[1:]))
    duplicate_time_count = len(times) - len(set(times))
    full_rows = [tuple(r.get(k, "") for k in header) for r in rows]
    prices=[]; volumes=[]; ohlc_violations=0; off_tick=0
    for r in rows:
        o,h,l,c = (float(r[k]) for k in ("open","high","low","close"))
        v=float(r["volume"])
        prices.extend((o,h,l,c)); volumes.append(v)
        ohlc_violations += int(not (l <= min(o,c) <= max(o,c) <= h))
        off_tick += sum(int(abs(p*4-round(p*4)) > 1e-7) for p in (o,h,l,c))
    counts=Counter(t.date().isoformat() for t in times)
    gaps=[{"from":a.isoformat(sep=" "),"to":b.isoformat(sep=" "),"seconds":int((b-a).total_seconds())}
          for a,b in zip(times,times[1:]) if (b-a).total_seconds()!=60]
    metrics={
      "bytes":len(raw),"git_blob_sha1":blob,"sha256":sha256,
      "expected_hashes_match": blob==EXPECTED_GIT_BLOB and sha256==EXPECTED_SHA256,
      "header":header,"row_count":len(rows),"unique_timestamp_count":len(set(times)),
      "duplicate_timestamp_count":duplicate_time_count,"duplicate_full_row_count":len(full_rows)-len(set(full_rows)),
      "timestamp_start_naive":times[0].isoformat(sep=" "),"timestamp_end_naive":times[-1].isoformat(sep=" "),
      "timestamp_date_counts":dict(counts),"strictly_increasing":all(a<b for a,b in zip(times,times[1:])),
      "minute_delta_seconds":dict(sorted(deltas.items())),"non_60_second_gaps":gaps,
      "naive_clock_rows_0930_1559":sum(1 for t in times if t.strftime("%H:%M") >= "09:30" and t.strftime("%H:%M") <= "15:59"),
      "naive_clock_rows_0931_1600":sum(1 for t in times if t.strftime("%H:%M") >= "09:31" and t.strftime("%H:%M") <= "16:00"),
      "ohlc_bound_violations":ohlc_violations,"off_0_25_tick_price_fields":off_tick,
      "volume_negative_rows":sum(v<0 for v in volumes),"volume_noninteger_rows":sum(not v.is_integer() for v in volumes),
      "volume_zero_rows":sum(v==0 for v in volumes),"volume_sum":sum(volumes),"volume_min":min(volumes),"volume_max":max(volumes),
    }
    return metrics

if __name__ == "__main__":
    result={"candidate":"mbytes21/MNQ_DATA","commit":COMMIT,"path":PATH,"url":URL,
      "admission":"NOT_ADMITTED","metrics":audit(),
      "stop_reason":["No published provenance or transformation lineage binds these observed CSV bytes to a vendor/feed.",
        "No source documentation resolves timestamp timezone or start/end label convention; session-break anchors are suggestive but cannot establish the representation mapping.",
        "No published source establishes Last as exchange-trade prints or defines volume units/aggregation semantics.",
        "No documented instrument mapping or independent evidence establishes that the bytes represent the March 2021 MNQ H21 contract."],
      "decision":"Stop after this single-file audit; no scoring or model outcomes inspected.",
      "references":[
        "https://github.com/mbytes21/MNQ_DATA/tree/fc5508e2c152938d6d9eb70a36b888ae26107176/plaintext_csv",
        "https://static.ninjatrader.com/support/helpGuides/nt8/exporting.htm",
        "https://static.ninjatrader.com/support/helpGuides/nt8/importing.htm",
        "https://www.cmegroup.com/notices/electronic-trading/2021/06/20210621.html"]}
    OUT.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))
