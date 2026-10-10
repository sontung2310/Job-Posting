"""Provider repair regressions: saved/local data only, no paid calls."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'.agents/skills/job-retrieval/scripts'))
sys.path.insert(0, str(ROOT/'scripts'))
import apify_transport as transport
import seek_details
import discovery

PRICING = {'startedAt': '2026-01-01T00:00:00Z', 'pricingModel': 'PAY_PER_EVENT',
           'pricingPerEvent': {'actorChargeEvents': {
               'result': {'eventPriceUsd': .0025},
               'salary-finder': {'eventPriceUsd': .003}}}}

class Repairs(unittest.TestCase):
    def test_api_cap_is_query_parameter_and_timeout_is_never_retried(self):
        actor = {'id': 'actor', 'pricingInfos': [PRICING]}
        run = {'actId': 'actor', 'platformUsageBillingModel': 'DEVELOPER'}
        with patch.object(transport, 'api', side_effect=[actor, run]):
            contract = transport.inspect_contract('seek', 'billing-proof')
        self.assertEqual(contract['result_usd'], '0.0055')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'contract.json'; path.write_text(json.dumps({'seek': contract}))
            args = {'actor': transport.ACTORS['seek'], 'input': {'maxResults': 1, 'findSalaries': False},
                    'chargeContracts': str(path), 'maxTotalChargeUsd': '.0055'}
            posted = []
            def api(path, payload=None):
                if payload is None: return actor if path.startswith('acts/') else run
                posted.append((path, payload)); raise ValueError('unknown submission')
            with patch.object(transport, 'api', side_effect=api):
                with self.assertRaisesRegex(transport.SubmissionError, 'unknown submission') as failure: transport.submit(args)
            self.assertEqual(failure.exception.outcome, 'submission_unknown')
            self.assertEqual(len(posted), 1)
            query = parse_qs(urlsplit(posted[0][0]).query)
            self.assertEqual(query['maxTotalChargeUsd'], ['0.0055'])
            self.assertEqual(query['memory'], ['512'])
            self.assertNotIn('maxTotalChargeUsd', posted[0][1])
            contract['pricing_snapshot'] = json.loads(json.dumps(contract['pricing_snapshot']))
            contract['pricing_snapshot']['startedAt'] = '2025-01-01T00:00:00Z'
            path.write_text(json.dumps({'seek': contract}))
            with patch.object(transport, 'api', side_effect=api):
                with self.assertRaisesRegex(transport.SubmissionError, 'pricing changed') as failure: transport.submit(args)
            self.assertEqual(failure.exception.outcome, 'not_submitted')
            self.assertEqual(len(posted), 1)

    def test_discovery_cli_routes_reserved_cap_to_rest_transport(self):
        import subprocess
        actor = {'id': 'actor', 'pricingInfos': [PRICING]}
        with patch.object(transport, 'api', side_effect=[actor, {'actId': 'actor', 'platformUsageBillingModel': 'DEVELOPER'}]):
            contract = transport.inspect_contract('seek', 'billing-proof')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'contracts.json'; path.write_text(json.dumps({'seek': contract}))
            base = [sys.executable, str(ROOT/'.agents/skills/job-retrieval/scripts/discovery.py'),
                    '--run-id', 'fixture', '--state-root', directory, '--cache-root', directory+'/cache']
            result = subprocess.run(base+['init', '--acquisition', '--platform', 'seek', '--title', 'AI Engineer',
                '--location', 'Melbourne', '--max-results', '1', '--charge-contracts', str(path),
                '--charge-limit-usd', '0.0055'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run(base+['next'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            request = json.loads(result.stdout)['requests'][0]
            self.assertEqual(request['tool'], 'local_apify')
            self.assertEqual(request['args']['maxTotalChargeUsd'], .0055)
            self.assertEqual(request['args']['chargeContracts'], str(path.resolve()))
            self.assertNotIn('maxTotalChargeUsd', request['args']['input'])
            self.assertFalse(request['args']['input']['findSalaries'])

    def test_separate_compute_charges_block_contract(self):
        with patch.object(transport, 'api', side_effect=[{'id': 'actor', 'pricingInfos': [PRICING]},
                  {'actId': 'actor', 'platformUsageBillingModel': 'USER'}]):
            with self.assertRaisesRegex(ValueError, 'platform usage'): transport.inspect_contract('seek', 'run')

    def test_seek_detail_extracts_jobposting_and_rejects_other_urls(self):
        url = 'https://www.seek.com.au/job/123'
        html = '<script type="application/ld+json">'+json.dumps({'@type': 'JobPosting', 'url': url, 'description': '<p>Build Python services.</p>'})+'</script>'
        self.assertEqual(seek_details.extract(html, url)['description_html'], '<p>Build Python services.</p>')
        with self.assertRaises(ValueError): seek_details.extract(html, 'https://www.seek.com.au/job/999')
        from urllib.request import Request
        with self.assertRaisesRegex(ValueError, 'different job'):
            seek_details.SafeRedirect().redirect_request(Request(url), None, 302, 'redirect', {}, 'https://www.seek.com.au/job/999')
        for bad in ['https://example.test/job/123', 'http://www.seek.com.au/job/123', 'https://www.seek.com.au:444/job/123', 'https://www.seek.com.au/job/123/extra', 'https://user@www.seek.com.au/job/123']:
            with self.subTest(url=bad), self.assertRaises(ValueError): seek_details.validate_url(bad)

    def test_seek_old_missing_description_is_not_fetched(self):
        from datetime import UTC, datetime, timedelta
        now = datetime.now(UTC)
        state = {'started_epoch': now.timestamp(), 'lookback_hours': 24,
                 'window_start': (now-timedelta(hours=24)).isoformat(), 'window_end': now.isoformat()}
        task = {'source': 'seek', 'actor': 'bovi/seek-jobs-scraper', 'jobs': [
            {'job_id': '1', 'url': 'https://www.seek.com.au/job/1', 'listing_date': (now-timedelta(days=5)).isoformat()},
            {'job_id': '2', 'url': 'https://www.seek.com.au/job/2', 'listing_date': (now-timedelta(hours=1)).isoformat()}]}
        discovery.schedule_details(state, task)
        self.assertEqual(task['phase'], 'details'); self.assertEqual(task['detail_index'], 1)
        task['inflight'] = {'id': 'detail', 'started': now.timestamp()}; task['key'] = 'seek'; task['attempts'] = 1
        state.update(tasks=[task], accepted=[], events=[])
        discovery.accept(state, 'detail', {'structuredContent': {'url': 'https://www.seek.com.au/job/2', 'error': 'blocked'}})
        self.assertEqual(task['phase'], 'inspect_details')
        task['inflight'] = {'id': 'inspection', 'started': now.timestamp()}
        discovery.accept(state, 'inspection', {'structuredContent': {'url': 'https://www.seek.com.au/job/2', 'description_html': '<p>Python</p>'}})
        self.assertEqual(task['phase'], 'done')
        self.assertEqual(discovery.normalize('seek', task['jobs'][1])['description_text'], 'Python')

if __name__ == '__main__': unittest.main()
