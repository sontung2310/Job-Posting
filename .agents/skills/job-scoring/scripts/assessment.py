#!/usr/bin/env python3
"""Mechanical saved-job assessment support. Semantic judgments belong to Codex."""
from __future__ import annotations
from pathlib import Path
import sys
WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(WORKSPACE_ROOT / "scripts"))

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import condition_profile
import assessment_validation
from private_io import write_private_json
import vault_evidence as vault

ROOT = WORKSPACE_ROOT


def freeze_requirements(units, classified):
    rows = classified.get("units") if isinstance(classified, dict) else None
    if not isinstance(rows, list) or any(not isinstance(row, dict) or type(row.get("id")) is not int for row in rows):
        raise ValueError("classifications must include each numbered original JD unit")
    expected = {unit["id"] for unit in units}
    if len(rows) != len(units) or {row["id"] for row in rows} != expected:
        raise ValueError("Extraction omitted, duplicated, or invented JD units")
    lookup = {row["id"]: row for row in rows}
    result = []
    for unit in units:
        row = lookup[unit["id"]]
        if row.get("category") not in {"Skills", "Experience", "Domain", "ignore"} or type(row.get("priority")) is not int or row["priority"] not in {1, 2, 3}:
            raise ValueError("Invalid requirement category or priority")
        if not isinstance(row.get("reason"), str) or not row["reason"].strip():
            raise ValueError("Every original JD unit needs a classification reason")
        if row["category"] != "ignore":
            result.append({"id": f"r{unit['id']}", "requirement": unit["text"],
                           "category": row["category"], "priority": row["priority"]})
    if not result:
        raise ValueError("No scoring requirements extracted; review JD instead of assigning a score")
    return result


def current_profile(vault_dir):
    with tempfile.TemporaryDirectory() as directory:
        return condition_profile.build_condition_profile(vault_dir, Path(directory)/"profile.json")


def units_from_jd(text):
    # Split only at original whitespace; each unit remains exact JD wording.
    parts = [part.strip() for part in re.split(r"\n+|(?<=[.!?])\s+(?=[A-Z])", text) if part.strip()]
    return [{"id": i+1, "text": part} for i, part in enumerate(parts)]


def job_units(job):
    text = job["description_text"]
    if job["position"].casefold() not in text.casefold():
        text = job["position"]+"\n"+text
    return units_from_jd(text)


def load_resumes(directory, binary):
    binary = binary or os.environ.get("PDFTOTEXT_BIN") or shutil.which("pdftotext")
    if not binary:
        raise ValueError("Set PDFTOTEXT_BIN to a pdftotext executable")
    result = {}
    for path in sorted(directory.glob("*")):
        if path.suffix.lower() == ".pdf":
            text = subprocess.run([binary, "-layout", str(path), "-"], check=True,
                                  capture_output=True, text=True, timeout=20).stdout.strip()
            if not text:
                raise ValueError("A resume has no extractable text")
            result[path.name] = text
    if len(result) < 2:
        raise ValueError("At least two text-extractable resumes required")
    return result


def repository_source_path(source):
    """Resolve allowed repository citations, including the retired adapter name."""
    prefix = "Job-Search repository "
    if not source.startswith(prefix):
        return None
    relative = source[len(prefix):].split("#", 1)[0]
    aliases = {"README.md": "README.md", "config/search_targets.yaml": "config/search_targets.yaml",
               "docs/06-source-adapters.md": "docs/additional-source-adapters.md",
               "docs/additional-source-adapters.md": "docs/additional-source-adapters.md"}
    if relative not in aliases:
        raise ValueError("Repository evidence source is not allowed")
    # Prefer an actual historical snapshot when present; otherwise use its renamed reference.
    path = ROOT / relative
    if not path.exists():
        path = ROOT / aliases[relative]
    path = path.resolve()
    if not path.is_relative_to(ROOT.resolve()) or not path.is_file():
        raise ValueError("Repository evidence source unavailable for inspection")
    return path


def evidence_fingerprint(vault_dir, resume_dir):
    digest = hashlib.sha256(vault.local_vault_fingerprint(vault_dir).encode())
    notes, errors = vault.scan_vault(vault_dir)
    if errors:
        raise ValueError("unreadable evidence input")
    for source in sorted({source for note in vault.eligible_notes(notes) for source in note.sources}):
        relative = source.removeprefix("[[").removesuffix("]]").split("#")[0]
        path = (vault_dir/relative).resolve()
        if path.is_relative_to(vault_dir.resolve()) and path.is_file() and not vault.is_excluded_path(path.relative_to(vault_dir.resolve())):
            digest.update(path.read_bytes())
        elif source.startswith("Job-Search repository "):
            digest.update(repository_source_path(source).read_bytes())
    for path in sorted(resume_dir.glob("*")):
        if path.suffix.lower() == ".pdf":
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def source_excerpts(sources, resumes, vault_dir, remote_sources=None):
    result = []
    for source in sources:
        if source in resumes:
            result.append({"source": source, "text": resumes[source]})
        elif source.startswith("user-confirmed:"):
            result.append({"source": source, "text": "User confirmation recorded in this verified note."})
        else:
            if source.startswith("https://") and remote_sources is not None and source in remote_sources:
                text = remote_sources[source]
                if not isinstance(text, str) or not text.strip():
                    raise ValueError("remote source excerpt must contain inspected text")
                result.append({"source": source, "text": text})
                continue
            relative = source.removeprefix("[[").removesuffix("]]").split("#")[0]
            path = (vault_dir / relative).resolve()
            if path.is_relative_to(vault_dir.resolve()) and path.is_file() and not vault.is_excluded_path(path.relative_to(vault_dir.resolve())):
                result.append({"source": source, "text": path.read_text()})
            elif source.startswith("Job-Search repository "):
                text = repository_source_path(source).read_text()
                if relative.endswith("README.md"):
                    sections = re.split(r"(?m)(?=^## )",text)
                    text = "\n".join(section for i,section in enumerate(sections)
                        if i == 0 or re.search(r"additional sources|maintain a source|project map",section.splitlines()[0],re.I))
                result.append({"source": source, "text": text})
            else:
                raise ValueError("Linked evidence source unavailable for inspection")
    return result


def prepare_assessment(input_path, state, vault_dir, resumes_dir, *, hybrid_search=None, pdftotext=None, readiness_cache=None, log_root=None, authorize_paid_retry=False):
    """Save local readiness and the full retrieval handoff; reuse unchanged work."""
    import scoring
    threshold = scoring.qualification_threshold()
    started = time.time()
    handoff = json.loads(input_path.read_text())
    if isinstance(handoff, list):
        coverage_path = input_path.parent/"coverage.json"
        coverage = json.loads(coverage_path.read_text()) if coverage_path.exists() else {"status": "unknown"}
        if not isinstance(coverage, dict):
            raise ValueError("saved coverage must be an object")
        handoff = {"jobs": handoff, "coverage": coverage,
                   **{key: coverage[key] for key in ("run_id", "checkpoint_path", "window_start", "window_end") if key in coverage}}
    if not isinstance(handoff, dict) or not isinstance(handoff.get("jobs"), list):
        raise ValueError("handoff must include saved normalized jobs")
    if not isinstance(handoff.get('coverage', {'status': 'unknown'}), dict):
        raise ValueError('saved coverage must be an object')
    workspace = ROOT if vault_dir.resolve() == (ROOT/'career-vault').resolve() else state.resolve().parent
    readiness_cache = readiness_cache or workspace/'.state/readiness.json'
    log_root = log_root or workspace/'logs'
    import readiness
    pdftotext = readiness.resolve_pdftotext(pdftotext)
    if handoff['jobs']:
        ready = readiness.check(mode='scoring', vault=vault_dir, resumes_dir=resumes_dir,
                                hybrid_search=hybrid_search, pdftotext=pdftotext, cache_path=readiness_cache,
                                authorize_paid_retry=authorize_paid_retry, defer_hybrid=True)
        profile, resumes, hybrid_search = ready['profile'], ready['resumes'], ready['hybrid_search']
        prepared = assessment_validation.prepare_jobs(handoff, profile)
        inputs = evidence_fingerprint(vault_dir, resumes_dir)
    else:
        profile, resumes, hybrid_search = {}, {}, False
        prepared, inputs = {'jobs': []}, 'empty-handoff'

    scoring_policy = scoring.policy()
    identity = assessment_validation.fingerprint({"handoff": handoff, "inputs": inputs, "hybrid_search": hybrid_search, "threshold": threshold, "scoring_policy": scoring_policy})
    manifest_path = state/"manifest.json"
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text())
        if existing.get("fingerprint") == identity:
            return existing
        if (state/"results.json").exists():
            raise ValueError("finalized assessment inputs cannot change; prepare a new scoring directory/run")
    manifest = {"schema_version": 1, "threshold": threshold, "scoring_policy": scoring_policy, "fingerprint": identity, "input_fingerprint": inputs,
                "run_id": os.environ.get("PIPELINE_RUN_ID") or state.name, "log_root": str(Path(log_root).resolve()),
                "handoff": handoff, "prepared": prepared, "profile": profile,
                "vault": str(vault_dir.resolve()), "resumes_dir": str(resumes_dir.resolve()),
                "pdftotext": pdftotext or os.environ.get("PDFTOTEXT_BIN") or shutil.which("pdftotext"),
                "hybrid_search": hybrid_search, "readiness_cache": str(Path(readiness_cache).resolve()), "started_epoch_seconds": started,
                "resume_lines": {name: units_from_jd(text) for name, text in resumes.items()},
                "jobs": [{"job_id": assessment_validation.job_id(job), "job": job, "units": job_units(job)} for job in handoff["jobs"]]}
    write_private_json(manifest_path, manifest)
    return manifest


def load_state(state):
    import scoring
    manifest = json.loads((state/"manifest.json").read_text())
    if manifest.get("threshold") != scoring.qualification_threshold():
        raise ValueError("qualification threshold changed or unavailable; prepare a new run")
    if manifest.get("schema_version") != 1:
        raise ValueError("unsupported private assessment manifest")
    if manifest['jobs'] and evidence_fingerprint(Path(manifest["vault"]), Path(manifest["resumes_dir"])) != manifest["input_fingerprint"]:
        raise ValueError("evidence/profile/resume inputs changed; prepare and review again")
    return manifest


def selected_job(manifest, identifier):
    matches = [row for row in manifest["jobs"] if row["job_id"] == identifier]
    if len(matches) != 1:
        raise ValueError("unknown or duplicate original job ID")
    return matches[0]


def condition_file(state, identifier):
    return state/f"{identifier}-condition.json"


def save_condition(state, identifier, review):
    manifest = load_state(state)
    row = selected_job(manifest, identifier)
    assessment_validation.validate_condition(row["job"], current_profile(Path(manifest["vault"])), review)
    write_private_json(condition_file(state, identifier), review)
    return review


def reviewed_condition(state, manifest, identifier):
    review = json.loads(condition_file(state, identifier).read_text())
    row = selected_job(manifest, identifier)
    status = assessment_validation.validate_condition(row["job"], current_profile(Path(manifest["vault"])), review)
    if status == "failed":
        raise ValueError("known failed condition skips requirement retrieval/scoring")
    return review


def freeze_job(state, identifier, classified):
    manifest = load_state(state)
    reviewed_condition(state, manifest, identifier)
    row = selected_job(manifest, identifier)
    result = {"input_fingerprint": manifest["input_fingerprint"], "classified": classified,
              "requirements": freeze_requirements(row["units"], classified)}
    path = state/f"{identifier}-requirements.json"
    if path.exists():
        accepted = json.loads(path.read_text())
        # Retry explanations may vary; the accepted decisions stay frozen.
        original_units = [{key: value for key, value in unit.items() if key != 'reason'}
                          for unit in accepted['classified']['units']]
        retry_units = [{key: value for key, value in unit.items() if key != 'reason'}
                       for unit in classified['units']]
        if (accepted['input_fingerprint'] != result['input_fingerprint']
                or accepted['requirements'] != result['requirements'] or original_units != retry_units
                or {key: value for key, value in accepted['classified'].items() if key != 'units'}
                != {key: value for key, value in classified.items() if key != 'units'}):
            raise ValueError("frozen requirements cannot change; use a new scoring directory/run")
        return accepted
    write_private_json(path, result)
    return result


def build_packet(state, identifier, linked_sources=None, authorize_paid_retry=False):
    manifest = load_state(state)
    review = reviewed_condition(state, manifest, identifier)
    row = selected_job(manifest, identifier)
    frozen = json.loads((state/f"{identifier}-requirements.json").read_text())
    if frozen.get("input_fingerprint") != manifest["input_fingerprint"] or frozen["requirements"] != freeze_requirements(row["units"], frozen["classified"]):
        raise ValueError("frozen requirements are stale or changed")
    requirements = frozen["requirements"]
    notes, _ = vault.scan_vault(Path(manifest["vault"]))
    skills = sorted({skill for note in vault.eligible_notes(notes) for skill in note.skills})
    requests = [{"requirement": requirement["requirement"], "terms": [match.group() for skill in skills
                 for match in re.finditer(r"(?<!\w)"+re.escape(skill)+r"(?!\w)", requirement["requirement"], re.I)],
                 "limit": 10, "compact": False} for requirement in requirements]
    requests_path = state/f"{identifier}-requests.json"
    write_private_json(requests_path, {"requests": requests})
    retrieval_path = state/f"{identifier}-retrieval.json"
    retrieval_identity = assessment_validation.fingerprint({"inputs": manifest["input_fingerprint"], "requirements": requirements, "hybrid_search": manifest["hybrid_search"]})
    saved = json.loads(retrieval_path.read_text()) if retrieval_path.exists() else {}
    if saved.get("fingerprint") == retrieval_identity:
        retrieval = saved["retrieval"]
    else:
        def fetch():
            import contextlib
            import io
            buffer = io.StringIO()
            try:
                with contextlib.redirect_stdout(buffer):
                    vault.run_batch_search(Path(manifest["vault"]), requests_path, 10, False, manifest["hybrid_search"],
                        "text-embedding-3-small", vault.DEFAULT_SEMANTIC_MIN_SCORE,
                        vault.DEFAULT_KEYWORD_WEIGHT, vault.DEFAULT_SEMANTIC_WEIGHT, None, None)
            except vault.SemanticSearchUnavailable as error:
                raise ValueError(str(error)) from error
            result = json.loads(buffer.getvalue())
            if len(result.get("results", [])) != len(requirements):
                raise ValueError("retrieval omitted requirement results")
            return result

        if manifest['hybrid_search']:
            from paid_operations import exclusive_lock, operation_path, pending_operation, require_paid_retry
            import readiness
            base = operation_path(Path(manifest['vault']), 'query-' + retrieval_identity)
            pending = base.with_suffix('.pending.json')
            confirmed = base.with_suffix('.result.json')
            local_pending = state / (identifier + '-retrieval-pending.json')
            with exclusive_lock(base.with_suffix('.lock')):
                cached = json.loads(confirmed.read_text()) if confirmed.exists() else {}
                if confirmed.exists():
                    if not isinstance(cached, dict) or cached.get('fingerprint') != retrieval_identity or cached.get('integrity') != assessment_validation.fingerprint(cached.get('retrieval')):
                        raise ValueError('confirmed hybrid cache changed; restore verified cached results before retrying')
                    retrieval = cached['retrieval']
                    write_private_json(retrieval_path, {'fingerprint': retrieval_identity, 'retrieval': retrieval})
                else:
                    # Import legacy markers for this operation without deleting old evidence.
                    legacy = {local_pending}
                    for old in (Path(manifest['vault']).resolve().parent / '.state').rglob('*-retrieval-pending.json'):
                        marker = json.loads(old.read_text())
                        if marker.get('fingerprint') == retrieval_identity:
                            legacy.add(old)
                    require_paid_retry(pending, authorize_paid_retry=authorize_paid_retry, legacy=legacy)
                    readiness.ensure_hybrid(Path(manifest['vault']), cache_path=manifest.get('readiness_cache'),
                        authorize_paid_retry=authorize_paid_retry)
                    with pending_operation(pending, authorize_paid_retry=authorize_paid_retry, legacy=legacy):
                        write_private_json(local_pending, {'fingerprint': retrieval_identity, 'status': 'pending'})
                        retrieval = fetch()
                        write_private_json(confirmed, {'fingerprint': retrieval_identity, 'retrieval': retrieval,
                            'integrity': assessment_validation.fingerprint(retrieval)})
                        write_private_json(retrieval_path, {'fingerprint': retrieval_identity, 'retrieval': retrieval})
        else:
            retrieval = fetch()
            write_private_json(retrieval_path, {'fingerprint': retrieval_identity, 'retrieval': retrieval})
    missing = sorted({source for retrieved in retrieval["results"] for match in retrieved["matches"]
                      if match["type"] not in {"constraint", "preferences", "profile-links"}
                      for source in match["source"] if source.startswith("https://")
                      and source not in (linked_sources or {})})
    pending_path = state/f"{identifier}-sources-needed.json"
    if missing:
        pending = {"job_handle": identifier, "status": "awaiting_source_inspection", "source_urls": missing}
        write_private_json(pending_path, pending)
        return pending
    resumes = load_resumes(Path(manifest["resumes_dir"]), manifest["pdftotext"])
    contexts, sources = {}, {}
    for retrieved in retrieval["results"]:
        retrieved["matches"] = [match for match in retrieved["matches"] if match["type"] not in {"constraint", "preferences", "profile-links"}]
        for match in retrieved["matches"]:
            contexts[match["path"]] = (Path(manifest["vault"])/match["path"]).read_text()
            for source in source_excerpts(match["source"], resumes, Path(manifest["vault"]), linked_sources):
                sources[source["source"]] = source["text"]
    packet = {"job": row["job"], "input_fingerprint": manifest["input_fingerprint"],
              "condition_status": review["status"], "condition_review": review,
              "classified": frozen["classified"], "resumes": list(resumes), "resume_lines": manifest["resume_lines"],
              "requirements": requirements, "retrieval": retrieval, "verified_notes": contexts, "linked_sources": sources}
    import scoring
    packet['allowed_evidence'] = scoring.evidence_catalog(retrieval)
    write_private_json(state/f"{identifier}-packet.json", packet)
    pending_path.unlink(missing_ok=True)
    template = {key: value for key, value in packet.items() if key not in {"verified_notes", "resume_lines"}}
    template["category"] = "AI Agent"
    template["requirements"] = [{**requirement, "candidate_strength": "unknown", "candidate_reason": "",
                                 "evidence": [], "resume_strengths": {name: "missing" for name in resumes},
                                 "resume_lines": {name: [] for name in resumes}} for requirement in requirements]
    write_private_json(state/f"{identifier}-review-template.json", template)
    return packet


def trusted_assessment(state, data, vault_dir, resumes_dir):
    """Bind judgments to independently persisted original inputs and retrieval packet."""
    manifest = load_state(state)
    if Path(manifest["vault"]).resolve() != vault_dir.resolve() or Path(manifest["resumes_dir"]).resolve() != resumes_dir.resolve():
        raise ValueError("calculator paths do not match persisted assessment inputs")
    original = selected_job(manifest, assessment_validation.job_id(data["job"]))
    if original["job"] != data["job"]:
        raise ValueError("reviewed job differs from persisted original JD")
    identifier = original["job_id"]
    condition = reviewed_condition(state, manifest, identifier)
    frozen = json.loads((state/f"{identifier}-requirements.json").read_text())
    packet = json.loads((state/f"{identifier}-packet.json").read_text())
    if not isinstance(frozen, dict) or not isinstance(packet, dict):
        raise ValueError("persisted frozen requirements and packet must be objects")
    expected = freeze_requirements(original["units"], frozen.get("classified"))
    if frozen.get("input_fingerprint") != manifest["input_fingerprint"] or frozen.get("requirements") != expected:
        raise ValueError("persisted frozen requirements are stale or changed")
    for key, value in {"job": original["job"], "input_fingerprint": manifest["input_fingerprint"],
                       "condition_status": condition["status"], "condition_review": condition,
                       "classified": frozen["classified"], "requirements": expected}.items():
        if packet.get(key) != value:
            raise ValueError("persisted packet differs from trusted original inputs/frozen requirements")
    for key in ("job", "input_fingerprint", "condition_status", "condition_review", "classified", "resumes", "retrieval", "linked_sources"):
        if data.get(key) != packet.get(key):
            raise ValueError("reviewed input differs from persisted frozen assessment packet")
    scored_path = state/f"{identifier}-scored.json"
    if scored_path.exists():
        saved = json.loads(scored_path.read_text())
        current = assessment_validation.fingerprint({"manifest": manifest["fingerprint"], "condition": condition, "reviewed": score_identity(data)})
        if saved.get('status') != 'evidence_review' and saved.get("assessment_fingerprint") != current:
            raise ValueError("finalized judgments cannot change; use a new scoring directory/run")
    return expected


def score_identity(data):
    return {key: value for key, value in data.items() if key != 'suggestions'} if isinstance(data, dict) else data


def assessment_fingerprint(state, identifier, manifest):
    condition = json.loads(condition_file(state, identifier).read_text())
    reviewed_path = state/f"{identifier}-reviewed.json"
    reviewed = json.loads(reviewed_path.read_text()) if condition.get("status") != "failed" else None
    return assessment_validation.fingerprint({"manifest": manifest["fingerprint"], "condition": condition, "reviewed": score_identity(reviewed)})


def outcome_integrity(outcome):
    return assessment_validation.fingerprint({key: value for key, value in outcome.items() if key != 'integrity'})


def require_unchanged_finalized(state, manifest):
    for row in manifest["jobs"]:
        path = state/f"{row['job_id']}-scored.json"
        if path.exists():
            saved = json.loads(path.read_text())
            if saved.get('integrity') != outcome_integrity(saved):
                raise ValueError('saved assessment integrity missing or changed; prepare a new run')
            if saved.get("assessment_fingerprint") and saved.get('status') != 'evidence_review':
                try:
                    current = assessment_fingerprint(state, row["job_id"], manifest)
                except (OSError, ValueError, TypeError, AttributeError) as error:
                    raise ValueError("finalized assessment inputs changed; use a new scoring directory/run") from error
                if current != saved["assessment_fingerprint"]:
                    raise ValueError("finalized assessment cannot change; use a new scoring directory/run")


def finalize_assessment(state, log_root=None, *, allow_pending=False):
    """Account for each original job; missing/invalid output remains explicit failure."""
    import scoring
    import pipeline_log
    manifest = load_state(state)
    require_unchanged_finalized(state, manifest)
    outcomes = []
    profile = current_profile(Path(manifest["vault"])) if manifest["jobs"] else {}
    for row in manifest["jobs"]:
        identifier = row["job_id"]
        saved_path = state/f"{identifier}-scored.json"
        if saved_path.exists():
            saved = json.loads(saved_path.read_text())
            if saved.get("assessment_fingerprint") and saved.get("status") in {"qualified", "below_threshold", "condition_failed"}:
                outcomes.append(saved)
                continue
        if allow_pending and not condition_file(state, identifier).exists():
            outcomes.append({"job_id": identifier, "status": "pending"})
            continue
        try:
            review = json.loads(condition_file(state, identifier).read_text())
            condition = assessment_validation.validate_condition(row["job"], profile, review)
            if condition == "failed":
                outcome = {"job_id": identifier, "status": "condition_failed", "condition_review": review}
            else:
                if allow_pending and not (state/f"{identifier}-reviewed.json").exists():
                    outcomes.append({"job_id": identifier, "status": "pending"})
                    continue
                reviewed = json.loads((state/f"{identifier}-reviewed.json").read_text())
                if not isinstance(reviewed, dict):
                    raise ValueError("reviewed job must be a JSON object")
                if reviewed.get("job") != row["job"] or reviewed.get("condition_review") != review:
                    raise ValueError("reviewed output does not match original job or approved condition judgment")
                saved_path = state/f"{identifier}-scored.json"
                saved = json.loads(saved_path.read_text()) if saved_path.exists() else None
                result = saved['result'] if saved and saved.get('status') != 'evidence_review' and 'result' in saved else scoring.calculate(reviewed, vault=Path(manifest["vault"]), resumes_dir=Path(manifest["resumes_dir"]), pdftotext=manifest["pdftotext"], state=state)
                status = result['status']
                outcome = {"job_id": identifier, "status": status, "condition_review": review,
                           "result": result}
            outcome["assessment_fingerprint"] = assessment_fingerprint(state, identifier, manifest)
            outcome['integrity'] = outcome_integrity(outcome)
            write_private_json(state/f"{identifier}-scored.json", outcome)
        except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as error:
            outcome = {"job_id": identifier, "status": "failed", "error_type": type(error).__name__, "error": str(error)}
            if isinstance(error, scoring.InvalidSubmissionError):
                outcome.update(error_code='invalid_submission', recoverable=True, diagnostics=error.diagnostics)
        outcomes.append(outcome)
    coverage = manifest["handoff"].get("coverage", {"status": "unknown"})
    failures = sum(row["status"] == "failed" for row in outcomes)
    pending = sum(row["status"] in {"pending"} for row in outcomes)
    evidence_review = sum(row["status"] == "evidence_review" for row in outcomes)
    discovery_complete = coverage.get("status") == "completed"
    summary = {"record_type": "assessment_summary", "run_id": manifest["run_id"],
               "status": "failed" if failures else "in_progress" if pending or evidence_review else "completed" if discovery_complete else "partial",
               "retained_job_count": len(outcomes), "scored_job_count": sum("result" in row for row in outcomes),
               "failed_job_count": failures, "pending_job_count": pending, "condition_failed_count": sum(row["status"] == "condition_failed" for row in outcomes),
               "qualified_job_count": sum(row["status"] == "qualified" for row in outcomes),
               "below_threshold_job_count": sum(row["status"] == "below_threshold" for row in outcomes),
               "evidence_review_job_count": evidence_review,
               "coverage": coverage,
               "elapsed_seconds": round(time.time()-manifest["started_epoch_seconds"], 3),
               "usage_available": False, "token_usage": None, "cost_estimate_usd": None,
               "usage_scope": "Codex telemetry unavailable; CLI completed-turn finalization is separate"}
    load_state(state)  # Detect edits during assessment before publishing any results.
    write_private_json(state/"results.json", {"coverage": coverage, "jobs": outcomes})
    write_private_json(state/"summary.json", summary)
    if log_root is not None:
        path = pipeline_log.stage_path(log_root, pipeline_log.local_run_date(manifest["started_epoch_seconds"]), "scoring")
        existing = [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []
        keys = {(row.get("run_id"), row.get("job_id"), row.get("record_type"), row.get("input_fingerprint")) for row in existing}
        for outcome in outcomes:
            if outcome["status"] in {"failed", "pending", "evidence_review"}:
                continue
            base = {"run_id": summary["run_id"], "job_id": outcome["job_id"], "input_fingerprint": manifest["input_fingerprint"], "recorded_at": pipeline_log.utc_now()}
            records = [{**base, "record_type": "condition_check_job", "status": outcome["condition_review"]["status"],
                        "reason": "Codex reviewed verified profile against original JD conditions."}]
            if "result" in outcome:
                records.append({**base, "record_type": "scoring_job", "status": outcome["result"]["status"],
                                "candidate_evidence_fit": outcome["result"]["match"]["ATS_score"],
                                "reason": "Validated reviewed requirements, verified citations and resume lines.",
                                "usage_available": False, "cost_estimate_usd": None, "token_usage": None})
            for record in records:
                key = (record["run_id"], record["job_id"], record["record_type"], record["input_fingerprint"])
                if key not in keys:
                    pipeline_log.append_record(path, record); keys.add(key)
    publish_report(state, manifest, outcomes, summary)
    return summary


def publish_report(state, manifest, outcomes, summary):
    """Publish visible progress; only a complete frozen report authorizes selection."""
    unresolved = [row for row in outcomes if row['status'] in {'pending', 'failed', 'evidence_review'}]
    selectable = not unresolved
    candidates = sorted((row for row in outcomes if row['status'] == 'qualified'),
                        key=lambda row: (-row['result']['match']['ATS_score'], row['job_id']))
    entries = [{'number': number, **row, 'job': selected_job(manifest, row['job_id'])['job']}
               for number, row in enumerate(candidates, 1)]
    identity = assessment_validation.fingerprint({'manifest': manifest['fingerprint'], 'candidates': entries, 'unresolved': unresolved})
    report = {'report_id': identity, 'run_id': manifest['run_id'], 'input_fingerprint': manifest['input_fingerprint'],
              'candidates': entries, 'unresolved': unresolved, 'selectable': selectable, 'summary': summary, 'application_records_written': False}
    path = state/'report.json'
    if path.exists():
        existing = json.loads(path.read_text())
        if existing.get('selectable'):
            if existing['report_id'] != identity:
                raise ValueError('current report changed; prepare a new run')
            return existing
    write_private_json(path, report)
    lines = [f"# Candidate report {identity}", '',
             'Ready for current-report selection.' if selectable else 'INCOMPLETE — NONSELECTABLE: do not approve these candidate numbers.',
             'No application records were written.', '',
             f"Run: {manifest['run_id']} | Threshold: score > {manifest['threshold']}",
             f"Scoring run wall time: {summary['elapsed_seconds']} seconds since run preparation (includes interruptions).",
             f"Original jobs: {summary['retained_job_count']} | Qualified: {summary['qualified_job_count']} | "
             f"Below threshold: {summary['below_threshold_job_count']} | Condition failures: {summary['condition_failed_count']} | "
             f"Pending: {summary['pending_job_count']} | Evidence review: {summary.get('evidence_review_job_count', 0)} | Failed: {summary['failed_job_count']}",
             'Discovery coverage: '+json.dumps(summary['coverage'], ensure_ascii=False), '']
    if unresolved:
        lines.extend(['## Remaining work', 'Resume this saved run with the same handoff; inspect these job handles.'])
        for row in unresolved:
            lines.append(f"- {row['job_id']}: {row['status']}" + (f" — {row['error']}" if row.get('error') else ''))
            if row['status'] == 'evidence_review':
                result = row['result']
                lines.append(f"  Evidence fit: {result['score_range']['lower']}–{result['score_range']['upper']}; evidence coverage: {result['evidence_coverage_percent']}%.")
                for requirement in result['evidence_table']:
                    if requirement['candidate_strength'] == 'unknown':
                        lines.append(f"  {requirement['id']}: {requirement['requirement']} — {requirement['candidate_reason']}")
    for entry in entries:
        job = entry['job']; result = entry['result']
        lines.extend(['', f"## {entry['number']}. {job['position']} — {job['company']}", job['job_url'],
                      'Location: '+str(job.get('location') or 'not advertised'),
                      'Source: '+str(job.get('source') or 'not supplied'),
                      'Posted: '+str(job.get('date_posted') or job.get('posted_at') or job.get('posted_date') or 'not supplied'),
                      'Advertised salary: '+str(job.get('salary') or job.get('salary_text') or 'not advertised'),
                      'Contact: '+str(job.get('contact') or job.get('contact_email') or job.get('contact_details') or 'not advertised'),
                      f"Evidence fit: {result['match']['ATS_score']}",
                      'Evidence range: '+json.dumps(result.get('score_range', {'lower': result['match']['ATS_score'], 'upper': result['match']['ATS_score']})),
                      'Evidence coverage: '+str(result.get('evidence_coverage_percent', 100))+'%',
                      'Resume coverage: '+json.dumps(result['resume_coverage'], ensure_ascii=False),
                      'Condition review: '+json.dumps(entry['condition_review'], ensure_ascii=False),
                      'Brief match: '+json.dumps({strength: sum(row['candidate_strength'] == strength for row in result['evidence_table']) for strength in sorted({row['candidate_strength'] for row in result['evidence_table']})})])
        lines.extend(['', '### Complete match', '```json', json.dumps(result['match'], ensure_ascii=False, indent=2), '```'])
    target = state/'report.md'
    target.write_text('\n'.join(lines)+'\n'); target.chmod(0o600)
    return report


def prepare_run(input_path, state, vault_dir, resumes_dir, **options):
    manifest = prepare_assessment(input_path, state, vault_dir, resumes_dir, **options)
    rows = []
    for row in manifest['jobs']:
        rows.append({'job_handle': row['job_id'], 'condition': {'reviewer': 'codex', 'status': '', 'reason': '', 'clauses': []},
                     'classified': {'units': [{'id': unit['id'], 'category': '', 'priority': 1, 'reason': ''} for unit in row['units']]}})
    result = {'run_handle': str(state.resolve()), 'jobs': [{'job_handle': row['job_id'], 'job': row['job'], 'units': row['units']} for row in manifest['jobs']],
              'profile': manifest['profile'], 'resume_lines': manifest['resume_lines'], 'coverage': manifest['handoff'].get('coverage', {'status': 'unknown'}),
              'requirements_template': {'jobs': rows}}
    if not rows:
        result.update(submit_judgments(state, {'jobs': []}))
    return result


def submission_rows(manifest, submission):
    rows = submission.get('jobs') if isinstance(submission, dict) else None
    if not isinstance(rows, list):
        raise ValueError('submission must contain jobs')
    accepted, failures, seen = [], [], set()
    known = {row['job_id'] for row in manifest['jobs']}
    for index, row in enumerate(rows):
        handle = row.get('job_handle') if isinstance(row, dict) else None
        if not isinstance(handle, str) or handle not in known or handle in seen:
            failures.append({'submission_index': index, 'status': 'failed', 'error': 'invalid, unknown or duplicate job handle'})
            continue
        seen.add(handle)
        accepted.append(row)
    return accepted, failures


def coverage_reference(state, manifest):
    coverage = manifest['handoff'].get('coverage', {'status': 'unknown'})
    return {'status': coverage.get('status', 'unknown'), 'manifest_path': str((state/'manifest.json').resolve()),
            **{key: value for key, value in coverage.items() if key.endswith('_count') or key in {'failed', 'completed'}}}


def assessment_progress(state, manifest):
    outcomes = []
    for row in manifest['jobs']:
        identifier = row['job_id']
        scored = state/f'{identifier}-scored.json'
        condition = condition_file(state, identifier)
        if scored.exists():
            status = json.loads(scored.read_text())['status']
        elif condition.exists() and json.loads(condition.read_text()).get('status') == 'failed':
            status = 'condition_failed'
        else:
            status = 'pending'
        outcomes.append({'job_handle': identifier, 'status': status})
    return {'coverage': manifest['handoff'].get('coverage', {'status': 'unknown'}), 'outcomes': outcomes,
            'progress': {'original_job_count': len(outcomes), 'unresolved_job_count': sum(row['status'] in {'pending', 'failed', 'evidence_review'} for row in outcomes)}}


def require_bounded_submission(submission):
    if isinstance(submission, dict) and isinstance(submission.get('jobs'), list) and len(submission['jobs']) > 3:
        raise ValueError('Submit at most three jobs per batch; reuse the same run for the next batch')


def submit_requirements(state, submission, linked_sources=None, authorize_paid_retry=False):
    require_bounded_submission(submission)
    manifest = load_state(state)
    require_unchanged_finalized(state, manifest)
    packets, templates, awaiting_sources = [], [], []
    rows, failures = submission_rows(manifest, submission)
    for supplied in rows:
        identifier = supplied['job_handle']
        try:
            row = selected_job(manifest, identifier)
            prepared = next(job for job in manifest['prepared']['jobs'] if job['job_id'] == identifier)
            review = {**supplied['condition'], 'jd_fingerprint': prepared['jd_fingerprint'],
                      'profile_fingerprint': manifest['prepared']['profile_fingerprint']}
            condition_path = condition_file(state, identifier)
            if condition_path.exists():
                accepted = json.loads(condition_path.read_text())
                if accepted != {**review, 'reason': accepted['reason']}:
                    raise ValueError('accepted condition cannot change; prepare a new run')
                assessment_validation.validate_condition(row['job'], current_profile(Path(manifest['vault'])), review)
                review = accepted
            else:
                save_condition(state, identifier, review)
            if review['status'] == 'failed':
                continue
            freeze_job(state, identifier, supplied['classified'])
            if (state/f'{identifier}-scored.json').exists():
                packet = json.loads((state/f'{identifier}-packet.json').read_text())
                if linked_sources and any(packet['linked_sources'].get(key) != value for key, value in linked_sources.items()):
                    raise ValueError('finalized supporting sources cannot change')
            else:
                packet = build_packet(state, identifier, linked_sources, authorize_paid_retry)
            if packet.get('status') == 'awaiting_source_inspection':
                awaiting_sources.append(packet)
                continue
            import scoring
            allowed_evidence = scoring.evidence_catalog(packet['retrieval'])
            packets.append({'job_handle': identifier, 'allowed_evidence': allowed_evidence, **{key: packet[key] for key in ('job', 'requirements', 'retrieval', 'verified_notes', 'linked_sources')}})
            template = json.loads((state/f'{identifier}-review-template.json').read_text())
            templates.append({'job_handle': identifier, 'category': '', 'requirements': template['requirements'], 'allowed_evidence': allowed_evidence})
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
            failures.append({'job_handle': identifier, 'status': 'failed', 'error': str(error)})
    result = {'run_handle': str(state.resolve()), 'packets': packets, 'judgments_template': {'jobs': templates}, 'failures': failures, 'awaiting_sources': awaiting_sources}
    # Condition-only and empty batches still finish through the same validator.
    if not templates and not failures and not awaiting_sources and all(condition_file(state, row['job_id']).exists() for row in manifest['jobs']):
        result.update(submit_judgments(state, {'jobs': []}))
    result.update(assessment_progress(state, manifest))
    return result


def submit_judgments(state, submission, log_root=None):
    require_bounded_submission(submission)
    manifest = load_state(state)
    require_unchanged_finalized(state, manifest)
    rows, failures = submission_rows(manifest, submission)
    if any('suggestions' in row for row in rows):
        raise ValueError('scoring ends at the report; suggestions require approved preparation')
    # Check immutable accepted jobs for the whole batch before any mutation.
    reviewed_rows = []
    for supplied in rows:
        identifier = supplied['job_handle']
        packet_path = state/f'{identifier}-packet.json'
        if not packet_path.exists():
            continue  # The finalizer reports this original job as incomplete.
        packet = json.loads(packet_path.read_text())
        reviewed = {key: value for key, value in packet.items() if key not in {'verified_notes', 'resume_lines'}}
        if (state/f'{identifier}-reviewed.json').exists() and 'category' not in supplied and 'requirements' not in supplied:
            reviewed = json.loads((state/f'{identifier}-reviewed.json').read_text())
        reviewed.update({key: supplied[key] for key in ('category', 'requirements') if key in supplied})
        if (state/f'{identifier}-scored.json').exists():
            trusted_assessment(state, reviewed, Path(manifest['vault']), Path(manifest['resumes_dir']))
        reviewed_rows.append((identifier, reviewed))
    previous_reviews = {}
    for identifier, reviewed in reviewed_rows:
        path = state/f'{identifier}-reviewed.json'
        previous_reviews[identifier] = json.loads(path.read_text()) if path.exists() else None
        write_private_json(state/f'{identifier}-draft.json', reviewed)
        write_private_json(state/f'{identifier}-reviewed.json', reviewed)
    ledger_run = os.environ.get('PIPELINE_RUN_ID')
    if ledger_run:
        import scoring_ledger
        ledger_state = scoring_ledger.default_state_dir()
        existing = scoring_ledger.read_json_lines(scoring_ledger.run_state_path(ledger_state, ledger_run))
    summary = finalize_assessment(state, log_root or Path(manifest.get('log_root', state.resolve().parent/'logs')), allow_pending=True)
    outcomes = json.loads((state/'results.json').read_text())['jobs']
    for outcome in outcomes:
        identifier = outcome['job_id']
        if outcome['status'] == 'failed' and identifier in previous_reviews:
            previous = previous_reviews[identifier]
            path = state/f'{identifier}-reviewed.json'
            if previous is None:
                path.unlink(missing_ok=True)
            else:
                write_private_json(path, previous)
            failures.append({'job_handle': identifier, **{key: outcome[key] for key in ('error', 'error_type', 'error_code', 'recoverable', 'diagnostics') if key in outcome}})
    if ledger_run:
        recorded = {row['job_id']: row for row in existing}
        for outcome in outcomes:
            if outcome['status'] not in {'qualified', 'below_threshold'}:
                continue
            original = selected_job(manifest, outcome['job_id'])['job']
            identifier = scoring_ledger.job_id(original['job_url'])
            fit = outcome['result']['match']['ATS_score']
            if identifier in recorded:
                if recorded[identifier]['candidate_evidence_fit'] != fit or recorded[identifier]['status'] != outcome['status']:
                    raise ValueError('CLI scoring ledger conflicts with validated assessment')
                continue
            scoring_ledger.run_record(ledger_state, ledger_run, original['job_url'], original['company'], original['position'],
                                     fit, outcome['status'], 'Validated verified evidence and exact resume support against original requirements.')
    if failures:
        summary = {**summary, 'status': 'failed'}
    return {'run_handle': str(state.resolve()), 'summary': summary, 'jobs': outcomes, 'failures': failures, **assessment_progress(state, manifest)}



def inspect_jobs(state, offset=0, limit=1, *, shared=False):
    """Read a bounded page of original jobs, templates, packets and validated results."""
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 3:
        raise ValueError('inspect requires nonnegative offset and limit between 1 and 3')
    manifest = load_state(state)
    if shared:
        return {'run_handle': str(state.resolve()), 'shared_handle': manifest['input_fingerprint'],
                'profile': manifest['profile'], 'resume_lines': manifest['resume_lines'],
                'coverage': manifest['handoff'].get('coverage', {'status': 'unknown'})}
    rows = []
    for row in manifest['jobs'][offset:offset+limit]:
        identifier = row['job_id']
        item = {'job_handle': identifier, 'job': row['job'], 'units': row['units'],
                'requirements_template': {'job_handle': identifier,
                    'condition': {'reviewer': 'codex', 'status': '', 'reason': '', 'clauses': []},
                    'classified': {'units': [{'id': unit['id'], 'category': '', 'priority': 1, 'reason': ''} for unit in row['units']]}}}
        condition_path = condition_file(state, identifier)
        requirements_path = state/f'{identifier}-requirements.json'
        if condition_path.exists():
            accepted = json.loads(condition_path.read_text())
            item['requirements_template']['condition'] = {key: value for key, value in accepted.items() if key not in {'jd_fingerprint', 'profile_fingerprint'}}
            item['accepted_condition'] = accepted
        if requirements_path.exists():
            accepted = json.loads(requirements_path.read_text())
            item['requirements_template']['classified'] = accepted['classified']
            item['accepted_requirements'] = accepted['requirements']
        packet = state/f'{identifier}-packet.json'
        if packet.exists():
            item['packet'] = json.loads(packet.read_text())
            import scoring
            item['packet']['allowed_evidence'] = scoring.evidence_catalog(item['packet']['retrieval'])
            item['packet'].pop('resume_lines', None)
            template = json.loads((state/f'{identifier}-review-template.json').read_text())
            item['judgments_template'] = {'job_handle': identifier, 'category': '',
                'requirements': template['requirements'], 'allowed_evidence': item['packet']['allowed_evidence']}
        draft = state/f'{identifier}-draft.json'
        if draft.exists():
            item['draft_path'] = str(draft.resolve())
        pending_sources = state/f'{identifier}-sources-needed.json'
        if pending_sources.exists():
            item['awaiting_sources'] = json.loads(pending_sources.read_text())
        scored = state/f'{identifier}-scored.json'
        if scored.exists():
            item['outcome'] = json.loads(scored.read_text())
        rows.append(item)
    end = min(offset + limit, len(manifest['jobs']))
    return {'run_handle': str(state.resolve()), 'jobs': rows, 'shared_handle': manifest['input_fingerprint'],
            'coverage': coverage_reference(state, manifest),
            'original_job_count': len(manifest['jobs']), 'next_offset': end if end < len(manifest['jobs']) else None}


def compact_response(state, command, result):
    """Keep full output private; stdout carries handles, counts and bounded failures."""
    path = state/f'{command}-response.json'
    write_private_json(path, result)
    manifest = load_state(state)
    return {'run_handle': str(state.resolve()), 'response_path': str(path.resolve()),
            'results_path': str((state/'results.json').resolve()) if (state/'results.json').exists() else None,
            'original_job_count': len(manifest['jobs']),
            **{key: result[key] for key in ('progress', 'failures', 'awaiting_sources') if key in result},
            'coverage': coverage_reference(state, manifest),
            **{key: result[key] for key in ('destinations', 'requires_destination_duplicate_check', 'application_records_written') if key in result},
            'report_path': str((state/'report.md').resolve()) if (state/'report.md').exists() else None,
            'report_id': json.loads((state/'report.json').read_text())['report_id'] if (state/'report.json').exists() else None,
            'summary': {key: value for key, value in result.get('summary', {}).items() if key != 'coverage'}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prepare = commands.add_parser('prepare')
    prepare.add_argument('--input', type=Path, required=True)
    prepare.add_argument('--output', type=Path, required=True)
    prepare.add_argument('--vault', type=Path, default=ROOT/'career-vault')
    prepare.add_argument('--resumes-dir', type=Path, default=ROOT/'resumes')
    prepare.add_argument('--pdftotext')
    prepare.add_argument('--readiness-cache', type=Path)
    prepare.add_argument('--log-root', type=Path)
    prepare.add_argument('--hybrid-search', type=vault.parse_bool)
    prepare.add_argument('--authorize-paid-retry', action='store_true', help='only after explicit user approval')
    inspect = commands.add_parser('inspect', help='read at most three jobs with their working templates and results')
    inspect.add_argument('--run', type=Path, required=True)
    inspect.add_argument('--offset', type=int, default=0)
    inspect.add_argument('--limit', type=int, default=1)
    inspect.add_argument('--shared', action='store_true', help='inspect profile, every resume and full coverage once')
    for name in ('requirements', 'judgments'):
        command = commands.add_parser(name)
        command.add_argument('--run', type=Path, required=True)
        command.add_argument('--input', type=Path, required=True)
        if name == 'requirements':
            command.add_argument('--linked-sources', type=Path)
            command.add_argument('--authorize-paid-retry', action='store_true', help='only after explicit user approval')
        if name == 'judgments': command.add_argument('--log-root', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == 'prepare':
            result = prepare_run(args.input, args.output, args.vault, args.resumes_dir, hybrid_search=args.hybrid_search, pdftotext=args.pdftotext, readiness_cache=args.readiness_cache, log_root=args.log_root, authorize_paid_retry=args.authorize_paid_retry)
        elif args.command == 'inspect':
            result = inspect_jobs(args.run, args.offset, args.limit, shared=args.shared)
        elif args.command == 'requirements':
            result = submit_requirements(args.run, json.loads(args.input.read_text()), json.loads(args.linked_sources.read_text()) if args.linked_sources else None, args.authorize_paid_retry)
        else:
            result = submit_judgments(args.run, json.loads(args.input.read_text()), args.log_root)
        printed = result if args.command == 'inspect' else compact_response(args.output if args.command == 'prepare' else args.run, args.command, result)
        print(json.dumps(printed))
        return 1 if result.get('failures') or result.get('summary', {}).get('status') == 'failed' else 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, vault.SemanticSearchUnavailable) as error:
        parser.error(str(error))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
