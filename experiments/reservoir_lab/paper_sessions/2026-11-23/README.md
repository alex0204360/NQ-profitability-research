# November 23 pre-registered one-day paper scorecard

Replayed November 23 data on the morning of November 24 using the separate frozen workbench 823435e and dated Yahoo MNQZ26.CME one-minute bars. This session was not input to the trade-memory study. Only the original and pre-registered −$500 session-loss guard were scored. Cash returned zero. Each strategy traded one MNQ with $6 round-trip friction, completed-bar signals, modeled next-open fills and a 15:55 New York flatten. The source contained all 390 expected bars; the dated-contract mapping and minute-start convention are vendor assumptions. No time-aligned bid/ask tape was supplied or available here. This is one forward paper observation on the original policy. November 23 is now exposed for any future redesign.

| Policy | Trades | Net | Max marked drawdown | Last exit ET |
|---|---:|---:|---:|---|
| Original | 21 | −$645.00 | $1,273.50 | 15:55 |
| Daily guard | 10 | −$531.50 | $832.00 | 11:44 |

The loss trigger observes the completed minute and requests the next open, which can realize a loss beyond $500. The original made seven winning trades, and both sides lost in aggregate. The scorecard and both ledgers were reproduced from the retained raw response. The response is retained privately and its SHA-256 and exact source URL are recorded in scorecard.json. The HTML includes every modeled fill for each policy. Eligible for the originally frozen aggregate study only under its separate source criteria; the one-day result alone cannot qualify a strategy.
