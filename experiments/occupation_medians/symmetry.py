"""Mirror-equivariant readout of the interval of occupation medians."""
import replay
import sys


def symmetric_median(rows, weights):
    occupied = sorted((p,w) for r,w in zip(rows,weights) if w>0
                      for p in (r['low'],(r['low']+r['high'])/2,r['high']))
    half = 1.5*sum(weights)
    mass = 0
    for i,(price,weight) in enumerate(occupied):
        mass += weight
        if mass == half:
            return (price+occupied[i+1][0])/2
        if mass > half:
            return price


if __name__ == '__main__':
    import json
    replay.median_site = symmetric_median
    events = replay.run(replay.load(sys.argv[1]))
    with open('symmetric_summary.json','w') as f:
        json.dump(replay.summarize(events),f,indent=2)
