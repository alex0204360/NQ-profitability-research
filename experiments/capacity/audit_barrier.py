"""Check the causal next-close barrier on both exposed panels."""
import argparse
import json
from pathlib import Path

import pandas as pd

from experiments.hold_work.sources import load_sources
from .barrier import audit
from .neuron import encode


def run(source, output):
    history, external, _ = load_sources(market_dir=source)
    sessions = [('discovery40', history), ('external60', external['MNQ.csv'])]
    all_rows = []
    for source_name, tape in sessions:
        for _, bars in tape.groupby(tape.index.date):
            all_rows.append(audit(bars, encode(bars)).assign(source=source_name))
    rows = pd.concat(all_rows, ignore_index=True)
    rows['touched_without_close'] = rows.touched_intrabar & ~rows.closed_through
    report = {}
    for name, z in rows.groupby('source'):
        report[name] = dict(issued=len(z), reachable=int(z.reachable.sum()), touched=int(z.touched_intrabar.sum()),
                            reversed=int(z.closed_through.sum()), touched_without_close=int(z.touched_without_close.sum()),
                            unreachable_observed_reversals=int((~z.reachable & z.closed_through).sum()),
                            numerically_close=int(z.near_boundary.sum()))
    output.mkdir(parents=True,exist_ok=True)
    rows.to_csv(output/'barriers.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    (output/'barriers.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('market',type=Path)
    p.add_argument('output',type=Path)
    a = p.parse_args()
    run(a.market,a.output)
