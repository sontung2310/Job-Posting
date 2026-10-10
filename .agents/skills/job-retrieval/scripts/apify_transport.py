#!/usr/bin/env python3
"""Apify REST transport: one submission, with a provider-enforced USD cap."""
import argparse
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT/'scripts'))
from private_io import write_private_json

ACTORS = {'seek': 'websift/seek-job-scraper', 'linkedin': 'valig/linkedin-jobs-scraper'}
CAP_DESCRIPTION = 'Apify REST run query maxTotalChargeUsd limits total pay-per-event charges.'
DOC = 'https://docs.apify.com/api/v2/actors-runs-post'


def token():
    value = os.environ.get('APIFY_TOKEN')
    if not value:
        for line in (ROOT/'.env').read_text().splitlines():
            key, sep, raw = line.strip().partition('=')
            if sep and key.strip().removeprefix('export ') == 'APIFY_TOKEN':
                value = raw.strip().strip('"\'')
                break
    if not value:
        raise ValueError('APIFY_TOKEN unavailable')
    return value


def api(path, payload=None):
    request = Request('https://api.apify.com/v2/'+path,
                      data=json.dumps(payload).encode() if payload is not None else None,
                      headers={'Authorization': 'Bearer '+token(), 'Content-Type': 'application/json'})
    # Never retry submissions: a timeout may still have created a billable run.
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)['data']
    except Exception as error:
        raise ValueError('Apify request failed; reconcile any submitted run before retrying ('+type(error).__name__+')') from None


def prices(actor):
    data = api('acts/'+actor.replace('/', '~'))
    now = datetime.now(UTC)
    choices = [p for p in data.get('pricingInfos', [])
               if datetime.fromisoformat(p['startedAt'].replace('Z', '+00:00')) <= now]
    if not choices:
        raise ValueError('Actor pricing unavailable')
    pricing = max(choices, key=lambda p: p['startedAt'])
    if pricing.get('pricingModel') != 'PAY_PER_EVENT':
        raise ValueError('Only inspected pay-per-event actors are supported')
    rates = {}
    for name, event in pricing['pricingPerEvent']['actorChargeEvents'].items():
        tiers = event.get('eventTieredPricingUsd', {})
        values = [Decimal(str(t['tieredEventPriceUsd'])) for t in tiers.values()]
        if 'eventPriceUsd' in event:
            values.append(Decimal(str(event['eventPriceUsd'])))
        if not values:
            raise ValueError('Unverified event price: '+name)
        rates[name] = max(values)
    expected = ({'result', 'salary-finder'} if actor == ACTORS['seek']
                else {'apify-default-dataset-item', 'apify-actor-start'})
    if set(rates) != expected or any(not v.is_finite() or v < 0 for v in rates.values()):
        raise ValueError('Actor charge events changed; inspect before submission')
    return data, pricing, rates


def inspect_contract(source, run_id, actor_version=None):
    actor = ACTORS[source]
    data, pricing, rates = prices(actor)
    run = api('actor-runs/'+run_id)
    if run.get('actId') != data['id'] or run.get('platformUsageBillingModel') != 'DEVELOPER':
        raise ValueError('Cannot prove platform usage is included in actor charges')
    # Reserve every possible result event, including Seek salary disclosure.
    rate = sum(v for k, v in rates.items() if k != 'apify-actor-start')
    start = rates.get('apify-actor-start', Decimal(0))
    now = datetime.now(UTC)
    return {'actor': actor, 'actor_version': actor_version, 'tool': 'local_apify', 'transport': 'apify-api',
            'currency': 'USD', 'enforcement': 'provider_total_charge_usd', 'optional_events': [],
            'result_usd': str(rate), 'start_usd': str(start), 'inspected_at': now.isoformat(),
            'expires_at': (now+timedelta(hours=24)).isoformat(), 'pricing_snapshot': pricing,
            'billing_run_id': run_id, 'pricing_evidence': 'Apify actor pricingInfos and billing run '+run_id,
            'enforcement_evidence': DOC, 'schema_evidence': DOC+'#query-parameters',
            'charge_cap_argument': 'maxTotalChargeUsd', 'cap_description': CAP_DESCRIPTION,
            'connector_input_schema': {'properties': {'maxTotalChargeUsd': {'type': 'number', 'description': CAP_DESCRIPTION}}}}


class SubmissionError(ValueError):
    def __init__(self, message, outcome, run_id=None):
        super().__init__(message)
        self.outcome = outcome
        self.run_id = run_id


def submit(args):
    progress = {"outcome": "not_submitted", "run_id": None}
    try:
        return _submit(args, progress)
    except (ValueError, KeyError, OSError, TypeError) as error:
        raise SubmissionError(str(error), progress["outcome"], progress["run_id"]) from None


def _submit(args, progress):
    from charge_contract import checked_contract
    actor = args['actor']
    source = next((key for key, value in ACTORS.items() if value == actor), None)
    if not source:
        raise ValueError('Unsupported actor')
    contracts = json.loads(Path(args['chargeContracts']).read_text())
    contract = checked_contract(contracts, source, actor, 'local_apify')
    # Recheck pricing and billing evidence immediately before the one POST.
    current = inspect_contract(source, contract['billing_run_id'], contract.get('actor_version'))
    if current['pricing_snapshot'] != contract['pricing_snapshot']:
        raise ValueError('Actor pricing changed; refresh charge contracts')
    ceiling = Decimal(str(args['maxTotalChargeUsd']))
    if not ceiling.is_finite() or ceiling <= 0:
        raise ValueError('Positive finite charge cap required')
    query = urlencode({'maxTotalChargeUsd': str(ceiling), 'memory': 512, 'timeout': 300})
    version = contract.get('actor_version')
    if version:
        query += '&'+urlencode({'build': version})
    # Resolve credentials before marking the POST as potentially submitted.
    token()
    progress['outcome'] = 'submission_unknown'
    run = api('acts/'+actor.replace('/', '~')+'/runs?'+query, args['input'])
    if isinstance(run.get('id'), str) and run['id'].strip():
        progress.update(outcome='confirmed_run', run_id=run['id'])
    return {'structuredContent': {'runId': run['id'], 'status': run['status'],
            'storages': {'datasets': {'default': {'id': run['defaultDatasetId']}}}}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['inspect', 'submit'])
    parser.add_argument('--seek-run')
    parser.add_argument('--linkedin-run')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--config', type=Path, default=ROOT/'config/search_targets.yaml')
    args = parser.parse_args()
    if args.command == 'submit':
        print(json.dumps(submit(json.load(sys.stdin))))
    else:
        import yaml
        config = yaml.safe_load(args.config.read_text())
        previous = json.loads(args.output.read_text()) if args.output and args.output.exists() else {}
        args.seek_run = args.seek_run or previous.get('seek', {}).get('billing_run_id')
        args.linkedin_run = args.linkedin_run or previous.get('linkedin', {}).get('billing_run_id')
        contracts = {source: inspect_contract(source, run, config['sources'][source].get('actor_version'))
                     for source, run in [('seek', args.seek_run), ('linkedin', args.linkedin_run)] if run}
        if not contracts or not args.output:
            raise ValueError('Provide billing run evidence and a private output path')
        write_private_json(args.output, contracts)
        print(json.dumps({'charge_contracts': str(args.output.resolve()), 'sources': list(contracts)}))

if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError, TypeError) as error:
        failure = {'error': str(error)}
        if isinstance(error, SubmissionError):
            failure.update(submission_outcome=error.outcome, run_id=error.run_id)
        print(json.dumps(failure), file=sys.stderr)
        sys.exit(1)
