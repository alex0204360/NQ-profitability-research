# Can high volume without price progress predict the next repricing?

Two hand-programmed recurrent networks were frozen and executed. The signed-area network lost after costs in all three panels. The redesigned network earned positive stressed net in two later November panels but lost in discovery. It remains a frozen research candidate. Independently validated discoveries: **zero**. Execution allocation: **cash**.

## What changed inside the network

The first network retained separate memories of effort (relative volume) and motion (normalized close displacement). Its two product neurons compared effort followed by motion with motion followed by effort. On discovery, 583 of its 695 trades began with nonpositive effort memory. Reversing both the volume anomaly and price increment preserves their product; consequently the network could interpret quiet trading as evidence for a volume-led move. It earned $0.24 gross per trade against $3 base costs.

The second network lets a bar deposit evidence only when positive volume surprise exceeds absolute price displacement. A later signed move spends a fraction of the stock. A one-range move spends all available stock; the same deposit cannot fund repeated releases. The remaining directional forecast controls the exit. Median immediate holding time rose from five to fourteen minutes on discovery. The new mechanism improved the gross average to $1.89 per trade, still below costs. OHLCV gives no direct observation of trade aggressor, hidden liquidity or order-book imbalance. The reservoir measures a proxy. Numerical matrices and the algebraic motivation are in [area.json](area.json), [reservoir.json](reservoir.json), and [protocol.md](protocol.md).

## One-contract MNQ results

All figures below charge $6 per round trip. Immediate means the next bar's open. Delayed adds one minute to signal-driven entry and exit. Drawdown is measured at every minute close with one-way costs at each fill. Source timestamps are assumed to mark bar starts. The aggregate November rows count each session once.

| Reservoir panel | Sessions | Immediate trades | Net | Net/trade | Marked drawdown | Delayed trades | Delayed net | Delayed drawdown |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Sep 14–Oct 9, discovery | 20 | 206 | −$847.50 | −$4.11 | $2,269.00 | 188 | −$1,409.00 | $2,976.50 |
| Nov 16–20, first later replay | 5 | 25 | +$867.00 | +$34.68 | $1,727.50 | 25 | +$1,008.00 | $1,868.50 |
| Nov 3–13, extension scored second | 9 | 68 | +$1,245.50 | +$18.32 | $874.00 | 64 | +$896.00 | $973.50 |
| Nov 3–20 together, descriptive | 14 | 93 | +$2,112.50 | +$22.72 | $1,727.50 | 89 | +$1,904.00 | $1,868.50 |

| Frozen comparison, immediate stressed net | Discovery | Nov 16–20 | Nov 3–13 |
|---|---:|---:|---:|
| Signed area | −$4,002.50 | −$1,165.50 | −$2,080.50 |
| Symmetric product readout | −$1,705.00 | −$3,483.00 | −$5,671.00 |
| Leaky price momentum | −$6,163.50 | −$3,033.00 | −$1,641.50 |
| Reservoir with volume-only deposits | −$3,240.00 | −$851.00 | −$1,579.50 |
| Cash | $0 | $0 | $0 |

**Incremental value.** The volume-only ablation isolates the deposit penalty for price movement. The complete reservoir beat this ablation on all three immediate-fill panels. With the additional minute of delay the ablation beat it on November 16–20 ($1,201 versus $1,008). On all fourteen November sessions the paired five-session block interval for daily improvement over that ablation spans −$136 to +$411 at the delayed fill. The mechanism remains unresolved under delay. Freezing the reservoir's November entry and exit times but using the momentum direction gives −$483.50 immediate stressed net across the two panels, versus +$2,112.50 for the reservoir. This last comparison shares the circuit's exits and is a directional diagnostic only. All-bar eight-minute signed returns for the reservoir switched from +0.30 points in discovery to −6.24 in the first later panel; profitable variable-duration trades do not establish a general eight-minute forecast.

**Risk and concentration.** November immediate stressed net stayed positive (+$1,224) after removing its best date; nine of fourteen dates made money. Median trade was +$2.00, versus +$22.72 mean. November had no gap exits. Discovery had four immediate reservoir gap exits; excluding all four leaves −$1,144. The November marked drawdowns exceeded the prior $1,500 firm budget at both fills. A minute-close simulation cannot determine compliance with intrabar or trailing account rules. Exact spread, queue, fees, latency and executable fills require independent data. The engine assumes an adverse all-in cost per trade; changing fees alone never changes the submitted orders.

## Data exposure and prospective handoff

- The discovery source is the repository's previously opened continuous MNQ=F minute archive at commit 8336fe8. Roll mapping is unresolved. Neither the oracle teacher labels nor sealed 2025 bars enter this experiment.
- The later source was requested by dated symbol MNQZ26.CME. The chart metadata identifies CME futures and one-minute granularity. It omits an independent contract identifier, expiration and a definitive minute-start convention. November 16–20 yielded all 1,950 expected daytime bars. The weights were frozen before inspecting these prices. The nine-session extension was registered **after** that result and covers all remaining full weekdays since the last documented November 2 upload. Its 3,510 daytime bars were complete. Each earlier query also returned one later timestamp outside the request; both were excluded before scoring. All exposure now extends through November 20 for this program. The fourteen sessions are temporal replication on the same vendor, not a prospective validation cohort.
- Keep the reservoir frozen for the first registered **20 new full sessions, November 23–December 22, 2026**. Individual December and March contracts, switch date, source audit, complete observation requirement and paired economic screens are locked in [prospective.json](prospective.json). Treat risk qualification separately. Score once with [prospective.py](prospective.py) after the immutable source is available. The prospective track has no market observations yet.
- The older fitted $8 gate used other archived campaigns and a different execution policy. It was not replayed on these panels. The comparisons here are cash, momentum, matched-direction, symmetric-order and volume-only controls. Historical comparisons to the impulse and auction studies use their own instrument and contracts. [Prior impulse research](../impulse_context/README.md) · [Prior auction research](../astra/README.md)

## Reproduction

Use Python 3.12, NumPy and pandas. Run commands in this directory. Read the six numbered September–October CSV parts from commit 8336fe8 under data/mnq_oracle_2026 into a private directory; the loader verifies every part against its SHA-256. For the November periods, preserve each raw chart response privately. The GitHub receipts record the exact URLs, SHA-256 digests and dropped timestamps. If the vendor revises or expires a response, use the captured bytes. Never substitute a newly returned price tape without reporting the changed digest.

```sh
python -m pytest -q test_*.py
python evaluate.py --discovery /path/to/six-parts --models area reservoir volume_control --out /tmp/mnq-discovery
python capture.py /path/to/november
python capture.py /path/to/extension1 --window extension1
python capture.py /path/to/extension2 --window extension2
python evaluate.py --november /path/to/november/bars.csv --models area reservoir volume_control --out /tmp/mnq-november
python evaluate.py --extension /path/to/extension1/bars.csv /path/to/extension2/bars.csv --models area reservoir volume_control --out /tmp/mnq-extension
```

Private capture bundle directories use the prefixes mnq-november, mnq-extension1 and mnq-extension2. Each includes the raw JSON and normalized CSV. Future scoring accepts one canonical unadjusted source with timestamp_utc, contract, open, high, low, close, volume columns and an independently recorded checksum. Use the contract strings in the manifest. The score command is `python prospective.py /path/to/bars.csv --sha256 SOURCE_DIGEST --out /path/to/new-results`. The runner verifies the frozen code and weights and returns numerical screens; documentary source and fill verification remain a separate research obligation.

The Git history records the area freeze (339cad9), execution freeze (9440609), first result (5865d14), reservoir surgery (ba7972f), first temporal registration and capture (8d43a1d), and extension freeze (e50b52b). The discovery, november and november-extension directories contain all cost/delay combinations, daily equity changes and mechanism diagnostics. Trade ledgers include decision-time activations, gross and $3-base results. Subtract $3 per trade from base net to reproduce stressed net.
