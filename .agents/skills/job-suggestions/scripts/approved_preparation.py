#!/usr/bin/env python3
"""Validate selected report candidates and save approved-only suggestions."""
from __future__ import annotations
from pathlib import Path
import sys
WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(WORKSPACE_ROOT / "scripts"))
sys.path.insert(0, str(WORKSPACE_ROOT / ".agents/skills/job-scoring/scripts"))

import argparse
import json
import os
import subprocess
import assessment
import assessment_validation
import vault_evidence as vault
from private_io import write_private_json
from assessment import load_state, require_unchanged_finalized, reviewed_condition


def suggestion_template(result, condition_review=None):
    recommended = result['match']['recommended_resume']
    gaps = [{'requirement_id': row['id'], 'text': row['requirement'] + ': ' + row['candidate_reason']}
            for row in result['evidence_table'] if row['candidate_strength'] != 'direct']
    gaps += [{'condition_wording': clause['wording'], 'text': clause['wording'] + ' ' + clause['reason']}
             for clause in (condition_review or {}).get('clauses', []) if clause['status'] == 'manual_review']
    coverage = [{'requirement_id': row['id'], 'text': row['requirement'] + ': resume support is ' + row['resume_strengths'][recommended]}
                for row in result['evidence_table'] if row['resume_strengths'][recommended] != 'direct']
    return {'jd_priorities': [{key: row[key] for key in ('id', 'requirement', 'priority')} for row in result['evidence_table']],
            'strengths': [], 'gaps': gaps, 'resume_plan': {
                'recommended_resume': recommended, 'coverage_gaps': coverage, 'changes': []}}


def validate_suggestions(suggestions, result, condition_review=None):
    if not isinstance(suggestions, dict) or any(not isinstance(suggestions.get(key), list) for key in ('jd_priorities', 'strengths', 'gaps')):
        raise ValueError('qualifier needs JD priorities, strengths, gaps and resume plan')
    rows = {row['id']: row for row in result['evidence_table']}
    expected = suggestion_template(result)['jd_priorities']
    if suggestions['jd_priorities'] != expected:
        raise ValueError('JD priorities must preserve all frozen requirement IDs, scope and priority')
    plan = suggestions.get('resume_plan')
    if not isinstance(plan, dict) or plan.get('recommended_resume') != result['match']['recommended_resume'] or any(not isinstance(plan.get(key), list) for key in ('coverage_gaps', 'changes')):
        raise ValueError('resume plan must identify validated recommended resume, coverage gaps and changes')
    allowed = {(item['path'], item['heading']) for row in rows.values() for item in row['evidence']}
    def sourced(item):
        if not isinstance(item, dict) or not isinstance(item.get('text'), str) or not item['text'].strip() or not isinstance(item.get('citations'), list) or not item['citations']:
            raise ValueError('strength/change needs text and supporting citations')
        if any(not isinstance(cite, dict) or (cite.get('path'), cite.get('heading')) not in allowed for cite in item['citations']):
            raise ValueError('suggestion cites unsupported evidence')
    if not suggestions['strengths']:
        raise ValueError('qualifier needs a sourced strength')
    for strength in suggestions['strengths']:
        sourced(strength)
    manual = {c['wording'] for c in (condition_review or {}).get('clauses', []) if c['status'] == 'manual_review'}
    for gap in suggestions['gaps'] + plan['coverage_gaps']:
        if not isinstance(gap, dict) or not (gap.get('requirement_id') in rows or gap.get('condition_wording') in manual) or not isinstance(gap.get('text'), str) or not gap['text'].strip():
            raise ValueError('gap must link text to a frozen requirement')
    required = {row['id'] for row in rows.values() if row['candidate_strength'] != 'direct'}
    covered = {gap.get('requirement_id') for gap in suggestions['gaps']}
    conditions = {gap.get('condition_wording') for gap in suggestions['gaps']}
    if not required.issubset(covered) or not manual.issubset(conditions):
        raise ValueError('suggestions must account for every evidence gap and unclear condition')
    required_coverage = {row['id'] for row in rows.values() if row['resume_strengths'][plan['recommended_resume']] != 'direct'}
    if not required_coverage.issubset({gap.get('requirement_id') for gap in plan['coverage_gaps']}):
        raise ValueError('resume coverage gaps cannot be omitted')
    for change in plan['changes']:
        sourced(change)
        if change.get('requirement_id') not in rows or change.get('review_before_adding') is not True:
            raise ValueError('supported resume changes must link requirements and be labelled review before adding')


def select_candidates(state, report_id, numbers, *, obsidian=False, notion=False):
    """Resolve explicit approval to current frozen candidates; writes remain connector-owned."""
    if type(obsidian) is not bool or type(notion) is not bool:
        raise ValueError('destination flags must be booleans')
    manifest = load_state(state)
    require_unchanged_finalized(state, manifest)
    report = json.loads((state/'report.json').read_text())
    if report.get('selectable') is not True or report.get('unresolved') or any(
            not (state/f"{row['job_id']}-scored.json").exists() or
            json.loads((state/f"{row['job_id']}-scored.json").read_text()).get('status') not in {'qualified', 'below_threshold', 'condition_failed'}
            for row in manifest['jobs']):
        raise ValueError('incomplete report cannot authorize selection')
    if report.get('report_id') != report_id or report.get('input_fingerprint') != manifest['input_fingerprint']:
        raise ValueError('stale report approval')
    expected_identity = assessment_validation.fingerprint({'manifest': manifest['fingerprint'], 'candidates': report['candidates'], 'unresolved': report.get('unresolved', [])})
    if expected_identity != report_id:
        raise ValueError('report mapping changed')
    if not numbers or any(type(number) is not int for number in numbers) or len(set(numbers)) != len(numbers):
        raise ValueError('selection needs unique candidate numbers')
    entries = {entry['number']: entry for entry in report['candidates']}
    if any(number not in entries for number in numbers):
        raise ValueError('unknown candidate number')
    selected = [entries[number] for number in numbers]
    for entry in selected:
        if entry['result']['match']['ATS_score'] <= manifest['threshold']:
            raise ValueError('selected candidate is below current threshold')
        current = json.loads((state/f"{entry['job_id']}-scored.json").read_text())
        if current != {key: value for key, value in entry.items() if key not in {'number', 'job'}}:
            raise ValueError('report assessment provenance changed')
        reviewed_condition(state, manifest, entry['job_id'])
    return {'report_id': report_id, 'run_handle': str(state.resolve()), 'selected': selected,
            'destinations': {'obsidian': 'enabled' if obsidian else 'skipped_disabled',
                             'notion': 'enabled' if notion else 'skipped_disabled'},
            'requires_destination_duplicate_check': True, 'application_records_written': False}



def approve_selection(state, report_id, numbers, *, obsidian=False, notion=False):
    selected = select_candidates(state, report_id, numbers, obsidian=obsidian, notion=notion)
    selected['selected'].sort(key=lambda row: row['number'])
    identity = assessment_validation.fingerprint({'report_id': report_id, 'numbers': sorted(numbers)})
    handle = state / 'preparation' / identity
    payload = {**selected, 'run_id': load_state(state)['run_id'], 'numbers': sorted(numbers),
               'selection_id': identity, 'preparation_handle': str(handle.resolve())}
    write_private_json(handle / 'selection.json', payload)
    return payload


def load_preparation(handle):
    saved = json.loads((handle / 'selection.json').read_text())
    identity = assessment_validation.fingerprint({'report_id': saved['report_id'], 'numbers': sorted(saved['numbers'])})
    if identity != handle.name or identity != saved.get('selection_id'):
        raise ValueError('approved selection changed')
    flags = saved['destinations']
    if set(flags) != {'obsidian', 'notion'} or any(v not in {'enabled', 'skipped_disabled'} for v in flags.values()):
        raise ValueError('invalid destination flags')
    current = select_candidates(Path(saved['run_handle']), saved['report_id'], saved['numbers'],
        obsidian=flags['obsidian'] == 'enabled', notion=flags['notion'] == 'enabled')
    if current['selected'] != saved['selected']:
        raise ValueError('approved candidate provenance changed')
    return saved


def inspect_preparation(handle, offset=0, limit=1):
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 3:
        raise ValueError('inspect requires nonnegative offset and limit between 1 and 3')
    selection = load_preparation(handle)
    state = Path(selection['run_handle'])
    manifest = load_state(state)
    resume_lines = {name: assessment.units_from_jd(text) for name, text in
                    assessment.load_resumes(Path(manifest['resumes_dir']), manifest['pdftotext']).items()}
    rows = []
    for entry in selection['selected'][offset:offset + limit]:
        packet = json.loads((state / (entry['job_id'] + '-packet.json')).read_text())
        manifest = load_state(state)
        reviewed = json.loads((state / (entry['job_id'] + '-reviewed.json')).read_text())
        assessment.trusted_assessment(state, reviewed, Path(manifest['vault']), Path(manifest['resumes_dir']))
        vault_root = Path(manifest['vault']).resolve()
        for relative, text in packet['verified_notes'].items():
            note = (vault_root / relative).resolve()
            if not note.is_relative_to(vault_root) or vault.is_excluded_path(note.relative_to(vault_root)) or note.read_text() != text:
                raise ValueError('saved suggestion evidence changed')
        packet['resume_lines'] = resume_lines
        path = handle / (entry['job_id'] + '-suggestions.json')
        saved_suggestions = json.loads(path.read_text()) if path.exists() else None
        if saved_suggestions is not None:
            validate_suggestions(saved_suggestions, entry['result'], entry['condition_review'])
        rows.append({'number': entry['number'], 'job': entry['job'], 'result': entry['result'],
            'condition_review': entry['condition_review'], 'packet': packet,
            'suggestions': saved_suggestions,
            'suggestions_template': {'number': entry['number'], 'suggestions': suggestion_template(entry['result'], entry['condition_review'])}})
    end = min(offset + limit, len(selection['selected']))
    return {'preparation_handle': str(handle.resolve()), 'jobs': rows,
            'next_offset': end if end < len(selection['selected']) else None}


def submit_suggestions(handle, submission):
    selection = load_preparation(handle)
    rows = submission.get('jobs') if isinstance(submission, dict) else None
    if not isinstance(rows, list) or not 1 <= len(rows) <= 3:
        raise ValueError('submit one to three selected jobs')
    selected = {row['number']: row for row in selection['selected']}
    seen = set()
    for row in rows:
        number = row.get('number') if isinstance(row, dict) else None
        if type(number) is not int or number not in selected or number in seen:
            raise ValueError('suggestions require unique approved candidate numbers')
        seen.add(number)
        validate_suggestions(row.get('suggestions'), selected[number]['result'], selected[number]['condition_review'])
    # Revalidate approval and provenance immediately before private persistence.
    load_preparation(handle)
    for row in rows:
        entry = selected[row['number']]
        write_private_json(handle / (entry['job_id'] + '-suggestions.json'), row['suggestions'])
    import pipeline_log
    manifest = load_state(Path(selection['run_handle']))
    log_root = Path(manifest['log_root'])
    log_path = pipeline_log.stage_path(log_root, pipeline_log.local_run_date(manifest['started_epoch_seconds']), 'suggestion')
    existing = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()] if log_path.exists() else []
    keys = {(row.get('report_id'), row.get('job_id')) for row in existing}
    for row in rows:
        job_id = selected[row['number']]['job_id']
        if (selection['report_id'], job_id) not in keys:
            pipeline_log.append_record(log_path, {'record_type': 'suggestion_job', 'run_id': selection['run_id'],
                'report_id': selection['report_id'], 'job_id': job_id, 'status': 'prepared',
                'recorded_at': pipeline_log.utc_now(), 'usage_available': False, 'token_usage': None,
                'cost_estimate_usd': None, 'elapsed_seconds': None})
    ready = 0
    for entry in selected.values():
        path = handle / (entry['job_id'] + '-suggestions.json')
        if path.exists():
            validate_suggestions(json.loads(path.read_text()), entry['result'], entry['condition_review'])
            ready += 1
    return {'preparation_handle': str(handle.resolve()), 'selected_job_count': len(selected),
            'suggestions_ready_count': ready, 'remaining_job_count': len(selected) - ready,
            'status': 'ready_for_destinations' if ready == len(selected) else 'in_progress',
            'application_records_written': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    select = commands.add_parser('select')
    select.add_argument('--run', type=Path, required=True)
    select.add_argument('--report-id', required=True)
    select.add_argument('--numbers', type=int, nargs='+', required=True)
    inspect = commands.add_parser('inspect')
    inspect.add_argument('--preparation', type=Path, required=True)
    inspect.add_argument('--offset', type=int, default=0)
    inspect.add_argument('--limit', type=int, default=1)
    submit = commands.add_parser('suggestions')
    submit.add_argument('--preparation', type=Path, required=True)
    submit.add_argument('--input', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'select':
            result = approve_selection(args.run, args.report_id, args.numbers,
                obsidian=vault.parse_bool(os.environ.get('WRITE_OBSIDIAN', 'false')),
                notion=vault.parse_bool(os.environ.get('WRITE_NOTION', 'false')))
            result = {k: result[k] for k in ('preparation_handle', 'report_id', 'run_id', 'destinations', 'application_records_written')}
        elif args.command == 'inspect':
            result = inspect_preparation(args.preparation, args.offset, args.limit)
        else:
            result = submit_suggestions(args.preparation, json.loads(args.input.read_text()))
        print(json.dumps(result))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        parser.error(str(error))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
