"""Run from this directory with python replay.py /path/to/canonical.csv."""
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd

root = Path(__file__).resolve().parent
source = Path(sys.argv[1])
with source.open('rb') as f:
    assert hashlib.file_digest(f,'sha256').hexdigest() == '1577e60a7feab411e49da7a56c7052a64738cd1757cfd60aa11fd783ff43b60b'
rows = []
for chunk in pd.read_csv(source, chunksize=50000, dtype=str):
    stamps = pd.to_datetime(chunk['timestamp ET'], format='%m/%d/%Y %H:%M')
    use = (stamps.dt.year < 2025) & (stamps.dt.weekday < 5)
    rows.append(chunk.loc[use].set_index(stamps[use]).between_time('09:31','16:00'))
    if (stamps.dt.year >= 2025).any():
        break
bars = pd.concat(rows)[['open','high','low','close']].astype(float)
assert bars.index.is_monotonic_increasing and bars.index.is_unique
assert np.isfinite(bars).all().all()
assert ((bars.high >= bars[['open','close']].max(axis=1)) & (bars.low <= bars[['open','close']].min(axis=1))).all()
parts = []
for _, g in bars.groupby(bars.index.to_series().diff().ne(pd.Timedelta(minutes=1)).cumsum()):
    if len(g) < 18:
        continue
    close = g.close.to_numpy()
    positions = np.arange(16,len(g)-1)
    positions = positions[(g.index[positions].hour*60+g.index[positions].minute)<=956]
    if not len(positions):
        continue
    returns = np.lib.stride_tricks.sliding_window_view(np.diff(close),16)[positions-16]
    scale = (g.high-g.low).rolling(14).mean().shift(2).to_numpy()[positions]
    x = np.column_stack([returns,(g.high-g.close).iloc[positions],(g.close-g.low).iloc[positions]])
    x /= np.where(scale>0,scale,1)[:,None]
    due = g.index[positions] + pd.Timedelta(minutes=4)
    observed = bars.index.searchsorted(due)
    # Source stamps indicate bar ends. If the due bar is absent, the
    # next observed open is the first executable mark after interruption.
    exit_price = np.where(bars.index[observed] == due, bars.close.iloc[observed],
                          bars.open.iloc[observed])
    entry = g.open.to_numpy()[positions+1]
    frame = pd.DataFrame(dict(exit=bars.index[observed],scale=scale,impulse=x[:,14:16].sum(axis=1),
        two_up=x[:,14:16].min(axis=1)>0,gross=exit_price-entry,
        first_move=close[positions+1]-entry,upper=x[:,16]),index=g.index[positions])
    for version in ('v06','v08','v09'):
        m = json.loads((root/f'{version}.json').read_text())
        a = x
        for layer in m['layers']:
            a = np.maximum(0,a @ np.array(layer['W']).T+layer['b'])
        score = (a @ np.array(m['output']['W']).T+m['output']['b']).ravel()
        background = x[:,:14].sum(axis=1)/7
        overhead = np.maximum(0,-np.cumsum(x[:,13::-1],axis=1)).mean(axis=1)
        raw = frame.impulse-background-abs(background)-x[:,16]-2
        if version=='v08':
            raw -= overhead
        if version=='v09':
            raw -= .5*np.abs(np.cumsum(x[:,13::-1],axis=1)).mean(axis=1)
        expected = np.minimum(np.clip(raw,0,1),2*np.maximum(0,x[:,14:16].min(axis=1)))
        np.testing.assert_allclose(score,expected,atol=1e-12)
        frame[version] = score * scale
    parts.append(frame)
allbars = pd.concat(parts)
def run(mask):
    selected = []
    free = pd.Timestamp.min
    for time,end in allbars.loc[mask,'exit'].items():
        if time >= free:
            selected.append(time)
            free=end
    return allbars.loc[selected].copy()

results = {}
for name, mask in [('clock_long',np.ones(len(allbars),bool)),('two_up',allbars.two_up),
                   ('v06',allbars.v06>0.725+1e-10),('v08',allbars.v08>0.725+1e-10),('v09',allbars.v09>0.725+1e-10)]:
    t = run(mask)
    net = (t.gross-.725)*20
    days = net.groupby(net.index.date).sum()
    equity = np.r_[0,net.cumsum()]
    results[name] = dict(trades=len(t),net=float(net.sum()),mean=net.mean(),gross_points=t.gross.mean(),
        daily_sharpe_252=(lambda d: np.sqrt(252)*d.mean()/d.std())(days.reindex(np.unique(allbars.index.date),fill_value=0)),
        max_closed_drawdown=float((np.maximum.accumulate(equity)-equity).max()),
        mean_extra_tick_each_fill=net.mean()-10,without_best_day=net[net.index.date!=days.idxmax()].mean(),
        median=net.median(),win_rate=(net>0).mean(),year_means=net.groupby(net.index.year).mean().to_dict())
    if name.startswith('v'):
        controls = allbars[allbars.two_up & (allbars[name]<=.725+1e-10)]
        groups = dict(tuple(controls.groupby(controls.index.floor('h'))))
        diffs=[]
        for stamp,trade in t.iterrows():
            pool=groups.get(stamp.floor('h'))
            if pool is None:
                continue
            pool=pool[(pool.exit<=stamp)|(pool.index>=trade.exit)]
            if len(pool):
                diffs.append(trade.gross-pool.loc[(pool.impulse-trade.impulse).abs().idxmin(),'gross'])
        results[name].update(matched_n=len(diffs),matched_delta_points=np.mean(diffs))
        t.assign(net_usd=net).to_csv(root/f'{name}-trades.csv')
(root/'results.json').write_text(json.dumps(results,indent=2)+'\n')
# Paired moving-block bootstrap of incremental daily P&L on eligible dates.
calendar = pd.Index(np.unique(allbars.index.date))
ledgers = {v:pd.read_csv(root/f'{v}-trades.csv',index_col=0,parse_dates=[0])
           for v in ('v06','v08','v09')}
daily = {v:t.net_usd.groupby(t.index.date).sum().reindex(calendar,fill_value=0)
         for v,t in ledgers.items()}
rng = np.random.default_rng(613)
n = len(calendar)
starts = rng.integers(n,size=(5000,(n+4)//5))
indices = ((starts[:,:,None]+np.arange(5))%n).reshape(5000,-1)[:,:n]
audit = {}
for reference in ('v06','v09'):
    delta = (daily['v08']-daily[reference]).to_numpy()
    audit['v08_minus_'+reference] = dict(mean_daily=delta.mean(),
        percentile95=np.quantile(delta[indices].mean(axis=1),[.025,.975]).tolist())
parent = ledgers['v06']
for label, t in [('retained',parent[parent.v08>.725+1e-10]),
                 ('removed',parent[parent.v08<=.725+1e-10])]:
    audit[label] = dict(count=len(t),mean_net=t.net_usd.mean(),median_net=t.net_usd.median())
t=ledgers['v08']
for label,g in t.groupby(t.net_usd>0):
    audit['win' if label else 'loss'] = g[['scale','impulse','upper','first_move','gross']].median().to_dict()
audit['v08_top_five_share_of_net'] = t.net_usd.nlargest(5).sum()/t.net_usd.sum()
audit['eligible_dates']=n
(root/'audit.json').write_text(json.dumps(audit,indent=2)+'\n')
