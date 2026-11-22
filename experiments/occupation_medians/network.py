"""Direct threshold-network realization, independent of the sorted median evaluator."""
import csv
import sys
import replay
from symmetry import symmetric_median


def center(rows,weights):
    # Atoms are linear projections (1,0), (1/2,1/2), (0,1) of each low/high pair.
    sites = [a*r['low']+b*r['high'] for r in rows for a,b in ((1,0),(.5,.5),(0,1))]
    mass = [w for w in weights for _ in range(3)]
    half = .5*sum(mass)
    lower, upper = [], []
    for p in sites:
        # Pairwise comparison gates encode occupied mass on either side of p.
        left = sum(w*(q<=p) for q,w in zip(sites,mass))
        right = sum(w*(q>=p) for q,w in zip(sites,mass))
        if left >= half and right >= half:
            lower.append(p)
            upper.append(p)
    return .5*(min(lower)+max(upper))


if __name__ == '__main__':
    days = replay.load(sys.argv[1])
    with open('symmetric_activations.csv','w') as f:
        writer = csv.writer(f)
        writer.writerow(['day','minutes_from_open','time_center','volume_center','unit','side','gross_next','gross_delayed'])
        replay.median_site = symmetric_median
        events = [e for e in replay.run(days) if e['head']=='mass']
        for e,d in zip(events[::2],events[1::2],strict=True):
            rows = [days[e['day']][i] for i in range(e['start'],e['start']+12)]
            t = center(rows,[1]*12)
            v = center(rows,[r['volume'] for r in rows])
            assert (t,v)==(e['time_median'],e['volume_median'])
            writer.writerow([e['day'],e['start'],t,v,e['unit'],e['side'],e['gross'],d['gross']])
