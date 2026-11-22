"""Matched clock-window probes; all labels are offline measurements in points."""
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
rows = []
for folder, heads in [('results', ['intersection','midpoint','pooled']),
                      ('erasure_results', ['erase','fade','distributed'])]:
    probes = pd.read_csv(HERE / folder / 'probes.csv', index_col=0)
    for period, q in [('all',probes), ('sep_oct',probes.loc[:'2026-10-31']),
                      ('nov',probes.loc['2026-11-01':])]:
        for head in heads:
            g = q[q[head] != 0]
            a, b = g[head].apply(np.sign)*g.forward1, g[head].apply(np.sign)*g.forward2
            rows.append(dict(period=period, head=head, n=len(g), mean_next=a.mean(),
                             mean_delayed=b.mean(), median_next=a.median(),
                             both_cover_stress=((a>3)&(b>3)).mean(),
                             different_sign=(a*b<0).mean()))
pd.DataFrame(rows).to_csv(HERE/'diagnosis.csv',index=False)
