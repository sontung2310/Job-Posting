#!/usr/bin/env python3
"""Checkpointed discovery. Python owns state; discovery_bridge.js invokes Codex tools."""
from __future__ import annotations
from pathlib import Path
import sys
WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(WORKSPACE_ROOT / "scripts"))

import argparse
import fcntl
import hashlib
import json
import math
import os
import re
import sys
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import yaml
from paid_operations import exclusive_lock
import pipeline_log as log
from job_sources import canonical_url, compact_text, strip_html

ROOT = WORKSPACE_ROOT
TOOLS = {
    'indeed': 'mcp__codex_apps__indeed_job_search_search_jobs',
    'linkedin': 'mcp__apify__valig__linkedin_jobs_scraper',
    'seek': 'mcp__apify__websift__seek_job_scraper',
}
PAGE_TOOL = 'mcp__apify__get_dataset_items'
POLL_TOOL = 'mcp__apify__get_actor_run'
FIELDS = {
    'linkedin': 'id,link,title,companyName,location,postedAt,salary,descriptionText,descriptionHtml,companyWebsite',
    'seek': 'id,jobLink,title,salary,listedAt,content.unEditedContent,content.sections,joblocationInfo.displayLocation,emails,companyProfile.name,companyProfile.website,advertiser.name',
}


ACTOR_TOOLS = {
    'valig/linkedin-jobs-scraper': TOOLS['linkedin'],
    'bovi/seek-jobs-scraper': 'mcp__apify__bovi__seek_jobs_scraper',
    'curious_coder/linkedin-jobs-scraper': 'mcp__apify__curious_coder__linkedin_jobs_scraper',
    'websift/seek-job-scraper': 'mcp__apify__websift__seek_job_scraper',
}
ACTOR_FIELDS = {
    'valig/linkedin-jobs-scraper': 'id,url,title,companyName,location,postedDate,postedTimeAgo,salary,description,descriptionHtml',
    'bovi/seek-jobs-scraper': 'job_id,url,title,company,location,listing_date,salary,description_text,description_html',
}


def task_actor(task):
    # Historical checkpoints keep their original actor and input contract.
    return task.get('actor') or {'linkedin': 'curious_coder/linkedin-jobs-scraper', 'seek': 'websift/seek-job-scraper'}.get(task['source'])


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    with temporary.open('w', encoding='utf-8') as handle:
        os.chmod(temporary, 0o600)
        json.dump(value, handle, ensure_ascii=False)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def resolve_lookback(config, override=None):
    value = override if override is not None else config.get('lookback_hours', 24)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError('lookback_hours must be a positive integer')
    return value


def window(state):
    started = datetime.fromtimestamp(state['started_epoch'], UTC)
    if ('window_start' in state) != ('window_end' in state):
        raise ValueError('Ambiguous checkpoint window: both exact endpoints are required')
    if 'window_start' in state and 'window_end' in state:
        try:
            lower = datetime.fromisoformat(state['window_start'])
            upper = datetime.fromisoformat(state['window_end'])
            hours = (upper - lower).total_seconds() / 3600
            if lower.tzinfo is None or upper.tzinfo is None or upper != started or hours <= 0 or not hours.is_integer():
                raise ValueError()
            if 'lookback_hours' in state and resolve_lookback({}, state['lookback_hours']) != hours:
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError('Ambiguous checkpoint window: explicit recovery or a new run is required')
        return int(hours), lower, upper
    # The former checkpoint format proves 24 hours through its saved provider filters.
    tasks = state.get('tasks', [])
    proven = tasks and all(
        t['source'] == 'indeed' or
        (t['source'] == 'linkedin' and t.get('args', {}).get('urls') and all(dict(parse_qsl(urlsplit(url).query)).get('f_TPR') == 'r86400' for url in t['args']['urls'])) or
        (t['source'] == 'seek' and t.get('args', {}).get('dateRange') == 1)
        for t in tasks)
    if 'lookback_hours' in state or not proven:
        raise ValueError('Ambiguous legacy checkpoint window: explicit recovery or a new run is required')
    return 24, started - timedelta(hours=24), started


def plan(config, smoke=False, cap=None, platform=None, title=None, location=None, lookback_hours=None, acquisition=False):
    if not smoke and not acquisition and any(x is not None for x in (platform, title, location)):
        raise ValueError("Platform/title/location selectors require --smoke")
    selected_title, selected_location = title, location
    hours = resolve_lookback(config, lookback_hours)
    pairs = {}
    for target in config['searches']:
        locations = target['location']
        for location in locations if isinstance(locations, list) else [locations]:
            title = target['title'].strip()
            location = location.strip()
            pairs.setdefault((title.casefold(), location.casefold()), (title, location))
    sources = [source for source, settings in config['sources'].items() if settings.get('enabled')]
    if smoke or acquisition:
        pairs = {key: pair for key, pair in pairs.items() if (selected_title is None or pair[0].casefold() == selected_title.casefold()) and (selected_location is None or pair[1].casefold() == selected_location.casefold())}
        if not pairs or not sources or (platform is not None and platform not in sources):
            raise ValueError('Smoke selection must match one enabled configured search')
        pairs = dict(list(pairs.items())[:1])
        sources = [platform or sources[0]]
    tasks = []
    maximum = config['max_results_per_search_per_source'] if cap is None else min(cap, config['max_results_per_search_per_source'])
    if type(maximum) is not int or maximum < 1:
        raise ValueError('Result cap must be positive')
    if smoke:
        maximum = min(maximum, 3)
    for title, location in pairs.values():
        for source, settings in config['sources'].items():
            if source not in sources:
                continue
            if source not in TOOLS:
                raise ValueError(f'Unsupported source: {source}')
            if source == 'indeed':
                args = {'country_code': 'AU', 'location': location, 'search': title, 'radius': 25}
            elif source == 'linkedin':
                if settings['actor'] not in ('curious_coder/linkedin-jobs-scraper', 'valig/linkedin-jobs-scraper'):
                    raise ValueError('Unexpected LinkedIn actor')
                args = {'urls': ['https://www.linkedin.com/jobs/search/?' + urlencode({'keywords': title, 'location': location + ', Australia', 'f_TPR': f'r{hours * 3600}'})], 'limitPerSource': maximum, 'waitSecs': 5, 'scrapeCompany': False}
                if settings['actor'] == 'valig/linkedin-jobs-scraper':
                    args = {'keywords': title, 'location': location + ', Australia', 'datePosted': 'r86400' if hours <= 24 else 'r604800' if hours <= 168 else 'r2592000' if hours <= 720 else '', 'limit': min(maximum, 1000)}
            else:
                if settings['actor'] not in ('websift/seek-job-scraper', 'bovi/seek-jobs-scraper'):
                    raise ValueError('Unexpected Seek actor')
                args = {'searchTerm': title, 'location': location, 'dateRange': min(365, math.ceil(hours / 24)), 'sortBy': 'ListedDate', 'maxResults': maximum}
                if acquisition:
                    args['findSalaries'] = False
                if settings['actor'] == 'bovi/seek-jobs-scraper':
                    args = {'searchQueries': [title], 'where': location, 'siteKey': 'AU-Main', 'maxItems': maximum, 'includeDescriptions': False, 'disableUsageStats': True}
            key = hashlib.sha256(f'{source}|{title.casefold()}|{location.casefold()}'.encode()).hexdigest()[:16]
            tasks.append({'key': key, 'source': source, 'title': title, 'location': location, 'actor': settings.get('actor'), 'args': args, 'cap': min(maximum, 1000) if settings.get('actor') == 'valig/linkedin-jobs-scraper' else maximum, 'phase': 'search', 'attempts': 0, 'offset': 0, 'jobs': [], 'inflight': None})
    return tasks


def unpack(response):
    if response.get('isError'):
        text = ' '.join(x.get('text', '') for x in response.get('content', []))
        raise ValueError(text or 'MCP tool failed')
    data = response.get('structuredContent')
    if isinstance(data, dict):
        return data
    for block in response.get('content', []):
        try:
            data = json.loads(block.get('text', ''))
            if isinstance(data, dict):
                return data
        except (ValueError, TypeError):
            pass
    raise ValueError('Tool returned no structured JSON result')


def confirmed_rejection(message):
    return 'platform-feature-disabled' in message.lower() or 'monthly usage hard limit exceeded' in message.lower()


def rolling_window(state):
    return state.get('acquisition') or state.get('window_policy') == 'submission-relative-v1'


def next_requests(state, limit=3):
    if state.get('smoke_test') and (len(state['tasks']) != 1 or state['tasks'][0]['cap'] > 3):
        raise ValueError('Unsafe legacy smoke checkpoint: reconcile saved runs without starting another search')
    hours, lower, upper = window(state)
    state.update(lookback_hours=hours, window_start=lower.isoformat(), window_end=upper.isoformat())
    requests = []
    now = time.time()
    deadline = state.setdefault('supervision_deadline', state['started_epoch'] + 30 * 60)
    active = any(task['phase'] not in ('done', 'failed', 'blocked') for task in state['tasks'])
    if state.get('supervision_paused') or (active and now >= deadline):
        state['supervision_paused'] = True
        return []
    for task in state['tasks']:
        if task['phase'] == 'blocked' and confirmed_rejection(task.get('error', '')):
            task.update(phase='failed', error_type='ProviderUsageLimit')
        if task['phase'] == 'blocked' and task['source'] == 'indeed' and task.get('error', '').startswith('Search submission interrupted;'):
            task.update(phase='search' if task['attempts'] < 3 else 'failed', inflight=None, next_after=now + 2, error_type='ReadRetryLimit')
        phase = task['phase']
        if phase in ('done', 'failed', 'blocked'):
            continue
        if task['inflight']:
            # Reads can be repeated after an interruption; paid submissions cannot.
            if phase == 'search' and task['source'] != 'indeed':
                task.update(phase='blocked', error='Search submission interrupted; attach its known Actor run ID. Never automatically relaunch.')
                continue
            if phase == 'search':
                task['inflight'] = None
                if task['attempts'] >= 3:
                    task.update(phase='failed', error_type='ReadRetryLimit', error='Interrupted Indeed request reached retry limit')
                    continue
                task['next_after'] = max(task.get('next_after', 0), now + 2)
        if task.get('next_after', 0) > now:
            continue
        if phase == 'search':
            if task['source'] == 'indeed' and state.get('indeed_next_after', 0) > now:
                continue
            # Rolling provider filters must also cover queue/resume delay.
            if rolling_window(state):
                upper = datetime.fromtimestamp(now, UTC)
                lower = upper - timedelta(hours=hours)
                task.update(window_start=lower.isoformat(), window_end=upper.isoformat(), observed_epoch=now)
            age_seconds = hours * 3600 if rolling_window(state) else max(hours * 3600, math.ceil(now - lower.timestamp()))
            actor = task_actor(task)
            if actor == 'bovi/seek-jobs-scraper':
                task['source_filter'] = {'date_filter': 'unfiltered'}
                task['source_limitation'] = 'actor_has_no_date_filter'
            elif actor == 'valig/linkedin-jobs-scraper':
                preset = 'r86400' if age_seconds <= 86400 else 'r604800' if age_seconds <= 604800 else 'r2592000' if age_seconds <= 2592000 else ''
                task['args']['datePosted'] = preset
                task['source_filter'] = {'datePosted': preset}
                if not preset or age_seconds != int(preset[1:]):
                    task['source_limitation'] = 'coarse_covering_date_filter'
            elif task['source'] == 'seek':
                days = math.ceil(age_seconds / 86400)
                if days > 365:
                    task.update(phase='failed', error_type='UnsupportedWindow', error='Seek supports at most 365 days; cannot cover the saved window', source_limitation='requested_window_exceeds_supported_filter')
                    continue
                task['args']['dateRange'] = days
                task['source_filter'] = {'dateRange': days}
            elif task['source'] == 'linkedin':
                parts = urlsplit(task['args']['urls'][0])
                query = dict(parse_qsl(parts.query))
                query['f_TPR'] = f'r{age_seconds}'
                task['args']['urls'] = [urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))]
                task['source_filter'] = {'f_TPR': query['f_TPR']}
            else:
                task['source_filter'] = {'date_filter': 'unfiltered'}
            if rolling_window(state) and actor == 'curious_coder/linkedin-jobs-scraper' and hours != 24:
                task['source_limitation'] = 'non_24_hour_filter_not_verified'
            tool, args = ACTOR_TOOLS[actor] if actor else TOOLS[task['source']], task['args']
            if state.get('acquisition') and task['source']!='indeed':
                from charge_contract import checked_contract,cap_arguments
                contract=checked_contract(state.get('charge_contracts',{}),task['source'],actor,tool)
                if contract.get('transport') == 'apify-api':
                    tool = 'local_apify'
                    args = {'actor': actor, 'input': dict(args), 'chargeContracts': state['charge_contracts_path']}
                args=cap_arguments(args,contract,state.get('charge_limit_usd'))
            task.pop('submission_outcome', None)
            task['attempts'] += 1
            if task['source'] == 'indeed':
                state['indeed_next_after'] = now + 3
        elif phase in ('details', 'inspect_details'):
            index = task['detail_index']
            tool, args = ('inspect_seek_description' if phase == 'inspect_details' else 'local_seek_detail'), {'url': normalize('seek', task['jobs'][index])['job_url']}
        elif phase == 'poll':
            if not task.get('actor_run_id'):
                raise ValueError('Cannot poll an empty Actor run ID')
            tool, args = POLL_TOOL, {'runId': task['actor_run_id'], 'waitSecs': 30}
        else:
            tool, args = PAGE_TOOL, {'datasetId': task['dataset_id'], 'offset': task['offset'], 'limit': min(20, task['cap'] - task['offset']), 'clean': False, 'fields': ACTOR_FIELDS.get(task_actor(task), FIELDS[task['source']])}
        task["request_sequence"] = task.get("request_sequence", 0) + 1
        identifier = f"{task['key']}:{phase}:{task['offset']}:{task['request_sequence']}"
        task['inflight'] = {'id': identifier, 'started': now}
        requests.append({'id': identifier, 'tool': tool, 'args': args})
        if len(requests) >= limit:
            break
    return requests


def schedule_details(state, task):
    task['phase'] = 'done'
    if task_actor(task) != 'bovi/seek-jobs-scraper':
        return
    _, lower, upper = window(state)
    for index, row in enumerate(task['jobs']):
        job = normalize('seek', row)
        status, _ = acquisition_freshness(job['posted_at'], task, lower, upper)
        if job['description_text'] or row.get('description_inspected') or status not in ('confirmed', 'uncertain'):
            continue
        from seek_details import validate_url
        try:
            validate_url(job['job_url'])
        except ValueError:
            row['description_inspected'] = True
            row['description_error'] = 'Invalid Seek detail URL'
            continue
        task.update(phase='details', detail_index=index)
        break


def accept(state, identifier, response):
    task = next((t for t in state['tasks'] if t['inflight'] and t['inflight']['id'] == identifier), None)
    if task is None:
        if identifier in state['accepted']:
            return {'status': 'already_saved'}
        raise ValueError('Response does not match a pending request')
    elapsed = time.time() - task['inflight']['started']
    phase = task['phase']
    try:
        data = unpack(response)
        if phase == 'search' and task['source'] == 'indeed':
            if not isinstance(data.get('jobs'), list):
                raise ValueError('Indeed response missing jobs list')
            task['jobs'] = data['jobs'][:task['cap']]
            task['result_cap_reached'] = len(data['jobs']) >= task['cap'] or data.get('totalAvailable', 0) > len(data['jobs'])
            task['phase'] = 'done'
        elif phase in ('search', 'poll'):
            run_id = data.get('runId')
            if not isinstance(run_id, str) or not run_id.strip():
                raise ValueError('Actor response missing runId; do not restart paid search')
            if task.get('actor_run_id') and task['actor_run_id'] != run_id:
                raise ValueError('Actor run ID changed')
            task['actor_run_id'] = run_id
            dataset = data.get('storages', {}).get('datasets', {}).get('default', {})
            if dataset.get('id'):
                task['dataset_id'] = dataset['id']
            status = data.get('status')
            if status == 'SUCCEEDED':
                if not task.get('dataset_id'):
                    raise ValueError('Succeeded Actor missing dataset ID')
                task['phase'] = 'done' if dataset.get('itemCount') == 0 else 'page'
                task['result_cap_reached'] = dataset.get('itemCount', 0) >= task['cap']
            elif status in ('READY', 'RUNNING', 'TIMING-OUT'):
                task['phase'] = 'poll'
            elif status in ('FAILED', 'ABORTED', 'TIMED-OUT'):
                task.update(phase='failed', error=f'Actor ended as {status}; no automatic paid restart')
            else:
                raise ValueError('Unknown Actor status')
        elif phase in ('details', 'inspect_details'):
            row = task['jobs'][task['detail_index']]
            url = normalize('seek', row)['job_url']
            if data.get('url') != url:
                raise ValueError('Description response does not match the saved job URL')
            if data.get('description_html'):
                if not isinstance(data['description_html'], str):
                    raise ValueError('Description must contain source text')
                row.update(description_html=data['description_html'], description_source_url=url)
            else:
                row['description_error'] = data.get('error', 'Description unavailable')
            if phase == 'details' and not data.get('description_html'):
                task['phase'] = 'inspect_details'
            else:
                row['description_inspected'] = True
                schedule_details(state, task)
        else:
            items = data.get('items')
            total = data.get('totalItemCount')
            if not isinstance(items, list) or not isinstance(total, int) or total < 0:
                raise ValueError('Dataset response missing items or totalItemCount')
            if data.get('datasetId') != task['dataset_id'] or data.get('offset') != task['offset']:
                raise ValueError('Dataset page does not match the saved request')
            if len(items) > min(20, task['cap'] - task['offset']):
                raise ValueError('Dataset page exceeded the saved result cap')
            if not items and task['offset'] < min(total, task['cap']):
                raise ValueError('Unexpected empty dataset page')
            task['jobs'].extend(items)
            task['offset'] += len(items)
            if task['offset'] >= min(total, task['cap']):
                schedule_details(state, task)
    except ValueError as error:
        message = str(error)
        # Only a confirmed rate-limit rejection is safe to retry a submission.
        failure = response.get('transportFailure', {}) if isinstance(response, dict) else {}
        outcome = failure.get('submission_outcome')
        if phase == 'search' and outcome == 'confirmed_run' and failure.get('run_id'):
            task.update(phase='poll', actor_run_id=failure['run_id'], error=message)
        elif phase == 'search' and outcome == 'not_submitted':
            task['submission_outcome'] = outcome
            if task['attempts'] < 3:
                task.update(next_after=time.time() + 2, error=message)
            else:
                task.update(phase='failed', error=message, error_type='PreSubmissionFailure')
        elif confirmed_rejection(message):
            task.update(phase='failed', error=message)
        elif phase == 'search' and state.get('smoke_test'):
            task.update(phase='blocked', error=message + '; smoke submission cannot be repeated')
        elif 'rate limit' in message.lower() and task['attempts'] < 3 and (phase != 'search' or task['source'] == 'indeed'):
            match = re.search(r'(?:in|after)\s+(\d+)\s+seconds', message, re.I)
            task['next_after'] = time.time() + max(60, int(match.group(1)) if match else 60)
            if task['source'] == 'indeed':
                state['indeed_next_after'] = task['next_after']
        elif phase != 'search' and task.get('read_failures', 0) < 2:
            task['read_failures'] = task.get('read_failures', 0) + 1
            task['next_after'] = time.time() + 2
        else:
            task.update(phase='blocked' if phase == 'search' and task['source'] != 'indeed' else 'failed', error=message)
        task['error_type'] = ('PreSubmissionFailure' if outcome == 'not_submitted' else
                              'ProviderUsageLimit' if confirmed_rejection(message) else 'ToolResponseError')
    task['inflight'] = None
    state['accepted'].append(identifier)
    state['events'].append({'request_id': identifier, 'search_id': task['key'], 'platform': task['source'], 'operation': phase, 'elapsed_seconds': elapsed, 'status': task['phase'], 'recorded_at': log.utc_now()})
    return {'search_id': task['key'], 'platform': task['source'], 'phase': task['phase'], 'rows_saved': len(task['jobs']), 'elapsed_seconds': round(elapsed, 3)}


def value(row, key):
    if key in row:
        return row[key]
    current = row
    for part in key.split('.'):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def normalize(source, row):
    if source == 'linkedin':
        fields = ('link', 'companyName', 'title', 'location', 'postedAt', 'descriptionText')
        url, company, title, location, posted, description = [row.get(x) for x in fields]
        url = url or row.get('url')
        posted = posted or row.get('postedDate')
        description = description or row.get('description') or row.get('descriptionHtml')
        website = row.get('companyWebsite')
    elif source == 'seek':
        url, title, posted = row.get('jobLink') or row.get('url'), row.get('title'), row.get('listedAt') or row.get('listing_date')
        company = value(row, 'advertiser.name') or value(row, 'companyProfile.name') or row.get('company')
        location = value(row, 'joblocationInfo.displayLocation') or row.get('location')
        description = row.get('description_text') or row.get('description_html') or value(row, 'content.unEditedContent') or ' '.join(value(row, 'content.sections') or [])
        website = value(row, 'companyProfile.website')
    else:
        url, company, title, location = row.get('url'), row.get('company'), row.get('title'), row.get('location')
        posted = row.get('datePosted') or row.get('datePublished') or row.get('postedAt') or row.get('posted_date')
        description = row.get('description') or row.get('descriptionText')
        website = row.get('companyWebsite')
    url = canonical_url(url)
    parts = urlsplit(url)
    if parts.scheme not in ('https', 'http') or not parts.netloc:
        url = ''
    if url and ((source == 'linkedin' and ((parts.hostname or '') == 'linkedin.com' or (parts.hostname or '').endswith('.linkedin.com'))) or (source == 'seek' and re.fullmatch(r'(?:www\.|au\.)?seek\.com(?:\.au)?', parts.hostname or ''))):
        # These source paths identify jobs; tracking query strings are unnecessary.
        host = 'www.seek.com.au' if source == 'seek' else 'www.linkedin.com'
        url = urlunsplit(('https', host, parts.path.rstrip('/'), '', ''))
    emails = row.get('emails') or re.findall(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', str(description or ''))
    email = next((e for e in emails if isinstance(e, str) and re.fullmatch(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', e)), None)
    return {'source': source.title() if source != 'linkedin' else 'LinkedIn', 'source_job_id': str(row.get('id') or row.get('job_id') or row.get('jobkey') or row.get('jrtk') or '') or None, 'job_url': url, 'company': compact_text(company), 'position': compact_text(title), 'location': compact_text(location), 'posted_at': posted, 'posted_age': row.get('postedTimeAgo'), 'salary': row.get('salary'), 'contact_email': email, 'company_website': website, 'description_text': strip_html(description)}


def fresh(posted, source, started, lookback_hours=24, window_start=None):
    raw = str(posted or '').strip()
    # Rolling source filters and relative/calendar-only labels cannot establish
    # the original fixed window after a delayed fetch or resumed Actor run.
    try:
        date = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        if date.tzinfo is None:
            return False
        return (window_start or started - timedelta(hours=lookback_hours)) <= date <= started
    except ValueError:
        return False


def acquisition_freshness(posted, task, session_lower, session_upper):
    """Unknown timezone calendar dates span all civil timezones; never invent midnight."""
    raw = str(posted or '').strip()
    requested_hours = (session_upper-session_lower).total_seconds()/3600
    filters = task.get('source_filter', {})
    provider = ((task['source'] == 'seek' and filters.get('dateRange') == math.ceil(requested_hours/24)) or
                (task['source'] == 'linkedin' and requested_hours == 24 and (filters.get('f_TPR') == 'r86400' or filters.get('datePosted') == 'r86400')))
    lower = datetime.fromisoformat(task.get('window_start', session_lower.isoformat()))
    upper = datetime.fromisoformat(task.get('window_end', session_upper.isoformat()))
    precision = 'unknown'
    interval = None
    try:
        parsed = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        if task_actor(task) == 'valig/linkedin-jobs-scraper':
            day = parsed.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=UTC)
            interval = (day-timedelta(hours=14), day+timedelta(days=1, hours=12))
            precision = 'calendar_unknown_timezone'
        elif parsed.tzinfo is not None:
            interval = (parsed, parsed)
            precision = 'exact'
        elif re.fullmatch(r'\d{4}-\d{2}-\d{2}', raw):
            day = parsed.replace(tzinfo=UTC)
            interval = (day-timedelta(hours=14), day+timedelta(days=1, hours=12))
            precision = 'calendar_unknown_timezone'
    except ValueError:
        for fmt in ('%B %d, %Y', '%b %d, %Y'):
            try:
                day = datetime.strptime(raw, fmt).replace(tzinfo=UTC)
                interval = (day-timedelta(hours=14), day+timedelta(days=1, hours=12))
                precision = 'calendar_unknown_timezone'
                break
            except ValueError:
                pass
    # Cached freshness must satisfy both historical acquisition and the new request.
    checks = [(lower, upper), (session_lower, session_upper)]
    if upper < session_lower or (interval and any(interval[1] < lo or interval[0] > hi for lo, hi in checks)):
        classification = 'outside'
    elif interval and all(lo <= interval[0] and interval[1] <= hi for lo, hi in checks):
        classification = 'confirmed'
    else:
        classification = 'uncertain' if provider and interval else 'unresolved'
    return classification, {'precision': precision, 'provider_filtered': provider,
        'source_filter': task.get('source_filter'), 'window_start': lower.isoformat(),
        'window_end': upper.isoformat(), 'possible_posting_interval': [x.isoformat() for x in interval] if interval else None}


def progress(state, directory):
    hours, lower, started = window(state)
    tasks = state['tasks']
    remaining = sum(t['phase'] not in ('done', 'failed', 'blocked') for t in tasks)
    blocked = sum(t['phase'] == 'blocked' for t in tasks)
    failures = [t['key'] for t in tasks if t['phase'] in ('failed', 'blocked')]
    now = time.time()
    wakeups = [t['next_after'] for t in tasks if t['phase'] not in ('done', 'failed', 'blocked') and t.get('next_after', 0) > now]
    if any(t['source'] == 'indeed' and t['phase'] == 'search' for t in tasks) and state.get('indeed_next_after', 0) > now:
        wakeups.append(state['indeed_next_after'])
    return {
        'acquisition': ({'source': tasks[0]['source'], 'title': tasks[0]['title'], 'location': tasks[0]['location'],
            'lookback_hours': hours, 'max_results': state.get('requested_cap', tasks[0]['cap']), 'original_cap': tasks[0]['cap'],
            'interval': [tasks[0].get('window_start'), tasks[0].get('window_end')], 'source_filter': tasks[0].get('source_filter'),
            'continuation': 'unsupported', 'reused': state.get('reused', False), 'actor_version': state.get('actor_version')}
            if state.get('acquisition') else None), 'reused': state.get('reused', False), 'continuation': 'unsupported' if state.get('acquisition') else None,
        'run_id': state['run_id'], 'checkpoint_path': str((directory/'checkpoint.json').resolve()),
        'jobs_path': str((directory/'jobs.json').resolve()), 'coverage_path': str((directory/'coverage.json').resolve()),
        'window_policy': state.get('window_policy', 'fixed-run-start-legacy'),
        'lookback_hours': hours, 'window_start': lower.isoformat(), 'window_end': started.isoformat(),
        'search_count': len(tasks), 'completed_searches': sum(t['phase'] == 'done' for t in tasks),
        'failed_search_ids': failures, 'remaining': remaining, 'blocked': blocked, 'terminal': remaining == 0 or state.get('supervision_paused', False),
        'supervision_paused': state.get('supervision_paused', False),
        'supervision_deadline': state.get('supervision_deadline', state['started_epoch'] + 30 * 60),
        'status': 'partial' if state.get('supervision_paused') else ('partial' if failures else 'completed') if not remaining else 'in_progress',
        'retry_after_seconds': max(1, int(min(wakeups, default=now+1)-now)+1),
        'searches': [{key: t.get(key) for key in ('key', 'source', 'actor', 'title', 'location', 'phase', 'cap', 'attempts', 'actor_run_id', 'dataset_id', 'result_cap_reached', 'source_filter', 'source_limitation', 'window_start', 'window_end', 'error_type')} for t in tasks],
    }


def finish(state, directory, log_root=ROOT/'logs', vault=ROOT/'career-vault'):
    if state.get('finished') and (directory/'summary.json').exists():
        summary = json.loads((directory/'summary.json').read_text())
        if not (directory/'coverage.json').exists():
            save(directory/'coverage.json', dict(progress(state, directory), retained_job_count=summary['retained_job_count'], capped_searches=summary.get('capped_searches', 0)))
        return summary
    active = [t for t in state['tasks'] if t['phase'] not in ('done', 'failed', 'blocked')]
    if active and not state.get('supervision_paused'):
        raise ValueError('Discovery still has unfinished requests')
    hours, lower, started = window(state)
    existing = []
    for folder in ('01 Active', '99 Archive'):
        existing.extend(p.read_text(encoding='utf-8') for p in (vault/'07 Applications'/folder).rglob('*.md'))
    date = log.local_run_date(state['started_epoch'])
    path = log.stage_path(log_root, date, 'discovery')
    history = [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []
    retained_history = {(row.get('platform'), row.get('job_id')) for row in history
                        if row.get('run_id') == state['run_id'] and row.get('record_type') == 'discovery_job' and row.get('outcome') == 'retain'}
    rows = {}
    for task in state['tasks']:
        for raw in task['jobs']:
            job = normalize(task['source'], raw)
            if rolling_window(state):
                current_lower = lower if state.get('reused') else datetime.fromisoformat(task.get('window_start', lower.isoformat()))
                current_upper = started if state.get('reused') else datetime.fromisoformat(task.get('window_end', started.isoformat()))
                job['freshness_class'], job['freshness_provenance'] = acquisition_freshness(job['posted_at'], task, current_lower, current_upper)
            identity = job['job_url'] or job['source_job_id'] or hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()
            key = (task['source'], identity)
            if key in rows:
                old = rows[key]
                winner, other = (job, old) if len(job['description_text']) > len(old['description_text']) else (old, job)
                for field in winner:
                    if not winner[field] and other.get(field):
                        winner[field] = other[field]
                rows[key] = winner
            else:
                rows[key] = job
    retained = []
    locations = {t['location'].casefold() for t in state['tasks']}
    seen_urls, seen_roles = {}, {}
    records = []
    reasons = {}
    for (source, identity), job in sorted(rows.items(), key=lambda x: ((x[0][0], hashlib.sha256(x[0][1].encode()).hexdigest()[:16]) not in retained_history, -len(x[1]['description_text']))):
        location = next((city for city in sorted(locations) if re.search(r'\b' + re.escape(city) + r'\b', job['location'].casefold())), job['location'].casefold())
        role = tuple(re.sub(r'\W+', ' ', text).strip() for text in (job['company'].casefold(), job['position'].casefold(), location))
        if not all(job[k] for k in ('job_url', 'company', 'position', 'description_text')):
            reason = 'missing_required_fields'
        elif (job.get('freshness_class') not in ('confirmed', 'uncertain') if rolling_window(state) else not fresh(job['posted_at'], source, started, hours, lower)):
            reason = 'outside_selected_window_or_unreliable_date'
        elif job['job_url'] in seen_urls or role in seen_roles:
            reason = 'duplicate'
            winner = seen_urls.get(job['job_url']) or seen_roles.get(role)
            for field in ('salary', 'contact_email', 'company_website'):
                if not winner.get(field) and job.get(field):
                    winner[field] = job[field]
        elif any(job['job_url'] in text or (job['company'].casefold() in text.casefold() and job['position'].casefold() in text.casefold()) for text in existing):
            reason = 'existing_application'
        else:
            reason = 'retained'
            retained.append(job)
            seen_urls[job['job_url']] = job
            seen_roles[role] = job
        reasons[reason] = reasons.get(reason, 0) + 1
        records.append({'record_type': 'discovery_job', 'platform': source, 'job_id': hashlib.sha256(identity.encode()).hexdigest()[:16], 'outcome': 'retain' if reason == 'retained' else 'reject', 'reason': reason})
    failures = [t['key'] for t in state['tasks'] if t['phase'] != 'done']
    summary = {'record_type': 'stage1_summary', 'status': 'partial' if failures else 'completed', 'search_count': len(state['tasks']), 'completed_searches': sum(t['phase'] == 'done' for t in state['tasks']), 'failed_search_ids': failures, 'source_failures': [{'search_id': t['key'], 'platform': t['source'], 'error_type': t.get('error_type', 'SourceFailure')} for t in state['tasks'] if t['phase'] != 'done'], 'raw_row_count': sum(len(t['jobs']) for t in state['tasks']), 'unique_source_jobs': len(rows), 'retained_job_count': len(retained), 'reasons': reasons, 'elapsed_seconds': time.time() - state['started_epoch'], 'request_count': len(state['events']), 'cost_status': 'unavailable_from_connector', 'cost_scope': 'Provider charges are not consistently exposed by these MCP tools; no zero cost is fabricated.', 'capped_searches': sum(bool(t.get('result_cap_reached')) for t in state['tasks']), 'smoke_test': state['smoke_test']}
    summary.update({key: val for key, val in progress(state, directory).items() if key in ('run_id', 'checkpoint_path', 'jobs_path', 'coverage_path', 'lookback_hours', 'window_start', 'window_end', 'supervision_paused', 'supervision_deadline')})
    raw_jobs_path = directory/'raw-jobs.json'
    if state.get('acquisition'):
        raw_jobs = [normalize(t['source'], r) for t in state['tasks'] for r in t['jobs']]
        save(raw_jobs_path, raw_jobs)
    save(directory/'coverage.json', dict(progress(state, directory), retained_job_count=len(retained), raw_row_count=summary['raw_row_count'], raw_jobs_path=str(raw_jobs_path.resolve()) if state.get('acquisition') else None, capped_searches=summary['capped_searches']))
    save(directory/'jobs.json', retained)
    save(directory/'summary.json', summary)
    # Unknown paid submissions are provisional: save private coverage, but defer
    # final mutually exclusive outcomes until the existing Actor is reconciled.
    if state.get('supervision_paused') or any(task['phase'] == 'blocked' for task in state['tasks']):
        state['finished'] = False
        return summary
    summary['summary_revision'] = hashlib.sha256(json.dumps({key: summary[key] for key in
        ('status', 'completed_searches', 'retained_job_count', 'reasons')}, sort_keys=True).encode()).hexdigest()[:16]
    save(directory/'summary.json', summary)
    # Repeated finish is safe, including restart after a partially written log.
    written = set()
    if path.exists():
        for line in path.read_text().splitlines():
            old = json.loads(line)
            if old.get('run_id') == state['run_id']:
                written.add((old['record_type'], old.get('platform'), old.get('job_id'), old.get('request_id'), old.get('summary_revision')))
    for record in state['events'] + records + [summary]:
        record = dict(record)
        record.setdefault('record_type', 'discovery_request')
        key = (record['record_type'], record.get('platform'), record.get('job_id'), record.get('request_id'), record.get('summary_revision'))
        if key not in written:
            record.update(run_id=state['run_id'], run_date=date, recorded_at=record.get('recorded_at', log.utc_now()))
            log.append_record(path, record)
            written.add(key)
    public_line = f"{datetime.fromtimestamp(state['started_epoch'], log.LOCAL_ZONE).date()} | Stage 1 {state['run_id']}: {summary['status']}; {summary['completed_searches']}/{summary['search_count']} searches completed; {len(retained)} jobs retained; {summary['elapsed_seconds']:.3f}s wall time; provider cost unavailable from connectors.\n"
    with (log_root/'log.txt').open('a+', encoding='utf-8') as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.seek(0)
        if public_line not in handle.read():
            handle.seek(0, os.SEEK_END)
            handle.write(public_line)
    state['finished'] = True
    return summary


def probe_cache(config, source, title, location, hours, cache_root):
    if not list(cache_root.glob('*.json')):return {'reusable':False}
    task=plan(config,False,1,source,title,location,hours,True)[0]
    identity={'query':task['key'],'lookback':hours,'actor':config['sources'][source].get('actor'),'actor_version':config['sources'][source].get('actor_version'),'policy':'rolling-v1'}
    key=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    with exclusive_lock(cache_root/'lock'):
        entry=cache_root/(key+'.json')
        if not entry.exists():return {'reusable':False}
        checkpoint=Path(json.loads(entry.read_text())['checkpoint_path'])
        previous=json.loads(checkpoint.read_text())
        uncertain=any(t['phase'] not in ('done','failed') or (t['phase']=='failed' and t.get('submission_outcome') != 'not_submitted' and not confirmed_rejection(t.get('error',''))) for t in previous['tasks'])
        if uncertain:return {'reusable':False,'requires_reconciliation':True,'checkpoint_path':str(checkpoint)}
        upper=datetime.fromisoformat(previous['tasks'][0].get('window_end',previous['window_end']))
        return {'reusable':upper>=datetime.now(UTC)-timedelta(hours=hours),'checkpoint_path':str(checkpoint)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['probe-cache','init', 'next', 'accept', 'finish', 'attach', 'status', 'resume'])
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--state-root', type=Path, default=ROOT/'.state/stage1')
    parser.add_argument('--config', type=Path, default=ROOT/'config/search_targets.yaml')
    parser.add_argument('--log-root', type=Path, default=ROOT/'logs')
    parser.add_argument('--acquisition', action='store_true', help='One bounded configured query with submission-relative freshness')
    parser.add_argument('--charge-contracts',type=Path)
    parser.add_argument('--charge-limit-usd')
    parser.add_argument('--cache-root', type=Path, default=ROOT/'.state/acquisitions')
    parser.add_argument('--smoke', action='store_true', help='ONE platform and ONE configured title/location, at most three results')
    parser.add_argument('--max-results', type=int)
    parser.add_argument('--supervision-minutes', type=int, help='explicit extension for the resume command')
    parser.add_argument('--lookback-hours', type=int)
    parser.add_argument('--platform', choices=sorted(TOOLS))
    parser.add_argument('--title')
    parser.add_argument('--location')
    parser.add_argument('--limit', type=int, default=3)
    parser.add_argument('--request-id')
    parser.add_argument('--search-id')
    parser.add_argument('--actor-run-id')
    args = parser.parse_args()
    if args.command=='probe-cache':
        config=yaml.safe_load(args.config.read_text())
        print(json.dumps(probe_cache(config,args.platform,args.title,args.location,resolve_lookback(config,args.lookback_hours),args.cache_root)))
        return
    if args.command == 'init' and not args.smoke and not args.acquisition and any(x is not None for x in (args.platform, args.title, args.location)):
        raise ValueError('Platform/title/location selectors require --smoke')
    log.run_state_path(args.state_root, args.run_id)  # Validate identifier before constructing paths.
    directory = args.state_root/args.run_id
    directory.mkdir(parents=True, exist_ok=True)
    state_path = directory/'checkpoint.json'
    with exclusive_lock(args.cache_root/'lock'), (directory/'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.command == 'init':
            if state_path.exists():
                state = json.loads(state_path.read_text())
                hours, _, _ = window(state)
                if args.lookback_hours is not None and resolve_lookback({}, args.lookback_hours) != hours:
                    raise ValueError('Resume lookback conflicts with the saved window; use a new run')
                if args.smoke and (not state.get('smoke_test') or len(state['tasks']) != 1):
                    raise ValueError('Smoke cannot resume a normal or legacy multi-platform checkpoint')
                for key, selected in (('source', args.platform), ('title', args.title), ('location', args.location)):
                    if selected and any(t[key].casefold() != selected.casefold() for t in state['tasks']):
                        raise ValueError('Checkpoint does not match selected smoke search')
                result = dict(progress(state, directory), status='resumed')
            else:
                config = yaml.safe_load(args.config.read_text())
                hours = resolve_lookback(config, args.lookback_hours)
                minutes = config.get('discovery_supervision_minutes', 30)
                if type(minutes) is not int or minutes <= 0:
                    raise ValueError('discovery_supervision_minutes must be a positive integer')
                state = {'run_id': args.run_id, 'started_epoch': time.time(), 'tasks': plan(config, args.smoke, args.max_results, args.platform, args.title, args.location, hours, args.acquisition), 'accepted': [], 'events': [], 'smoke_test': args.smoke, 'window_policy': 'submission-relative-v1'}
                if args.acquisition:
                    if not all((args.platform, args.title, args.location)):
                        raise ValueError('Acquisition requires platform, title and location')
                    state['acquisition'] = True
                    state['charge_contracts']=json.loads(args.charge_contracts.read_text()) if args.charge_contracts else {}
                    state['charge_contracts_path']=str(args.charge_contracts.resolve()) if args.charge_contracts else None
                    state['charge_limit_usd']=args.charge_limit_usd
                    identity = {'query': state['tasks'][0]['key'], 'lookback': hours, 'actor': config['sources'][args.platform].get('actor'), 'actor_version': config['sources'][args.platform].get('actor_version'), 'policy': 'rolling-v1'}
                    state['requested_cap'] = state['tasks'][0]['cap']
                    state['actor_version'] = identity['actor_version']
                    state['cache_key'] = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
                    state['cache_root'] = str(args.cache_root.resolve())
                    entry = args.cache_root/(state['cache_key']+'.json')
                    if entry.exists():
                        previous = json.loads(Path(json.loads(entry.read_text())['checkpoint_path']).read_text())
                        uncertain = any(t['phase'] not in ('done', 'failed') or (t['phase'] == 'failed' and t.get('submission_outcome') != 'not_submitted' and not confirmed_rejection(t.get('error', ''))) for t in previous['tasks'])
                        if uncertain:
                            raise ValueError('Existing acquisition requires reconciliation/resume at '+json.loads(entry.read_text())['checkpoint_path'])
                        old_upper = datetime.fromisoformat(previous['tasks'][0].get('window_end', previous['window_end']))
                        fresh_lower = datetime.fromtimestamp(state['started_epoch'], UTC)-timedelta(hours=hours)
                        if old_upper >= fresh_lower:
                            state['tasks'] = previous['tasks']
                            state['reused'] = True
                state['supervision_deadline'] = state['started_epoch'] + minutes * 60
                started = datetime.fromtimestamp(state['started_epoch'], UTC)
                state.update(lookback_hours=hours, window_start=(started-timedelta(hours=hours)).isoformat(), window_end=started.isoformat())
                result = dict(progress(state, directory), status='initialized')
        else:
            state = json.loads(state_path.read_text())
            hours, _, _ = window(state)
            if args.lookback_hours is not None and resolve_lookback({}, args.lookback_hours) != hours:
                raise ValueError('Resume lookback conflicts with the saved window; use a new run')
            if args.command == 'next':
                requests = [] if state.get('finished') else next_requests(state, max(1, min(args.limit, 4)))
                result = dict(progress(state, directory), requests=requests)
            elif args.command == 'status':
                result = progress(state, directory)
            elif args.command == 'accept':
                response = json.load(sys.stdin)
                result = accept(state, args.request_id, response)
                response_path = directory/'responses'/(hashlib.sha256(args.request_id.encode()).hexdigest()+'.json')
                if not response_path.exists():
                    save(response_path, response)
                result['response_path'] = str(response_path.resolve())
            elif args.command == 'resume':
                if not state.get('supervision_paused') or type(args.supervision_minutes) is not int or args.supervision_minutes <= 0:
                    raise ValueError('Resume requires a paused checkpoint and positive --supervision-minutes')
                state.update(supervision_deadline=time.time() + args.supervision_minutes * 60, supervision_paused=False, finished=False)
                result = progress(state, directory)
            elif args.command == 'attach':
                task = next(t for t in state['tasks'] if t['key'] == args.search_id)
                if task['source'] == 'indeed' or task['phase'] != 'blocked' or not args.actor_run_id:
                    raise ValueError('Attach requires a blocked Apify search and its confirmed run ID')
                task.update(actor_run_id=args.actor_run_id, phase='poll', inflight=None)
                state['finished'] = False
                result = {'status': 'attached'}
            else:
                result = finish(state, directory, log_root=args.log_root)
        if args.command != 'status':
            hours, lower, upper = window(state)
            state.update(lookback_hours=hours, window_start=lower.isoformat(), window_end=upper.isoformat())
            save(state_path, state)
            if state.get('acquisition'):
                save(Path(state['cache_root'])/(state['cache_key']+'.json'), {'checkpoint_path': str(state_path.resolve())})
        if args.command == 'accept' and result.get('status') != 'already_saved':
            event = dict(state['events'][-1], record_type='discovery_request', run_id=state['run_id'], run_date=log.local_run_date(state['started_epoch']))
            log.append_record(log.stage_path(args.log_root, event['run_date'], 'discovery'), event)
    print(json.dumps(result))

if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, StopIteration) as error:
        print(f'discovery: {error}', file=sys.stderr)
        sys.exit(1)
