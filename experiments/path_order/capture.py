"""Capture the one registered temporal panel privately; share its receipt and aggregates."""
import argparse
import csv
import hashlib
import io
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from data import FIELDS

SYMBOL = "MNQZ26.CME"
START = datetime(2026, 11, 16, tzinfo=UTC)
END = datetime(2026, 11, 21, tzinfo=UTC)
WINDOWS = {"november": (START, END),
           "extension1": (datetime(2026,11,3,tzinfo=UTC), datetime(2026,11,7,tzinfo=UTC)),
           "extension2": (datetime(2026,11,9,tzinfo=UTC), datetime(2026,11,14,tzinfo=UTC))}


def capture(directory, window="november"):
    start, end = WINDOWS[window]
    query = urlencode(dict(period1=int(start.timestamp()), period2=int(end.timestamp()),
                           interval="1m", includePrePost="true"))
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{SYMBOL}?{query}"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "chart.json"
    if not path.exists():
        with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30) as response:
            payload = response.read()
        with path.open("xb") as f:
            f.write(payload)
    raw = path.read_bytes()
    chart = json.loads(raw)["chart"]
    if chart["error"]:
        raise ValueError(chart["error"])
    item, = chart["result"]
    meta = item["meta"]
    if (meta["symbol"] != SYMBOL or meta["instrumentType"] != "FUTURE" or
            meta["dataGranularity"] != "1m" or meta["exchangeTimezoneName"] != "America/New_York"):
        raise ValueError("unexpected symbol or series metadata")
    stamps = item["timestamp"]
    quotes, = item["indicators"]["quote"]
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["timestamp_utc", *FIELDS])
    dropped = []
    outside = []
    for row in zip(stamps, *(quotes[k] for k in FIELDS), strict=True):
        stamp = datetime.fromtimestamp(row[0], UTC)
        if window != "november" and not start <= stamp < end:
            outside.append(stamp.isoformat())
            continue
        if any(x is None for x in row[1:]):
            dropped.append(stamp.isoformat())
            continue
        writer.writerow([stamp.isoformat(), *row[1:]])
    csv_bytes = buf.getvalue().encode()
    csv_path = directory / "bars.csv"
    if csv_path.exists():
        if csv_path.read_bytes() != csv_bytes:
            raise ValueError("private CSV differs from frozen capture")
    else:
        with csv_path.open("xb") as f:
            f.write(csv_bytes)
    return dict(url=url, symbol=SYMBOL, source_sha256=hashlib.sha256(raw).hexdigest(),
                csv_sha256=hashlib.sha256(csv_bytes).hexdigest(), source_rows=len(stamps),
                ignored_outside_request=outside, dropped_incomplete=len(dropped), omitted_utc=dropped,
                metadata={k: meta.get(k) for k in ("symbol","exchangeName","instrumentType","currency",
                          "exchangeTimezoneName","dataGranularity","contractSymbol","expirationDate")})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--window", choices=list(WINDOWS), default="november")
    args = parser.parse_args()
    print(json.dumps(capture(args.directory, args.window), indent=2))
