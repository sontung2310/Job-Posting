#!/usr/bin/env python3
"""Shared readiness checks; cache personal inputs privately, print only counts."""
import argparse
import contextlib
import io
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import yaml
from condition_profile import build_condition_profile
from private_io import write_private_json
from vault_evidence import scan_vault, validation_errors, run_check_index, build_chroma_index, SemanticSearchUnavailable, local_vault_fingerprint
from paid_operations import exclusive_lock, operation_path, pending_operation

ROOT = Path(__file__).resolve().parents[1]


def resolve_pdftotext(explicit=None):
    configured = explicit or os.environ.get('PDFTOTEXT_BIN') or shutil.which('pdftotext')
    if configured:
        return configured
    bundled = Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/poppler/bin/pdftotext'
    return str(bundled) if bundled.is_file() and os.access(bundled, os.X_OK) else None


def local_check(mode='scoring', *, vault=ROOT/'career-vault', resumes_dir=ROOT/'resumes',
          hybrid_search=None, pdftotext=None, config_path=None, cache_path=None):
    if mode not in ('scoring', 'discovery'):
        raise ValueError('mode must be scoring or discovery')
    vault, resumes_dir = Path(vault), Path(resumes_dir)
    config_path = Path(config_path or ROOT/'config/search_targets.yaml')
    cache_path = Path(cache_path or ROOT/'.state/readiness.json')
    config = yaml.safe_load(config_path.read_text()) if config_path.exists() else {}
    if hybrid_search is None:
        hybrid_search = config.get('hybrid_search', True)
    if not isinstance(hybrid_search, bool):
        raise ValueError('hybrid_search must be boolean')
    if mode == 'discovery':
        # Discovery checks evidence eligibility locally; scoring owns personal/PDF/cloud readiness.
        notes, parse_errors = scan_vault(vault)
        errors = validation_errors(notes, parse_errors)
        if errors:
            raise ValueError('Vault readiness failed: ' + '; '.join(errors))
        fingerprint = hashlib.sha256(config_path.read_bytes() if config_path.exists() else b'').hexdigest()
        return dict(input_fingerprint=fingerprint, hybrid_search=hybrid_search, reused=False, resumes={})
    extractor = resolve_pdftotext(pdftotext)
    if not extractor:
        raise ValueError('pdftotext is required (set PDFTOTEXT_BIN)')
    pdfs = sorted(p for p in resumes_dir.iterdir() if p.is_file() and p.suffix.lower() == '.pdf')
    if len(pdfs) < 2:
        raise ValueError('At least two extractable resume PDFs are required.')
    paths = [config_path] if config_path.exists() else []
    paths += [p for p in vault.rglob('*') if p.is_file() and not any(part in ('07 Applications', '.obsidian', '__pycache__') for part in p.parts)]
    paths += pdfs
    paths += [Path(__file__), Path(__file__).with_name('condition_profile.py'), Path(__file__).with_name('vault_evidence.py'), Path(__file__).with_name('assessment_validation.py'), Path(__file__).with_name('private_io.py')]
    if Path(extractor).is_file():
        paths.append(Path(extractor))
    digest = hashlib.sha256(str(hybrid_search).encode())
    for path in sorted(set(paths)):
        digest.update(str(path.resolve()).encode()); digest.update(path.read_bytes())
    fingerprint = digest.hexdigest()
    try:
        saved = json.loads(cache_path.read_text())
        payload = {key: saved[key] for key in ('profile', 'resumes', 'input_fingerprint', 'hybrid_search')}
        integrity = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        if saved['input_fingerprint'] == fingerprint and saved['payload_sha256'] == integrity:
            cache_valid = True
        else:
            cache_valid = False
    except (OSError, ValueError, KeyError, TypeError):
        cache_valid = False
    if cache_valid:
        return dict(payload, reused=True)
    notes, parse_errors = scan_vault(vault)
    errors = validation_errors(notes, parse_errors)
    if errors:
        raise ValueError('Vault readiness failed: ' + '; '.join(errors))
    profile_path = cache_path.parent/'condition-check.json'
    profile = build_condition_profile(vault, profile_path)
    profile_path.chmod(0o600)
    texts = {}
    for pdf in pdfs:
        result = subprocess.run([str(extractor), '-layout', str(pdf), '-'], capture_output=True, text=True)
        if result.returncode or not result.stdout.strip():
            raise ValueError(f'No extractable text: {pdf.name}')
        texts[pdf.name] = result.stdout
    payload = dict(profile=profile, resumes=texts, input_fingerprint=fingerprint, hybrid_search=hybrid_search)
    saved = dict(payload, payload_sha256=hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest())
    write_private_json(cache_path, saved)
    return dict(payload, reused=False)


def ensure_hybrid(vault, *, cache_path=None, authorize_paid_retry=False):
    """One index owner across runs/cache paths; called only for eligible jobs."""
    vault = Path(vault)
    cache_path = Path(cache_path or vault.resolve().parent / '.state/readiness.json')
    base = operation_path(vault, 'index')
    pending = base.with_suffix('.pending.json')
    success = base.with_suffix('.ready.json')
    legacy = {cache_path.with_name(cache_path.name + '.hybrid-pending.json'),
              vault.resolve().parent / '.state/readiness.json.hybrid-pending.json'}
    with exclusive_lock(base.with_suffix('.lock')):
        fingerprint = local_vault_fingerprint(vault)
        try:
            previous = json.loads(success.read_text())
        except (OSError, ValueError):
            previous = {}
        with pending_operation(pending, authorize_paid_retry=authorize_paid_retry, legacy=legacy):
            # Helpers print index details; keep the public CLI stdout JSON-only.
            with contextlib.redirect_stdout(io.StringIO()):
                if previous.get('fingerprint') != fingerprint:
                    build_chroma_index(vault, 'text-embedding-3-small')
                run_check_index(vault, 'text-embedding-3-small')
            write_private_json(success, {'fingerprint': fingerprint})


def check(mode='scoring', *, vault=ROOT/'career-vault', resumes_dir=ROOT/'resumes',
          hybrid_search=None, pdftotext=None, config_path=None, cache_path=None,
          authorize_paid_retry=False, defer_hybrid=False):
    cache_path = Path(cache_path or ROOT/'.state/readiness.json')
    with exclusive_lock(cache_path.with_name(cache_path.name + '.lock')):
        result = local_check(mode, vault=vault, resumes_dir=resumes_dir,
            hybrid_search=hybrid_search, pdftotext=pdftotext, config_path=config_path,
            cache_path=cache_path)
    # Release the local cache lock before any remote index operation.
    if mode == 'scoring' and result['hybrid_search'] and not defer_hybrid:
        ensure_hybrid(vault, cache_path=cache_path, authorize_paid_retry=authorize_paid_retry)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--authorize-paid-retry', action='store_true', help='use only after explicit user approval of uncertain paid work')
    parser.add_argument('--local-only', action='store_true', help='prepare local inputs; defer cloud work until a job passes conditions')
    parser.add_argument('--mode', choices=('scoring', 'discovery'), default='scoring')
    parser.add_argument('--vault', type=Path, default=ROOT/'career-vault')
    parser.add_argument('--resumes', type=Path, default=ROOT/'resumes')
    parser.add_argument('--config', type=Path, default=ROOT/'config/search_targets.yaml')
    parser.add_argument('--cache', type=Path, default=ROOT/'.state/readiness.json')
    args = parser.parse_args()
    try:
        result = check(args.mode, vault=args.vault, resumes_dir=args.resumes, config_path=args.config, cache_path=args.cache, authorize_paid_retry=args.authorize_paid_retry, defer_hybrid=args.local_only)
    except (OSError, ValueError, SemanticSearchUnavailable) as error:
        parser.error(str(error))
    print(json.dumps({key: result[key] for key in ('input_fingerprint', 'hybrid_search', 'reused')} | {'resume_count': len(result['resumes']), 'ready': True}))

if __name__ == '__main__':
    main()
