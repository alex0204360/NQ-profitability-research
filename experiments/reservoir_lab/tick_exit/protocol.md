# Tick-sized exit evidence

Parent 823435e, in a separate worktree. November 19 was selected by the user after seeing a losing trade. All 34 archived sessions are discovery for this change. Use only the pinned September–October and November 3–20 bars. November 23 and the original prospective test are outside this experiment.

**Diagnosis before replay.** The rise from −2.06 on the 10:41 bar to −1.69 then +8.86 closed the profitable short. The reference entered long at the next opportunity after a +7.58 signal. Even at 11:49 the residual was +0.0006 points, so the zero-crossing policy kept the position open. Multiplying a positive memory by 7/8 can preserve its sign long after its magnitude loses economic significance.

**One edit.** Append four ReLUs to the signed point forecast. Let h(x)=2 ReLU(x−0.25)−ReLU(x−0.50), and y=h(x)−h(−x). This is zero within one MNQ tick, ramps continuously up to two ticks, and exactly copies larger magnitudes. The entry threshold stays 1.5 points. A fresh pulse can trigger reentry. The tick comes from contract granularity. There is no time-of-day rule, hard stop or tuned exit threshold. Freeze weights before scoring.

**Replay.** Compare original and candidate at next observed opens with $6 total friction per round trip, one contract, same gaps and 15:55 ET cutoff. The daily loss guard is a separate experiment and is disabled here. Trace the selected original entry, every replacement trade during its lifespan, the entire date and November excluding that date. Measure net, minute-close drawdown, trades, original winners cut short and offsetting new trades. Count a rerouted historical loss as discovery only. Preserve results including failure and do not search tick thresholds on these bars.
