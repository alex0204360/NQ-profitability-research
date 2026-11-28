"""Render the observed timing and break-even results from the published ledgers."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent
timing=json.loads((HERE.parent/'intraminute/results/summary.json').read_text())['timing']['volume']
tables=pd.read_csv(HERE/'results/tables.csv.gz')
fig,axes=plt.subplots(2,1,figsize=(8.0,6.7),constrained_layout=True)
ax=axes[0]
delay=[0,1,9,30,60];x=np.arange(len(delay))
for label,key,color,m in [('Signal close to entry','rank_prefill','#256882','o'),('Entry to 60 seconds later','rank_open_to_open','#ac531e','s')]:
    ax.plot(x,[timing[str(d)][key] for d in delay],marker=m,color=color,lw=2,label=label)
ax.axhline(0,lw=.8,color='#67737c')
ax.set(xticks=x,xticklabels=delay,ylabel='Spearman correlation',xlabel='Entry delay (seconds)',ylim=(-.06,.34),
       title='The minute discrepancy predicted movement into the opening print')
ax.legend(frameon=False)
ax=axes[1];delay=[0,1,9,60];x=np.arange(len(delay))
avg=[]
for d in delay:
    n=tables[f'trades_{d}']
    avg.append(((tables[f'net_{d}_3']+3*n)/n.where(n>0)).max())
bars=ax.bar(x,avg,width=.56,color='#256882')
ax.axhline(3,color='#ac531e',linestyle='--',lw=1.5)
ax.text(1.5,3.07,'Lowest tested round-trip friction ($3)',ha='center',color='#8e411b')
ax.bar_label(bars,labels=[f'${a:.2f}' for a in avg],padding=3)
ax.set(xticks=x,xticklabels=delay,ylabel='USD per MNQ round trip',xlabel='Entry delay (seconds)',ylim=(0,3.48),
       title='Best gross dollars per trade among 6,560 active fixed rules')
for ax in axes:
    ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',alpha=.14);ax.set_axisbelow(True)
fig.savefig(HERE/'results/timing-and-cost.png',dpi=180)
