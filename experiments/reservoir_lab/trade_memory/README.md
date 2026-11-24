# Trade memory belongs to an episode

The candidate failed the registered return screen. Keep the original reservoir as a reference and execution in cash. Resetting the failed-recovery memory corrected a real state-boundary problem and lowered November drawdown. It did not establish that filtering an old signal improves expectancy.

## What changed

The original exit study judged price patterns that could begin while the strategy was flat. Also, when an early exit freed the position, the opening forecast could still contain the deposit which had paid for the first entry. Break the two causal paths independently. The first edit resets the shock endpoints and armed latch on fill; only a move between two completed closes during the trade can supply its setup. The second resets an auxiliary copy of the reservoir at a failed-recovery exit. Before a same-direction re-entry, this copy must independently accumulate and release enough new volume evidence to clear the original 1.5-point hurdle. Allow a raw reversal to start a new episode. Market normalization and normal entry/exit assumptions carry through. The new state-routing circuit, its exact coefficients, primary candidate and acceptance screen were committed before scoring. [Protocol](protocol.md) · [Weights](weights.json) · [Circuit](routing.py)

## Paper replay

Trade one MNQ at next opens with $6 round-trip friction and a 15:55 ET cutoff. Each cell shows net / maximum minute-close drawdown in dollars. Each panel starts at zero. November 19 is included in the 14-date row and is broken out for diagnosis.

| Panel | Original reservoir | Prior failed recovery | Reset exits only | Fresh entries only | Both changes |
|---|---:|---:|---:|---:|---:|
| Sep 14–Oct 9 · 20 | −847.50 / 2,269 | −877.50 / 2,057 | −732 / 2,009 | −538 / 1,795 | −540 / 1,883 |
| Nov 3–20 · 14 | +2,112.50 / 1,727.50 | +1,425 / 1,157 | +1,317 / 1,156 | +763 / 1,172 | +1,401.50 / 1,012 |
| Nov 19 · 1 | −126.50 / 1,526.50 | −383 / 1,094 | −403 / 1,094 | −216.50 / 906 | −22.50 / 713.50 |
| Other 13 Nov | +2,239 / 995 | +1,808 / 824.50 | +1,720 / 824.50 | +979.50 / 1,012 | +1,424 / 1,012 |

**Memory audit.** Among full prior-policy hold exits, 15 of 51 in the earlier sample and 11 of 52 in November used a qualifying adverse shock whose starting close preceded the actual entry. On identical original entries, resetting exit memory changed November net from +$829.50 to +$1,447.50. Earlier net went from −$427 to −$591. Many apparent new-entry failures were genuine new evidence; on Nov 19 the 11:55 long still lost $436.50 with the fresh gate. The 10:45 long itself moved from −$564 under the original and −$127.50 under prior failed recovery to +$66.50 under both changes.

**Full replay.** In November the combined candidate gained $618 on its 103 shared entries versus prior failed recovery, skipped 19 entries worth +$612 and added three worth −$29.50. Net difference −$23.50; marked drawdown improved by $145. The two isolated effects were −$108 and −$662; their interaction was +$746.50. Treat their sum as policy effects including changed opportunities. The combined candidate gained $360.50 on Nov 19 and lost $384 relative to the prior policy on the other thirteen dates. The earlier twenty-date improvement of $337.50 was still a net loss of $540. The descriptive five-day paired interval for incremental daily dollars included zero in both primary panels. The earlier marked drawdown exceeded the historical $1,500 firm budget. The results are exploratory.

**Registered six-date replication.** Five of six MNQZ26 sessions passed source checks. October 30 had 381 usable daytime bars across both Yahoo endpoints and both query windows. Nine missing minutes prevent scoring the registered complete panel. This previously documented gap recurred. The five-date remainder was not substituted. Results contain only the 34 earlier research dates. [Capture receipt](capture_receipt.json)

**Separate forward paper observation.** The original pre-market kit on November 23 recorded −$645 on 21 trades versus −$531.50 on 10 for the daily guard. These results do not test the new memory circuit. No nine-second fill evidence was available. [November 23 scorecard](../paper_sessions/2026-11-23/README.md)

## Reproduction and artifacts

Use the original checkout's pinned six historical CSVs and three private November snapshots in the layout described by its workbench. Run from this directory:

```sh
python -m pytest -q test_memory.py ../adverse_impact/test_simulator.py
python run.py /path/to/scratch /tmp/memory-results
python capture_panel.py --verify --out /path/to/private-captures --receipt capture_receipt.json
```

The runner cross-checks original, continuous and fixed-entry prior ledgers, including exact fill times, directions, exit reasons and net dollars. The optional policy callback runs at each close after open fills. The earlier execution path remains reproducible without it. Original Forecast (pts) stays on screen; Hold value (pts) is experimental and positive favors holding either side. Reset markers indicate entry fills in local-memory modes. Use the two case buttons to compare original and edited exits with entry held identical. On the November 19 long at 10:45, the edited exit at 11:23 improved net by $630.50. On the November 10 short at 10:18, exiting at 10:33 cut a $662 winner to a $6 loss. The chart shows both exit times and prices. The event audit marks raw-above-hurdle bars suppressed by the fresh gate; several such bars may belong to one blocked episode. The folder contains full trade ledgers, daily net changes, routing diagnostics and a signed comparison against the original and the prior exit. [Detailed results](results/results.json)

## What the identical-entry comparison isolates

Each amount is the net change in dollars against the original. Marked drawdown uses completed minute closes. The paired comparison fixes every original entry. The full replay also changes subsequent opportunities.

| Panel | Saved on original losers | Change on original winners | Fixed-entry drawdown | New same-episode re-entries vs original (count / net) | Missed original trades (count / original net) | Additional friction in full policy |
|---|---:|---:|---:|---:|---:|---:|
| Earlier 20 | +526 | −269.50 | 2,019.50 | 11 / −213.50 | 8 / +38 | 66 |
| Nov 19 | +630.50 | −388.50 | 362.00 | 3 / −138 | 0 / 0 | 18 |
| Other 13 Nov | +1,268 | −2,175 | 941.50 | 10 / −3.50 | 6 / −125 | 60 |
| All 14 Nov | +1,898.50 | −2,563.50 | 941.50 | 13 / −141.50 | 6 / −125 | 78 |

The four-minute hold readout is an experimental score in points. The original side and exit conditions still apply, and the first nonpositive hold score while positioned requests the next executable open. Full attribution, including other added entries, is in results/results.json. The two charts, numerical weights and results are also bundled in [trade-memory-review.zip](trade-memory-review.zip).
