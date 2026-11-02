"""Local, research-only paper decision endpoint with an append-only audit journal.

The caller supplies completed causal features. This service neither builds a feed
nor submits orders. A prospective paper run requires newly observed bars.
"""

import argparse
import hashlib
import json
import math
import threading
import time
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from tools.reliability_decision_api import _time, decide


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


class PaperRecorder:
    def __init__(self, journal, model_root, family, fold, *, gate_usd=10,
                 engine=decide, clock=None):
        self.journal = Path(journal)
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        self.model_root = Path(model_root)
        self.family, self.fold = family, fold
        if gate_usd not in (8, 10, None):
            raise ValueError('Only frozen $8 or $10 gates supported')
        self.gate_usd = gate_usd
        self.engine = engine
        self.clock = clock or (lambda: datetime.now(UTC))
        self.lock = threading.Lock()
        self.last = {}
        self.pending = {}
        if self.journal.exists():
            for line in self.journal.read_text().splitlines():
                record = json.loads(line)
                if record.get('status') == 'accepted':
                    key = record['source_id']
                    instant = _time(record['available_at'])
                    if key not in self.last or instant > self.last[key]:
                        self.last[key] = instant
                    if record.get('action') in ('enter_long', 'enter_short'):
                        self.pending[record['decision_id']] = record
                elif record.get('status') == 'paper_fill':
                    self.pending.pop(record['decision_id'], None)

    def _append(self, record):
        with self.journal.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(record, sort_keys=True, allow_nan=False) + '\n')
            stream.flush()

    def query(self, envelope):
        """Return a proposal or a recorded rejection; never place an order."""
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError('Aware server clock required')
        now = now.astimezone(UTC)
        record = {'schema_version': 'paper-decision-event-v1',
                  'received_at': now.isoformat(), 'family': self.family,
                  'fold': self.fold, 'gate_usd': self.gate_usd,
                  'orders_submitted': 0,
                  'simulated_fill': None, 'status': 'rejected'}
        with self.lock:
            try:
                if not isinstance(envelope, dict) or set(envelope) != {
                    'source_id', 'data_sha256', 'observation'
                }:
                    raise ValueError('Exact paper envelope fields required')
                source = envelope['source_id']
                digest = envelope['data_sha256']
                if not isinstance(source, str) or not source or len(source) > 80:
                    raise ValueError('Nonempty source_id up to 80 characters required')
                if not isinstance(digest, str) or len(digest) != 64 or any(
                    c not in '0123456789abcdef' for c in digest
                ):
                    raise ValueError('Lowercase SHA-256 data identity required')
                record.update(source_id=source, data_sha256=digest)
                obs = envelope['observation']
                if not isinstance(obs, dict):
                    raise TypeError('Observation object required')
                record['state_sha256'] = hashlib.sha256(_canonical(obs)).hexdigest()
                available = _time(obs['available_at'])
                record['available_at'] = available.isoformat()
                record['state_timestamp'] = available.isoformat()
                age = (now - available).total_seconds()
                record['latency_ms'] = round(age * 1000, 3)
                if age < 0 or age > 120:
                    raise ValueError('Stale or future-dated completed bar')
                if source in self.last and available <= self.last[source]:
                    raise ValueError('Out-of-order or repeated completed bar')
                computation_started = time.perf_counter()
                if self.engine is decide:
                    result = self.engine(self.model_root, self.family, self.fold,
                                         obs, mode='paper', now=now,
                                         gate_usd=self.gate_usd)
                else:
                    result = self.engine(self.model_root, self.family, self.fold,
                                         obs, mode='paper', now=now)
                record['decision_compute_ms'] = round((time.perf_counter() - computation_started) * 1000, 3)
                if result.get('live_authorized') is not False or result.get('orders_submitted') != 0:
                    raise ValueError('Decision engine lacks paper-only guard')
                record.update(status='accepted', action=result['action'],
                              reason=result['reason'], model_hashes=result['hash_lineage'],
                              decision_id=hashlib.sha256(_canonical({
                                  'source_id': source, 'available_at': available.isoformat(),
                                  'state_sha256': record['state_sha256'],
                                  'model_hashes': result['hash_lineage']})).hexdigest())
                self.last[source] = available
                if record['action'] in ('enter_long', 'enter_short'):
                    self.pending[record['decision_id']] = record
                self._append(record)
                return {'event': record, 'decision': result}
            except (KeyError, TypeError, ValueError, OverflowError) as error:
                record['rejection_reason'] = str(error)
                self._append(record)
                return {'event': record, 'decision': None}

    def record_next_open(self, envelope):
        """Record the next observed open as a paper reference; no actual fill claim."""
        now = self.clock().astimezone(UTC)
        with self.lock:
            if not isinstance(envelope, dict) or set(envelope) != {
                'decision_id', 'source_id', 'bar_start', 'open'
            }:
                raise ValueError('Exact next-open fields required')
            decision = self.pending.get(envelope['decision_id'])
            if decision is None or decision['source_id'] != envelope['source_id']:
                raise ValueError('Unknown pending paper entry')
            bar_start = _time(envelope['bar_start'])
            if bar_start != _time(decision['available_at']):
                raise ValueError('Next bar is missing or out of order')
            if now < bar_start + timedelta(minutes=1):
                raise ValueError('Next bar has not completed')
            price = envelope['open']
            if type(price) not in (int, float) or not math.isfinite(price) or price <= 0:
                raise ValueError('Positive finite open required')
            if abs(price / .25 - round(price / .25)) > 1e-7:
                raise ValueError('MNQ open must align to 0.25-point tick')
            record = {'schema_version': 'paper-fill-event-v1', 'status': 'paper_fill',
                      'decision_id': envelope['decision_id'], 'source_id': envelope['source_id'],
                      'received_at': now.isoformat(), 'bar_start': bar_start.isoformat(),
                      'reference_open': price, 'cost_scenario_usd': 6,
                      'fill_type': 'observed_next_open_reference', 'orders_submitted': 0}
            self._append(record)
            self.pending.pop(envelope['decision_id'])
            return record


def handler_for(recorder):
    class Handler(BaseHTTPRequestHandler):
        def _reply(self, status, body):
            data = _canonical(body)
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == '/health':
                self._reply(200, {'status': 'paper_only', 'orders_submitted': 0})
            else:
                self._reply(404, {'error': 'Unknown endpoint'})

        def do_POST(self):
            if self.path not in ('/decide', '/next-open'):
                self._reply(404, {'error': 'Unknown endpoint'})
                return
            try:
                length = int(self.headers.get('Content-Length', '-1'))
                if length < 0 or length > 100_000:
                    raise ValueError('Request body length must be 0..100000 bytes')
                envelope = json.loads(self.rfile.read(length))
                if self.path == '/decide':
                    answer = recorder.query(envelope)
                    self._reply(200 if answer['decision'] is not None else 422, answer)
                else:
                    self._reply(200, recorder.record_next_open(envelope))
            except (ValueError, json.JSONDecodeError) as error:
                self._reply(400, {'error': str(error)})

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--journal', type=Path, required=True)
    parser.add_argument('--family')
    parser.add_argument('--fold')
    parser.add_argument('--gate', type=int, choices=(8, 10), default=10)
    parser.add_argument('--student', choices=('ridge_dual_delay', 'extra_trees_dual_delay'))
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    if args.student:
        from tools.cloud_student_decision_api import decide as student_decide

        def student_engine(run, candidate, unused_fold, observation, *, mode, now):
            return student_decide(run, candidate, observation, mode=mode, now=now)

        recorder = PaperRecorder(args.journal, args.root, args.student, 'cloud_campaign01',
                                 gate_usd=None, engine=student_engine)
    else:
        if not args.family or not args.fold:
            parser.error('--family and --fold are required without --student')
        recorder = PaperRecorder(args.journal, args.root, args.family, args.fold,
                                 gate_usd=args.gate)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler_for(recorder))
    server.serve_forever()


if __name__ == '__main__':
    main()
