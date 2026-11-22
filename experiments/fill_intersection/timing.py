"""Decompose matched-window delay into a signed entry loss and exit gain."""
from pathlib import Path

import numpy as np
import pandas as pd
from run import checked_window, prepare_panels, paired, BLOCK

here = Path(__file__).resolve().parent
panels, _ = prepare_panels(Path('/tmp/mnq-exposed/discovery'), Path('/tmp/mnq-reissued'), True)
bars = panels['combined34']
rows = []
for folder, heads in [('results',['intersection','midpoint','pooled']),
                      ('erasure_results',['erase','fade','distributed'])]:
    q = pd.read_csv(here/folder/'probes.csv', index_col=0)
    q.index = pd.to_datetime(q.index,utc=True).tz_convert(bars.index.tz)
    for head in heads:
        direction = np.sign(q.loc[q[head]!=0,head])
        for period, g in [('all',direction),('sep_oct',direction[direction.index.month<11]),
                          ('nov',direction[direction.index.month==11])]:
            entry = (bars.open.shift(-1)-bars.open.shift(-2)).loc[g.index]*g
            exit_gain = (bars.open.shift(-BLOCK-2)-bars.open.shift(-BLOCK-1)).loc[g.index]*g
            change = (q.forward2-q.forward1).loc[g.index]*g
            np.testing.assert_allclose(entry+exit_gain,change)
            rows.append(dict(head=head,period=period,n=len(g),entry_points=entry.mean(),
                             exit_points=exit_gain.mean(),change_points=change.mean()))
pd.DataFrame(rows).to_csv(here/'timing.csv',index=False)
