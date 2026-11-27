"""Chronological duration and downside forecasts on the exposed parent decisions."""
import argparse
import heapq
import json
from math import sqrt
from pathlib import Path

import numpy as np
import pandas as pd

from .downside import TailMemory
from .duration import Duration
from .run_matured import bootstrap_indexes

RISK_MODELS = ('range', 'unconditional', 'conditioned')


class RiskMemory(TailMemory):
    def __init__(self):
        self.history = {name: [] for name in RISK_MODELS}

    @property
    def count(self):
        return len(self.history['range'])


def score(group):
    duration, risk = Duration(), RiskMemory()
    pending, rows = [], []
    for i, event in enumerate(group.sort_values('decision_utc').itertuples()):
        while pending and pending[0][0] < event.decision_utc:
            _, _, h, actual, scale, loss = heapq.heappop(pending)
            duration.observe(h, actual)
            risk.observe(scale, loss)
        minutes = duration.predict(event.predicted_duration, event.clock_minutes)
        scale = {key: event.entry_scale * sqrt(value) for key, value in minutes.items()}
        scale['range'] = event.entry_scale
        risk_read = risk.predict(scale)
        row = dict(source=event.source, date=event.date, delay=event.delay, trade_id=event.trade_id,
                   decision_utc=event.decision_utc, mature_count=risk.count,
                   duration_diffusion=event.predicted_duration, duration_unconditional=minutes['unconditional'],
                   duration_conditioned=minutes['conditioned'])
        for key in RISK_MODELS:
            row['q_' + key] = risk_read[key] if risk_read is not None else np.nan
        row.update(actual=event.realized_duration, loss=event.loss_pts)
        rows.append(row)
        if pd.notna(event.loss_pts):
            assert event.decision_utc <= event.original_exit_time
            heapq.heappush(pending, (event.original_exit_time, i, event.predicted_duration,
                                     event.realized_duration, scale, event.loss_pts))
    return pd.DataFrame(rows)


def statistics(rows, dates):
    z = rows.dropna(subset=['q_conditioned', 'loss']).copy()
    dates = [date for date in dates if date >= z.date.min()]
    blocks = bootstrap_indexes(len(dates))
    counts = z.groupby('date').size().reindex(dates, fill_value=0).to_numpy()[blocks].sum(axis=1)
    valid = counts > 0

    def paired(difference):
        daily = difference.groupby(z.date).sum().reindex(dates, fill_value=0).to_numpy()
        averages = daily[blocks].sum(axis=1)[valid]/counts[valid]
        return {'difference': float(difference.mean()), 'ci95': np.quantile(averages,[.025,.975]).tolist()}

    report = {'eligible':len(rows), 'scored':len(z), 'mean_loss_pts':z.loss.mean(),
              'risk':{}, 'duration':{}, 'paired':{}}
    for key in RISK_MODELS:
        q = z['q_'+key]
        e = z.loss - q
        metric = np.maximum(.8*e, -.2*e)
        z['pinball_'+key] = metric
        report['risk'][key] = {'pinball': metric.mean(), 'mean_q':q.mean(), 'exceedance':(e>0).mean()}
    for key in ['conditioned','unconditional','diffusion']:
        forecast = z['duration_'+key]
        error = (np.log1p(forecast)-np.log1p(z.actual))**2
        z['dse_'+key] = error
        report['duration'][key] = {'log_mse':error.mean(), 'median_prediction_minutes':forecast.median()}
    for prefix, controls in [('pinball', ['range','unconditional']),('dse',['diffusion','unconditional'])]:
        for control in controls:
            report['paired'][prefix+'_vs_'+control] = paired(z[prefix+'_conditioned']-z[prefix+'_'+control])
    return report


def run(directory, out):
    events = pd.read_csv(directory/'downside_results/forecasts.csv.gz')
    keys = ['trade_id','delay']
    orig = pd.read_csv(directory/'results/first-decisions.csv.gz', usecols=keys+['original_exit_time'])
    events = events.merge(orig, on=keys, validate='one_to_one', how='left')
    for col in ['decision_utc','original_exit_time','alternate_utc']:
        events[col] = pd.to_datetime(events[col], utc=True)
    assert (events.original_exit_time-events.alternate_utc).dt.total_seconds().div(60).equals(events.realized_duration)
    dates = pd.read_csv(directory/'matured_results/daily.csv',usecols=['date','source','delay'])
    all_rows, summary = [], {}
    for (source, delay), group in events.groupby(['source','delay']):
        rows = score(group)
        days = sorted(dates.loc[dates.source.eq(source)&dates.delay.eq(delay),'date'].unique())
        summary.setdefault(source,{})[int(delay)] = statistics(rows,days)
        # A fresh implementation must reproduce every issued range-only downside forecast.
        base = group.set_index('trade_id').q_range.loc[rows.trade_id]
        np.testing.assert_allclose(base,rows.q_range,equal_nan=True)
        all_rows.append(rows)
    out.mkdir(parents=True,exist_ok=True)
    pd.concat(all_rows).to_csv(out/'forecasts.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    (out/'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory',type=Path)
    p.add_argument('output',type=Path)
    a = p.parse_args()
    run(a.directory, a.output)
