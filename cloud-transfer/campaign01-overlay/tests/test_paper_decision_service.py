"""Paper service ordering and audit behavior with a synthetic decision engine."""
import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tools.paper_decision_service import PaperRecorder

NOW = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)


def fake_engine(root, family, fold, observation, *, mode, now):
    assert mode == 'paper'
    return {'action': 'enter_long', 'reason': 'Synthetic threshold',
            'hash_lineage': {'synthetic.model': 'a' * 64},
            'live_authorized': False, 'orders_submitted': 0}


class PaperDecisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.journal = Path(self.temp.name) / 'events.jsonl'
        self.now = NOW
        self.recorder = PaperRecorder(self.journal, self.temp.name, 'extra_trees',
                                      'fold3', engine=fake_engine, clock=lambda: self.now)

    def query(self, when=NOW):
        return self.recorder.query({'source_id': 'feed-A', 'data_sha256': 'b' * 64,
                                    'observation': {'available_at': when.isoformat(),
                                                    'ready': True, 'features': {'x': 1}}})

    def test_records_rejections_and_survives_restart(self):
        accepted = self.query()
        self.assertEqual(accepted['event']['status'], 'accepted')
        self.assertEqual(accepted['decision']['action'], 'enter_long')
        repeated = self.query()
        self.assertIn('Out-of-order', repeated['event']['rejection_reason'])
        old = self.query(NOW - timedelta(seconds=121))
        self.assertIn('Stale', old['event']['rejection_reason'])
        self.recorder = PaperRecorder(self.journal, self.temp.name, 'extra_trees',
                                      'fold3', engine=fake_engine, clock=lambda: self.now)
        self.assertEqual(self.query()['event']['status'], 'rejected')
        events = [json.loads(line) for line in self.journal.read_text().splitlines()]
        self.assertEqual(len(events), 4)
        self.assertEqual(events[0]['orders_submitted'], 0)
        self.assertIsNone(events[0]['simulated_fill'])

    def test_next_open_requires_completed_contiguous_bar(self):
        accepted = self.query()
        identifier = accepted['event']['decision_id']
        payload = {'decision_id': identifier, 'source_id': 'feed-A',
                   'bar_start': NOW.isoformat(), 'open': 25000.25}
        with self.assertRaisesRegex(ValueError, 'not completed'):
            self.recorder.record_next_open(payload)
        self.now += timedelta(minutes=1)
        with self.assertRaisesRegex(ValueError, 'missing'):
            self.recorder.record_next_open({**payload,
                                            'bar_start': (NOW + timedelta(minutes=1)).isoformat()})
        fill = self.recorder.record_next_open(payload)
        self.assertEqual(fill['fill_type'], 'observed_next_open_reference')
        self.assertEqual(fill['reference_open'], 25000.25)
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            self.recorder.record_next_open(payload)


if __name__ == '__main__':
    unittest.main()
