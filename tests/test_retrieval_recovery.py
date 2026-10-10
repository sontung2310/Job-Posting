"""Offline recovery regressions; never submit paid requests."""
import json
import sys
import subprocess
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'.agents/skills/job-retrieval/scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import discovery
import apify_transport as transport
from test_discovery import state

class RecoveryTests(unittest.TestCase):
    def test_interrupted_indeed_retries_boundedly(self):
        saved = state()
        saved['tasks'] = [next(t for t in saved['tasks'] if t['source'] == 'indeed')]
        with patch.object(discovery.time, 'time', return_value=datetime.now(UTC).timestamp()) as clock:
            discovery.next_requests(saved)
            self.assertEqual(discovery.next_requests(saved), [])
            task = saved['tasks'][0]
            self.assertEqual(task['phase'], 'search')
            clock.return_value += 4
            self.assertEqual(len(discovery.next_requests(saved)), 1)
            task['attempts'] = 3
            discovery.next_requests(saved)
            self.assertEqual(task['phase'], 'failed')

    def test_transport_outcomes_control_retry_without_paid_resubmission(self):
        for outcome, phase in [('not_submitted', 'search'), ('submission_unknown', 'blocked'), ('confirmed_run', 'poll')]:
            with self.subTest(outcome=outcome):
                saved = state(); saved['tasks'] = [next(t for t in saved['tasks'] if t['source'] == 'linkedin')]
                request = discovery.next_requests(saved)[0]
                discovery.accept(saved, request['id'], {'isError': True, 'content': [{'type': 'text', 'text': 'transport failed'}],
                    'transportFailure': {'submission_outcome': outcome, 'run_id': 'known' if outcome == 'confirmed_run' else None}})
                self.assertEqual(saved['tasks'][0]['phase'], phase)
                if outcome == 'confirmed_run': self.assertEqual(saved['tasks'][0]['actor_run_id'], 'known')

    def test_cache_restart_distinguishes_not_submitted_and_unknown(self):
        from charge_contract_fixture import mock_charge_contracts
        cli = Path(discovery.__file__)
        for outcome in ('not_submitted', 'submission_unknown'):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as tmp:
                contracts = mock_charge_contracts(Path(tmp))
                def call(run, command):
                    args = [sys.executable, str(cli), command, '--run-id', run,
                            '--state-root', tmp, '--cache-root', tmp+'/cache',
                            '--charge-contracts', str(contracts), '--charge-limit-usd', '0.5']
                    if command == 'init':
                        args += ['--acquisition', '--platform', 'seek', '--title', 'AI Engineer',
                                 '--location', 'Melbourne', '--max-results', '10']
                    return subprocess.run(args, capture_output=True, text=True)
                self.assertEqual(call('original', 'init').returncode, 0)
                self.assertEqual(call('original', 'next').returncode, 0)
                checkpoint = Path(tmp)/'original/checkpoint.json'
                saved = json.loads(checkpoint.read_text())
                saved['tasks'][0].update(phase='failed' if outcome == 'not_submitted' else 'blocked',
                    inflight=None, submission_outcome=outcome, error='fixture failure')
                checkpoint.write_text(json.dumps(saved))
                restarted = call('restart', 'init')
                if outcome == 'not_submitted':
                    self.assertEqual(restarted.returncode, 0, restarted.stderr)
                    self.assertTrue(json.loads(restarted.stdout)['reused'])
                    self.assertEqual(json.loads(call('restart', 'next').stdout)['requests'], [])
                    self.assertEqual(json.loads(restarted.stdout)['status'], 'initialized')
                else:
                    self.assertNotEqual(restarted.returncode, 0)
                    self.assertIn('reconciliation/resume', restarted.stderr)

    def test_preflight_failure_never_reaches_post(self):
        with patch.object(transport, 'api') as api:
            with self.assertRaises(transport.SubmissionError) as error:
                transport.submit({'actor': transport.ACTORS['seek'], 'chargeContracts': '/missing-contract'})
            self.assertEqual(error.exception.outcome, 'not_submitted')
            api.assert_not_called()
