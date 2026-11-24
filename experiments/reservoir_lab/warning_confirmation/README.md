# Waiting for a warning to hold

The confirmation neuron improved full-policy historical returns versus both controls. It failed the frozen drawdown requirement in both windows. Keep it as a research result. No independent data have validated the new neuron.

## What gets one more bar

The previously frozen position-local exit emits a warning when the signed hold score first turns nonpositive from a failed retest while the original forecast still favors holding. Store the closing price of that warning in position coordinates. At the next completed close, a long must have closed higher, or a short lower, to cancel the warning. Equality and a worse close both request the next open. A strategy that always waits exactly one bar and then exits measures how much improvement comes from the delay alone. The two added weight rows are [0, 1] for writing the current level and [1, −1] for subtracting it from the next level. Raw forecast reversal, the gap exit and the 15:55 New York flatten take priority. A fresh copy of the price memory starts each episode.

The historical chart retains the original Forecast (pts). Hold value (pts) is an experimental, position-relative stopping score. On the warning bar it displays the four-bar carry score while waiting. A confirmed adverse displacement produces a nonpositive score at the confirmation close. The threshold is zero. Neither the warning bar nor the confirmation bar receives an earlier fill. [Frozen protocol](protocol.md) · [Weights](weights.json) · [Circuit](circuit.py)

## Full historical replay

One MNQ at $2 per point. Each round trip includes $6 in friction, and every decision based on a completed bar uses the next open. Each cell shows net dollars / maximum minute-close marked drawdown in dollars. Panels start with zero equity. The November panels overlap.

| Discovery window | Original | Immediate exit | Delay only | Confirmation |
|---|---:|---:|---:|---:|
| Earlier 20 | −847.50 / 2,269 | −540 / 1,883 | −659.50 / 1,977.50 | −530.50 / 1,942 |
| November 19 | −126.50 / 1,526.50 | −22.50 / 713.50 | −67.50 / 743.50 | −362 / 1,245 |
| Other 13 November | +2,239 / 995 | +1,424 / 1,012 | +1,678.50 / 1,163.50 | +2,375.50 / 1,029.50 |
| All 14 November | +2,112.50 / 1,727.50 | +1,401.50 / 1,012 | +1,611 / 1,163.50 | +2,013.50 / 1,245 |

Of the November full policy's 46 warnings, the next close reclaimed 29 and confirmed 17. November net expectancy was $20.97 per trade across 96 trades. In the earlier 20 sessions it was −$2.54 across 209 trades. The largest single-trade changes against the immediate exit occurred in the two examples that motivated the design.

* The November 10 short reclaimed its first warning by 22 points. Later, a separate warning confirmed. The edit earned $590.50 versus −$6 with the immediate exit and +$662 originally.
* The November 19 long reclaimed its warning by 48.25 points. Keeping it open ultimately lost $564 versus +$66.50 with the immediate exit. Delay-only took the next exit for +$167.

## Identical original entries

Dollar changes below are relative to each original trade's result. Winners and losers are classified by original net. The final two columns give the economics when later entries are allowed to change.

| Window | Change on losers | Change on winners | Paired net / marked drawdown | Added same-episode re-entries vs immediate (count / net) | Missed immediate trades (count / net) |
|---|---:|---:|---:|---:|---:|
| Earlier 20 | 169 | 131.5 | -547 / 1,926.5 | 1 / 12 | 14 / 105 |
| November 19 | 0 | -519 | -645.5 / 1,155 | 0 / 0 | 1 / -436.5 |
| Other 13 November | 814 | -822 | 2,231 / 1,104 | 0 / 0 | 11 / -45 |
| All 14 November | 814 | -1,341 | 1,585.5 / 1,439.5 | 0 / 0 | 12 / -481.5 |

On identical November entries, confirmation preserved $1,222.50 more on original winners than immediate exits, while giving back $1,084.50 of the protection on original losers. Delay-only earned $13 more than confirmation on those fixed entries. Allowing later entries to change lifted confirmation $612 above immediate: +$62 on 94 shared entries, 12 missed trades previously worth −$481.50, and two added trades worth +$68.50 after costs. That sum already includes $60 less friction. On the earlier 20 dates the full-policy advantage was only $9.50, including $48 less friction.

The chart's case buttons compare confirmation to the **original**, with identical entries. The biggest save was the November 18 short, from −$167.50 to +$279. The most damaged winner was the November 5 long, from +$477 to −$228.50. The downloadable ledgers include the exact bar-start timestamps. [Detailed results](results/results.json) · [Warning dispositions](results/events.csv)

## Yesterday's separate as-is paper replay

On November 23, the original had seven winners in 21 trades, −$519 gross, $126 modeled friction and **−$645 net**, with $1,273.50 marked drawdown. The frozen daily guard returned −$531.50 across 10 trades, with $832 drawdown. The preceding combined memory policy from f40665d returned −$421 across 23 trades, including $138 friction, with $1,060 drawdown. Its as-is comparison is retrospective on a previously disclosed session. The original and guarded ledgers exactly match the pre-market kit's previously saved run. The retained capture of all 390 MNQZ26 bars matches its source hash. Synchronized quotes were unavailable for a nine-second audit. November 23 was excluded from the confirmation experiment. [Original session chart and ledgers](../paper_sessions/2026-11-23/) · [As-is results](november23/as-is.json)

## Reproduction

Freeze commit b4ed868 precedes all candidate scoring. From this directory, use the same historical capture layout as the parent trade-memory lab.

```sh
python run.py /path/to/private/scratch /tmp/confirmation-results
python yesterday.py /path/to/nov23/raw-chart.json /tmp/nov23-as-is
python -m pytest -q test_confirmation.py ../trade_memory/test_memory.py ../adverse_impact/test_simulator.py
```

Original and immediate ledgers are checked byte-for-byte against the parent. The two offline charts, circuit, weights and scorecards are included in [confirmation-review.zip](confirmation-review.zip).
