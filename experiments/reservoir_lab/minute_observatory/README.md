# MNQ minute observatory

[Download the monitor and two charts](minute-observatory.zip). Open **November-23-replay.html** in the downloadable kit for an entire session with fills. The slider moves the information boundary through the session. The November 24 snapshot shows only completed minutes available at capture. The running observer uses the frozen original reservoir (03ec0a1). All trades and size comparisons are simulated.

## Start a local paper monitor

With Python 3.10+ and the kit extracted, run from the top-level folder:

```sh
python -m pip install numpy pandas
python monitor.py --contract MNQZ26 --out paper-session --serve --through-close
```

Open http://127.0.0.1:8765 in your browser on that computer. The server binds to loopback. Stop with Ctrl+C. For a checkout, replace `monitor.py` with `experiments/reservoir_lab/minute_observatory/observer.py`. Select the actual dated contract for each session. Use a full regular session. Holiday and early-close schedules have no special treatment in this research tool. The registered forward panel excludes shortened sessions.

For a faster data source, give the observer a growing CSV from your authorized feed writer. The writer must publish finalized one-minute bars, preferably by atomic replacement. Run a separate output directory for each data source.

```sh
python monitor.py --contract MNQZ26 --csv my-bars.csv --out my-paper-session --serve --through-close
```

The header is `timestamp_utc,contract,open,high,low,close,volume`. Timestamps identify the **start** of each bar, with Z or an explicit UTC offset. Prices are unadjusted tick-aligned prices of the named contract. The observer checks the file once per second between refreshes or the dated Yahoo source every 15 seconds. Yahoo bars need a later vendor timestamp to confirm completion. Its MNQ feed during this run lagged by approximately ten minutes. CSV freshness depends on the upstream provider.

## Reading the screen

The frozen encoder stores unspent volume surprise, releases it in the direction of price motion, and converts the directional memory to an experimental score in points. After 32 contiguous daytime bars, a flat position can enter beyond ±1.5 points. A zero crossing against an open position requests an exit. The chart displays the bar start, theoretical close-decision time, first local receipt and computation, in New York time. On first launch, older bars are backfilled and computed together. Good historical model timestamps alone cannot establish timely decisions. Modeled fills use the next contiguous open and become visible when that subsequent bar has been received. Pine/tick execution, a broker and a real-time quote subscription are outside this tool.

Changing paper size doubles fill costs, marked equity and drawdown on identical fills. It assumes both contracts fill at the same price. Drawdown is peak-to-trough using minute-close marks and a zero starting balance. Intraminute excursions and real slippage can be larger. The live chart resets money statistics for each session; the study compounds dollar P&L across dates within each panel with fixed size.

Each input journal persists first-seen bars, receipt times, response digests and the actual first computed forecasts, decisions and position sides. The local receipt-to-decision journal can be inspected in SQLite. Revisions and late insertions are logged separately so a displayed past decision cannot be rewritten. Missing bars invalidate pending orders and reset the neural warmup. A position spanning a gap exits at the next observed open in the paper model. Hold, flat, and scheduled flatten are explicit on the dashboard.

## Entry experiment and sizing

Design and weight freeze 0ac889d. Remove the largest direction-supporting release still present in the reservoir before admitting an entry. Keep all exits unchanged. This tests whether more than one price-volume release needs to support an entry. The candidate failed its predeclared screen. Across 14 November sessions only one original entry timestamp survived unchanged. The gate also admitted later signals and gave away most of November's net. Its better earlier result was still negative. It remains in discovery. The observer never runs this edit. [Protocol](protocol.md) · [Weights](weights.json) · [Discovery results](results/results.json)

| Discovery window | Original net / drawdown, one | Original net / drawdown, two | Entry edit net / drawdown, one | Entry edit net / drawdown, two |
|---|---:|---:|---:|---:|
| Earlier 20 | −847.50 / 2,269 | −1,695 / 4,538 | −334.50 / 1,642.50 | −669 / 3,285 |
| All 14 November | +2,112.50 / 1,727.50 | +4,225 / 3,455 | +165.50 / 1,678.50 | +331 / 3,357 |
| November 19 | −126.50 / 1,526.50 | −253 / 3,053 | −159 / 1,074 | −318 / 2,148 |
| Other 13 November | +2,239 / 995 | +4,478 / 1,990 | +324.50 / 856.50 | +649 / 1,713 |

On the separate November 23 replay the **original** earned −$645 with $1,273.50 drawdown at one, or −$1,290 with $2,547 drawdown at two. The previous one-bar confirmation exit had +$2,013.50 net / $1,245 drawdown in the 14 historical November sessions; at two that is +$4,027 / $2,490. Its earlier 20 sessions were −$530.50 / $1,942 at one or −$1,061 / $3,884 at two. No new candidate was run on November 23 or 24.

## From signals to evidence

1. **Observe.** Read the original brain, every completed bar, without changing weights during the forward study. Inspect receipt lag, missed observations and corrections every session.
2. **Measure executable prices.** Capture dated bid/ask and receipt times from a licensed real-time feed. Use the existing nine-second quote audit on the signal ledger, and compare next-open proxy returns to executable-side prices. Actual routing also requires decision, arrival and fill timestamps.
3. **Qualify one MNQ.** The original registered 20 named sessions run November 23 through December 22 with a scheduled contract roll. See the included prospective.json for source, benchmark, uncertainty, trade-count and marked risk tests. Yahoo monitoring alone cannot qualify the original. A new candidate needs its own untouched test.
4. **Evaluate size independently.** Under the requested $1,500 ceiling, identical fills require one-contract marked drawdown no greater than $750 to fit two. The historical protocol requires drawdown strictly below its budget; exact firm intraday rules and incremental slippage can tighten the constraint.

The research replay asserts exact reproduction of the original via an ablated entry gate. The minute observer was checked against the original engine on all 35 archived sessions, including discovery sessions with observed gaps, with every minute's mark and each fill matching. Prefix tests cover warmup, partial sessions, and chart history. Use the scripts in this directory for reproduction:

```sh
python evaluate_entry.py /path/to/private/scratch /tmp/entry-study
python verify.py /path/to/private/scratch /path/to/nov23/raw-chart.json /tmp/session-replay
```


## Risk within the minute and host timing

With identical modeled fills, equity is linear in the marked price while a position is open. For every observed bar, compute the lowest possible drawdown if the account low precedes the high, and the highest possible if that order reverses. Both paths must visit open and close in the correct order. The bounds agree for the original on the November panel. The close-based $1,727.50 drawdown reached $1,803 using OHLC extrema, or $3,606 at two. The previous confirmation strategy reached $1,304.50 at one or $2,609 at two. November 23 original intraminute drawdown was $1,374.50 at one or $2,749 at two. Missing observations, execution prices and actual firm liquidation rules can change realized risk. The dashboard equity chart uses close marks. [OHLC calculations](results/risk-bounds.json)

The CPU timing trial fed all 390 November 23 bars, one at a time, through the growing-CSV adapter, durable journal, decision computation and snapshot publication. Each resulting forecast, position, decision, fill and equity mark matched its reference prefix. Median processing took 42.49 ms, p95 61.23 ms and maximum 91.12 ms in this run. These times exclude upstream delivery, CSV polling (one second), browser refresh (two seconds), manual interaction and execution. [Timing receipt](results/host-latency.json)

## First delayed November 24 forecast

The first 32-bar forecast was +29.2573 points on the bar starting 10:01 ET. Its theoretical close decision was 10:02 ET. The host first observed it at 10:12:15 ET and recorded **Long next open** at 10:12:15 ET. That is 615.5 seconds after the close. The public source was delayed. This is a dated operational observation of the unchanged original and carries no completed-day performance claim. [First recorded call](results/first-observation.json)
