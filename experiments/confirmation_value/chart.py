"""Plot the largest beneficial and costly edits on the external next-open book."""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/New_York")


def draw(root, dest):
    decisions = pd.read_csv(root/"confirmation_value/results/decisions.csv.gz")
    chosen = decisions[decisions.source.eq("external60") & decisions.delay.eq(0) & decisions.survival_grid.lt(0)].copy()
    chosen["effect"] = -2 * chosen.y
    chosen["parent_net"] = chosen.direction * (chosen.original_exit_price - chosen.trade_id.map(
        pd.read_csv(root/"capacity/results/trades.csv.gz").query("model == 'original' and delay == 0").set_index("trade_id").entry
    )) * 2 - 6
    winners = chosen[chosen.parent_net > 0]
    trades = pd.read_csv(root/"capacity/results/trades.csv.gz")
    trades = trades[trades.model.eq("original") & trades.delay.eq(0)].set_index("trade_id")
    bars = pd.read_csv(root/"capacity/results/scores.csv.gz", usecols=["bar_start","panel","open","high","low","close"])
    bars = bars[bars.panel.eq("external")].copy()
    bars.index = pd.to_datetime(bars.bar_start, utc=True).dt.tz_convert(TZ)
    fig, axes = plt.subplots(2, 1, figsize=(9,6.7), layout="constrained")
    for ax, idx, title in zip(axes,[chosen.effect.idxmax(),winners.effect.idxmin()],
                             ["Largest saving","Largest damaged winner"]):
        x = chosen.loc[idx]
        tr = trades.loc[x.trade_id]
        start = pd.Timestamp(tr.entry_time).tz_convert(TZ)
        end = pd.Timestamp(tr.exit_time).tz_convert(TZ)
        early = pd.Timestamp(x.early_time).tz_convert(TZ)
        segment = bars.loc[(bars.index >= start) & (bars.index <= end)].sort_index()
        # Opens share a clock with both marked executable fills.
        ax.plot(segment.index,segment.open, color="#344e65", linewidth=1.6, label="Minute open")
        for time,price,label,mark,color in [(start,tr.entry,"Entry","o","#0d4f63"),
                (early,x.early_price,"Early exit","D","#b14b0c"),(end,tr.exit,"Original exit","s","#313e85")]:
            ax.scatter([time],[price],label=label, marker=mark, s=50,color=color,zorder=3)
        ax.set_title(f"{title}   {x.date}   {tr.side}   change {x.effect:+,.2f} USD",loc="left",fontsize=12)
        ax.set_ylabel("MNQ points")
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3,maxticks=8))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M",tz=TZ))
        ax.grid(axis="y",alpha=.25)
        ax.spines[["top","right"]].set_visible(False)
    axes[0].legend(loc="best",ncols=4,fontsize=8)
    axes[1].set_xlabel("New York time")
    fig.suptitle("Early exits changed the value of keeping the original position",fontsize=14)
    fig.savefig(dest,dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("experiments",type=Path)
    parser.add_argument("output",type=Path)
    args = parser.parse_args()
    draw(args.experiments,args.output)
