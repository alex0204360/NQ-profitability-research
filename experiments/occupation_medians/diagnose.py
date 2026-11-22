"""Compare true occupation weights with the same weights rotated six bars."""
import csv
import json
import random
import sys
from collections import Counter
import replay
from symmetry import symmetric_median


def rotated(rows, weights):
    return symmetric_median(rows, weights[6:]+weights[:6])


def audit(days):
    def replay_one(func):
        replay.median_site = func
        return [e for e in replay.run(days) if e['head']=='mass']
    lower = replay_one(replay.median_site)
    actual = replay_one(symmetric_median)
    null = replay_one(rotated)
    rows = []
    rng = random.Random(1122)
    for delay in (0,1):
        paired = [(e,n,b) for e,n,b in zip(actual,null,lower,strict=True) if e['delay']==delay]
        daily = Counter({day:0 for day in days})
        net = Counter({day:0 for day in days})
        for e,n,b in paired:
            pnl = e['gross']-3*abs(e['side'])
            daily[e['day']] += pnl-n['gross']+3*abs(n['side'])
            net[e['day']] += pnl
        values = [daily[k] for k in sorted(daily)]
        means = []
        for _ in range(4000):
            simulated = []
            while len(simulated)<len(values):
                start = rng.randrange(len(values))
                simulated.extend(values[(start+k)%len(values)] for k in range(5))
            means.append(sum(simulated[:len(values)])/len(values))
        means.sort()
        rows.append(dict(delay=delay, slots=len(paired), votes=dict(Counter(e['side'] for e,n,b in paired)),
                         changed_from_lower=sum(e['side']!=b['side'] for e,n,b in paired),
                         changed_from_rotated=sum(e['side']!=n['side'] for e,n,b in paired),
                         rotated_net=sum(n['gross']-3*abs(n['side']) for e,n,b in paired),
                         advantage_per_day=sum(values)/len(values),block_interval=[means[100],means[3899]],
                         net_without_best_day=sum(net.values())-max(net.values()),daily_net=dict(sorted(net.items()))))
    return rows


if __name__=='__main__':
    with open('diagnosis.json','w') as f:
        json.dump(audit(replay.load(sys.argv[1])),f,indent=2)
