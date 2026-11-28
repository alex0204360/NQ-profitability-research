import unittest

import pandas as pd

from experiments.barrier_response.run import opportunities


DAY = "2026-11-27"
START = pd.Timestamp(f"{DAY} 09:30", tz="America/New_York")


def make_bars(drop=()):
    index = pd.date_range(START, periods=391, freq="min")  # through 16:00
    if drop:
        index = index.delete([index.get_loc(START + pd.Timedelta(minutes=m)) for m in drop])
    step = {stamp: i for i, stamp in enumerate(pd.date_range(START, periods=391, freq="min"))}
    return pd.DataFrame({"open": [100.0 + step[t] for t in index]}, index=index)


def signals_at(*minutes, event="retained"):
    return pd.DataFrame([
        {"event": event, "signal": START + pd.Timedelta(minutes=m),
         "issued_bar": START + pd.Timedelta(minutes=m - 1),
         "next_close_barrier": 100.0, "open_beyond": False,
         "side": 1, "body": 1}
        for m in minutes
    ])


class OpportunityReplayTests(unittest.TestCase):
    def test_missing_due_bar_cancels_entry_and_releases_event_at_gap(self):
        bars = make_bars(drop=(1,))
        # The 09:30 signal's due open is missing; the 09:32 signal may retry at
        # the first available time after the cancellation boundary.
        rows = opportunities(bars, signals_at(0, 2), delay=0)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["accepted"])
        self.assertEqual(rows[0]["signal"], START + pd.Timedelta(minutes=2))
        self.assertEqual(rows[0]["entry_time"], START + pd.Timedelta(minutes=3))

    def test_gap_during_exposure_exits_at_first_available_open(self):
        bars = make_bars(drop=(4,))
        rows = opportunities(bars, signals_at(0), delay=0)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["entry_time"], START + pd.Timedelta(minutes=1))
        self.assertEqual(rows[0]["exit_time"], START + pd.Timedelta(minutes=5))
        self.assertEqual(rows[0]["exit"], bars.loc[rows[0]["exit_time"], "open"])

    def test_same_event_overlap_is_blocked_until_exit_close_then_reopens(self):
        bars = make_bars()
        rows = opportunities(bars, signals_at(0, 4, 6), delay=0)
        self.assertEqual([row["accepted"] for row in rows], [True, False, True])
        self.assertEqual(rows[0]["exit_time"], START + pd.Timedelta(minutes=6))
        self.assertEqual(rows[2]["entry_time"], START + pd.Timedelta(minutes=7))

    def test_extra_minute_latency_shifts_entry_and_exit_one_minute(self):
        bars = make_bars()
        signal = signals_at(0)
        immediate = opportunities(bars, signal, delay=0)[0]
        delayed = opportunities(bars, signal, delay=1)[0]
        self.assertEqual(delayed["entry_time"] - immediate["entry_time"], pd.Timedelta(minutes=1))
        self.assertEqual(delayed["exit_time"] - immediate["exit_time"], pd.Timedelta(minutes=1))
        self.assertEqual(immediate["entry"], bars.loc[immediate["entry_time"], "open"])
        self.assertEqual(delayed["entry"], bars.loc[delayed["entry_time"], "open"])

    def test_predetermined_exit_at_cutoff_allowed_beyond_cutoff_rejected(self):
        bars = make_bars()
        cutoff_minute = (pd.Timestamp(f"{DAY} 15:55", tz="America/New_York") - START).seconds // 60
        immediate = opportunities(bars, signals_at(cutoff_minute - 6, cutoff_minute - 5), delay=0)
        self.assertEqual(len(immediate), 1)
        self.assertEqual(immediate[0]["exit_time"], pd.Timestamp(f"{DAY} 15:55", tz="America/New_York"))
        delayed = opportunities(bars, signals_at(cutoff_minute - 7, cutoff_minute - 6), delay=1)
        self.assertEqual(len(delayed), 1)
        self.assertEqual(delayed[0]["exit_time"], pd.Timestamp(f"{DAY} 15:55", tz="America/New_York"))


if __name__ == "__main__":
    unittest.main()
