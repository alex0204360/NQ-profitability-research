# MNQ response and cross-market experiments

Three new mechanisms faced a newly sourced panel of 60 complete MNQ sessions from January 20 to April 15, 2026. None passed the registered profitability and risk screen. November 23 was excluded. November 25 appears as a previously observed comparison. All programs use one MNQ, completed minute signals, next-open modeled fills, $6 round-trip costs and a 15:55 New York cutoff. The friction stress uses $9 on identical fills. The scores in points are experimental. There is no first-seen or nine-second bid/ask execution record for the external data.

[Offline discovery trade chart](results/discovery/replay.html) · [Download the weights and inspector](response-kit.zip) · [Full account of the external trades](results/external/results.json) · [Synchronized NQ comparison](results/external/cross-market.json)

## What changed

* The first three-cell circuit accumulates evidence from adverse price moves and loses evidence on recovery. The preceding minute's relative volume changes the sensitivity of each cell. It emitted zero early exits across 299 historical entries. The original MNQ forecast stays intact. [Equations and first freeze](protocol.md)
* The next three rectifiers allow an adverse run to start again inside a profitable trade. On the 60 external sessions, forcing the original 541 entries made original losers $26.50 worse in aggregate and surrendered $149.50 on original winners. Of the individual changes on losers, some saved $112.50 and others cost $139. The unrestricted edit made three extra trades at $18 combined incremental friction. Those trades lost $44 net including that friction. No original entries were missed. [Redesign](redesign.md)
* The closing auction circuit asks whether afternoon trading retained the first half-hour's displacement. Volume weights how much time spent near either endpoint counts. A second brain measures the same reservoir on NQ and permits an MNQ entry when both contract scores agree. Its exit tolerates a three-point opposing NQ score. The latter kept 75 fewer round trips on the matched 59-day panel and lost $477 more than MNQ alone. Feeding MNQ to both inputs reproduced the original ledger. [Closing auction design](redesign.md) · [Cross-market weights and controls](synchrony.md)

## External test

| Policy | Sessions | Trades | Net | Net at $9 | Peak-to-trough intrabar drawdown (upper bound) |
|---|---:|---:|---:|---:|---:|
| Original MNQ reservoir | 60 | 541 | −$3,821 | −$5,444 | $5,719.50 |
| Sequential adverse evidence | 60 | 542 | −$3,936.50 | −$5,562.50 | $5,719.50 |
| Restartable adverse evidence | 60 | 544 | −$4,041 | −$5,673 | $5,703 |
| Prior volume-weighted impulse | 60 | 61 | −$764 | −$947 | $1,224.50 |
| Volume-weighted closing auction | 60 | 33 | −$357 | −$456 | $804 |
| Equal-weight closing auction | 60 | 32 | −$344 | −$440 | $851.50 |
| Always long, 15:30–15:55 | 60 | 60 | +$1,456 | +$1,276 | $834 |
| Original MNQ, synchronized subset | 59 | 534 | −$3,820 | −$5,422 | $5,719.50 |
| Joint NQ and MNQ entry and exit | 59 | 459 | −$4,297 | −$5,674 | $5,654.50 |

The always-long benchmark earned $24.27 per day with a descriptive 95% five-session circular-block interval from −$0.44 to +$47.72. In the external closing-auction comparison, abstention removed $299 net of long exposure and reversing 13 of the remaining days cost a further $1,514. The fixed clock was specified before opening external trade outcomes. A subsequent diagnostic applied the same clock to 247 full 2023 and 244 full 2024 NQ sessions on the previously studied archive. At native NQ economics the results were −$14,781.50 and −$5,828 respectively. MNQ-equivalent dollars on those NQ price paths are in the receipt. They are different instruments and dates. At two contracts the $834 external benchmark drawdown would scale to $1,668 under identical fills and linear costs. [Attribution and transport](results/closing-attribution.json)

## The trade the exit was meant to fix

The November 19 10:45 long closed 211.25 points above entry on the 11:40 bar before exiting 279 points below entry. Both edits took the same −$564. The restart circuit reached 7.76 on the 12:01 bar, just before the original exit. Reaching the threshold on that bar would still have produced the same next-open fill. Across all 40 historical comparison sessions the largest fixed-entry saving was $146.50 on the November 18 10:02 short. The worst damage was on the next day's 12:03 short. Exiting at 12:26 turned +$347.50 into −$512. These are the two case buttons in the chart. [November 19 trace receipt](results/nov19-long.json)

| Historical full-policy net | Earlier 20 | Nov 19 | Other 13 November | Disjoint five | Known Nov 25 |
|---|---:|---:|---:|---:|---:|
| Original | −$847.50 | −$126.50 | +$2,239 | −$592.50 | −$220 |
| Restartable evidence | −$640.50 | −$234 | +$2,144 | −$549 | −$220 |
| Price-only restart | −$635 | −$234 | +$2,351.50 | −$541.50 | −$220 |
| Closing auction | −$227 | $0 | −$680 | −$112 | +$90 |

## Data and handoff

The publisher attributes the public bars to the TopstepX ProjectX gateway. UTC timestamps map to 390 consecutive regular minutes on 60 dates. All 4,680 five-minute OHLCV groups matched the separately published five-minute file exactly under minute-start labeling. February 16 was partial and April 3 had no regular bars. January 20 lacked a complete matching NQ grid. The symbol files have no row-level contract IDs. The pinned downloader maps to June contracts, but historical roll and live submission timing are unverified. Matching the publisher's two aggregations checks internal consistency. This was the first scoring on this source for these frozen designs. All 60 dates are now exposed. [Pinned source](https://github.com/axb0306/cme-futures-ohlc/tree/60abd3fb6369c6ce0b6a4a65b0f2562fc96b1264) · [Coverage and checksums](results/external/source.json)

In the downloaded kit, open replay.html or run the following from the extracted folder with Python, NumPy and pandas installed. The inspector requires one complete-to-date session on a minute-start grid, with UTC datetime or timestamp_utc, open, high, low, close and volume. Supply only finalized candles. The final argument is the last completed bar's New York start time. Optional --side and --entry trace a specified open position to the first stop or supplied last close.

```sh
python experiments/reservoir_lab/response_evidence/inspect_bars.py MNQ.csv 2026-03-02 15:29 --nq NQ.csv
```

In the research checkout, run the commands below from this directory. For the external run put the pinned MNQ minute, MNQ five-minute and NQ minute files under SCRATCH/response-evidence as MNQ.csv, MNQ_5min.csv and NQ.csv. The source and NQ agreement scripts enforce hashes. Trade labels and panel membership never enter the circuits. Archive the raw file separately if rebuilding elsewhere.

```sh
python -m pytest -q test_response.py
python run.py SCRATCH results/discovery --extended
python run.py SCRATCH results/external --extended --external
python attribution.py results PATH_TO_PINNED_NQ_ARCHIVE
python nov19.py SCRATCH results
```

A next research question is whether a circuit can estimate the value of continuing *after* a favorable excursion using the price path available at that moment. The November 19 trade had already earned a substantial open profit. That question needs a prespecified comparator such as a trailing exit at the same exposure and a new outcome panel. The external benchmark here establishes how much a direction call can cost even when its chosen dates are profitable long.
