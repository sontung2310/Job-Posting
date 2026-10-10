#!/usr/bin/env python3
"""Read-only raw retrieval audit. Output contains counts, never JDs or credentials."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re


def audit(checkpoint, benchmark=None):
    state = json.loads(checkpoint.read_text())
    sources = {}
    raw_index = {}
    for source in ('seek', 'linkedin', 'indeed'):
        tasks = [task for task in state['tasks'] if task['source'] == source]
        rows = [row for task in tasks for row in task['jobs']]
        if not tasks:
            continue
        url_key = {'seek':'jobLink','linkedin':'link','indeed':'url'}[source]
        date_key = {'seek':'listedAt','linkedin':'postedAt','indeed':'posted_date'}[source]
        identities = [str(row.get('id') or row.get('jobkey') or row.get(url_key) or '') for row in rows]
        missing = sum(not identity for identity in identities)
        unique = len(set(identity for identity in identities if identity))
        dates = [str(row.get(date_key) or '') for row in rows]
        sources[source] = {'raw':len(rows), 'unique':unique,
            'duplicates':len(rows)-missing-unique, 'missing_identity':missing,
            'calendar_only':sum(bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}',date)) for date in dates),
            'posting_dates':dict(Counter(date[:10] for date in dates)),
            'date_ranges':sorted({task['args']['dateRange'] for task in tasks if 'dateRange' in task['args']})}
        for row, identity in zip(rows, identities):
            raw_index[source, identity] = row
    result = {'sources':sources, 'billing':'Raw rows are not actual charged-event telemetry.'}
    if benchmark:
        labels = json.loads(benchmark.read_text())['rows']
        seen = set()
        for label in labels:
            key = label['source'], label['source_job_id']
            if key in seen or key not in raw_index or label['label'] not in {'relevant','irrelevant','unknown'} or not label.get('reason'):
                raise ValueError('Invalid or duplicate benchmark identity/label')
            seen.add(key)
            row = raw_index[key]
            description = row.get('descriptionText') or row.get('descriptionHtml') or ''
            if key[0] == 'seek':
                description = row.get('content',{}).get('unEditedContent') or ' '.join(row.get('content',{}).get('sections') or [])
            if hashlib.sha256(str(description).encode()).hexdigest() != label['description_sha256']:
                raise ValueError('Benchmark description fingerprint changed')
        result['benchmark'] = {'unique_jobs':len(labels),'labels':dict(Counter(label['label'] for label in labels)),
            'semantic_validation':'Adjudicated labels; runtime relevance decisions require separate replay.'}
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint',type=Path,required=True)
    parser.add_argument('--benchmark',type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.checkpoint,args.benchmark)))
