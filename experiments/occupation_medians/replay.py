"""Dual occupation medians, using only completed bars and fixed nonoverlapping slots."""
import csv
import json
import statistics
import sys
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo


def median_site(rows, weights):
    # Each bar emits equal weight at low, midrange, high. First crossing of half mass.
    sites = sorted((price, w) for row, w in zip(rows, weights)
                   for price in (row['low'], (row['low'] + row['high']) / 2, row['high']))
    half = 1.5 * sum(weights)
    mass = 0
    for price, w in sites:
        mass += w
        if mass >= half:
            return price


def load(path):
    days = defaultdict(dict)
    with open(path) as f:
        for row in csv.DictReader(f):
            ts = datetime.fromisoformat(row['time'].replace('Z', '+00:00'))
            assert ts.tzinfo is not None
            ny = ts.astimezone(ZoneInfo('America/New_York'))
            day = ny.date().isoformat()
            assert day <= '2026-11-20'
            minute = ny.hour * 60 + ny.minute - 570
            if 0 <= minute < 390:
                assert minute not in days[day]
                days[day][minute] = {k: float(row[k]) for k in ('open','high','low','close','volume')}
    return days


def run(days):
    events = []
    for day, bars in sorted(days.items()):
        for start in range(0, 371, 20):
            if any(i not in bars for i in range(start, start+19)):
                continue
            window = [bars[i] for i in range(start,start+12)]
            volumes = [r['volume'] for r in window]
            if not sum(volumes):
                continue
            t = median_site(window, [1]*12)
            v = median_site(window, volumes)
            close = window[-1]['close']
            unit = max(.25, statistics.median(r['high']-r['low'] for r in window))
            # Separating medians by half a typical bar suppresses single-tick ties.
            vote = int(v-t >= unit/2) - int(t-v >= unit/2)
            for head, side in [('mass', vote), ('reverse', -vote),
                               ('toward_time', (int(t>close)-int(t<close)) * abs(vote))]:
                for delay in (0,1):
                    entry = start+12+delay
                    price = bars[entry]['open']
                    marks = [side*2*(bars[i]['close']-price) for i in range(entry,entry+5)]
                    gross = side*2*(bars[entry+5]['open']-price)
                    events.append(dict(day=day,start=start,head=head,side=side,delay=delay,
                                       time_median=t,volume_median=v,unit=unit,marks=marks,gross=gross))
    return events


def summarize(events):
    output = []
    for head in ('mass','reverse','toward_time'):
        for delay in (0,1):
            for cost in (3,6):
                for panel in ('all','early','nov'):
                    equity = peak = dd = trades = slots = 0
                    for e in events:
                        if (e['head'],e['delay']) != (head,delay):
                            continue
                        if panel != 'all' and (panel=='nov') != (e['day'] >= '2026-11-01'):
                            continue
                        slots += 1
                        if not e['side']:
                            continue
                        trades += 1
                        for mark in [0]+e['marks']:
                            level = equity + mark-cost/2
                            peak = max(peak,level)
                            dd = max(dd,peak-level)
                        equity += e['gross']-cost
                        peak = max(peak,equity)
                        dd = max(dd,peak-equity)
                    output.append(dict(head=head,delay=delay,cost=cost,panel=panel,slots=slots,
                                       trades=trades,net=equity,drawdown=dd))
    return output


if __name__ == '__main__':
    events = run(load(sys.argv[1]))
    with open('summary.json','w') as f:
        json.dump(summarize(events),f,indent=2)
    with open('activations.csv','w') as f:
        keys = ['day','start','time_median','volume_median','unit','side','gross']
        writer = csv.DictWriter(f,keys,extrasaction='ignore')
        writer.writeheader()
        writer.writerows(e for e in events if e['head']=='mass' and not e['delay'])
