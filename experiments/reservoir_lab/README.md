# Reservoir exit experiments

Keep the original reservoir as the research reference. Both edits reduced the November 19 loss on the 10:45 long. Each gave up more than 98% of the original net profit across the fourteen exposed November sessions. Neither qualifies as an upgrade.

## What the graph showed

Dates and times use New York time. A point on the chart is labeled by the minute's **start**. It becomes available at the end of that minute. The 10:41 and 10:42 bars rose from −2.06 to −1.69 points. On 10:42 the stock of evidence reached 0.2541. The next bar advanced 0.844 prior ranges and released +0.2145 units, lifting the forecast to +8.86. The original covered its short at 10:44 for +$90 net. The 10:44 bar produced +7.58 and the strategy entered long at 10:45 at 27,197.50. The forecast stayed positive as the evidence decayed. The 11:49 bar still read +0.0006 points. A fresh positive pulse arrived at 11:54; the first negative reading came at 12:01. The next open was 26,918.50, for −$564 including costs.

| Model | Selected long exit ET | Net on selected long | All trades in original long's window¹ | Full Nov 19 net | Other 13 Nov sessions net | All 14 Nov sessions net | 14-session marked drawdown | Sep–Oct 20-session net |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Original | 12:02 | −$564.00 | −$564.00 | −$126.50 | +$2,239.00 | +$2,112.50 | $1,727.50 | −$847.50 |
| Tick exit | 11:07 | +$160.50 | −$276.00 | −$75.00 | +$112.50 | +$37.50 | $1,303.50 | −$215.50 |
| Return to anchor | 11:52 | −$186.50 | −$186.50 | −$117.00 | +$120.50 | +$3.50 | $1,739.00 | −$930.00 |

¹ Entries at or after the original 10:45 entry and strictly before its 12:02 exit. All such positions closed by 12:02. Results assume one MNQ, next-open fills, $6 round-trip friction and the original 15:55 cutoff. The separate daily loss guard is disabled for this test.

**Tick exit.** Four ReLUs map a forecast within one tick to zero, and preserve magnitudes of two ticks or more. The 11:06 bar read +0.2266 and triggered the 11:07 exit at 27,280.75. The 11:54 pulse triggered another long at 11:55. That replacement lost $436.50. Earlier exits on 24 shared November entries that had originally won cost $3,377 in aggregate. Earlier exits on 15 original non-winners recovered $1,439. Other changed entries account for the rest of the difference. Across all fourteen dates, trades increased from 93 to 110. [Weights](tick_exit/weights.json) · [Trade ledger](tick_exit/results/candidate-trades.csv)

**Return to anchor.** This separate edit keeps the original forecast through quiet periods. A remembered price excursion arms one latch; a subsequent return to the starting price retires that directional episode until the raw sign changes. November 19's starting close was 27,206.50. The 10:59 bar armed the latch. The 11:50 close was still one tick above the anchor. The 11:51 close broke below it at 27,107.25. The circuit exited at 11:52 and skipped the second long. It then entered short a minute sooner than the original and lost $20.50 on that short. Across all fourteen sessions, earlier exits on 11 original winners cost $2,575.50. [Weights](return_to_anchor/weights.json) · [Activation trace](return_to_anchor/results/nov19-trace.csv)

## Inspect and reproduce

Each result directory contains an offline comparison.html with clickable candles and trades. Both charts open on November 19; choose Reference or the named variant. They also include every other archived session. The CSVs give full-precision scores, prices, marked daily net, and complete entry and exit ledgers. The original fills were checked against all 299 archived reference trades.

From this directory, run the commands below with the original six discovery CSVs and three hash-verified private November captures arranged as in the original workbench. Each script writes to the output directory supplied. The experiments use completed bars only. No one-minute delay or intrabar stop fill was simulated. These sessions, including the thirteen other November dates, have been seen before. November 23 has no score in this experiment.

```sh
python -m pytest -q test_surgery.py
python tick_exit/experiment.py /path/to/scratch /tmp/tick-exit
python tick_exit/experiment.py /path/to/scratch /tmp/return-to-anchor --model return_to_anchor
```

The branch starts at the frozen workbench commit 823435e. All additions live under experiments/reservoir_lab. The tick readout was frozen at 18870ea and the return-to-anchor circuit at 1a10558, after scoring the first edit. Keep both in discovery. The original prospective policy remains the one registered before these observations.
