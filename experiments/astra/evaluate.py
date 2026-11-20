"""Run with python evaluate.py /path/to/canonical.csv."""
import json
import runpy
import shutil
import tempfile
from pathlib import Path
import numpy as np
import pandas as pd
from brain import forecast, compression_forecast

here=Path(__file__).resolve().parent
with tempfile.TemporaryDirectory() as tmp:
    replay=Path(tmp)/'reference'
    shutil.copytree(here.parent/'impulse_context',replay)
    env=runpy.run_path(str(replay/'replay.py'))
bars=env['bars']
frame=env['allbars']
segments=bars.index.to_series().diff().ne(pd.Timedelta(minutes=1)).cumsum()
score=pd.concat([forecast(g) for _,g in bars.groupby(segments)]).reindex(frame.index)
results={}
calendar=pd.Index(np.unique(frame.index.date))
daily={}
def evaluate(name, signal):
    t=env['run'](signal.abs()>.725+1e-10)
    side=np.sign(signal.loc[t.index])
    net=(side*t.gross-.725)*20
    daily[name]=net.groupby(net.index.date).sum().reindex(calendar,fill_value=0.)
    equity=np.r_[0,net.cumsum()]
    results[name]=dict(trades=len(t),net=net.sum(),stress_net=net.sum()-10*len(t),
        closed_drawdown=float(max(np.maximum.accumulate(equity)-equity)),
        yearly=net.groupby(net.index.year).sum().to_dict(),
        by_side=net.groupby(side).agg(['count','sum','mean']).to_dict('index'))
for name in ('v06','v08','v09'):
    evaluate(name,frame[name])
for name,signal in [('cash',frame.scale*0),('periodic',frame.scale*0+1),
                    ('two_up',frame.two_up.astype(float)),('auction',score)]:
    evaluate(name,signal)
contracted=pd.concat([compression_forecast(g) for _,g in bars.groupby(segments)]).reindex(frame.index)
evaluate("auction_compression",contracted)
rng=np.random.default_rng(6721)
n=len(calendar)
idx=((rng.integers(n,size=(5000,(n+4)//5,1))+np.arange(5))%n).reshape(5000,-1)[:,:n]
for name in [k for k in daily if k.startswith('auction')]:
    results[name]['daily_delta_vs']={}
    for ref in daily:
        delta=(daily[name]-daily[ref]).to_numpy()
        results[name]['daily_delta_vs'][ref]=[delta.mean(),*np.quantile(delta[idx].mean(1),[.025,.975])]
(here/'results.json').write_text(json.dumps(results,indent=2)+'\n')
