#!/usr/bin/env python3
"""Calculate fit and resume scores from reviewed requirement judgments."""

from __future__ import annotations
from pathlib import Path
import sys
WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(WORKSPACE_ROOT / "scripts"))


from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from vault_evidence import build_candidates, scan_vault
import assessment as support
import assessment_validation


PROJECT_ROOT = WORKSPACE_ROOT
BUDGETS = {"Skills": 45, "Experience": 35, "Domain": 20}
STRENGTHS = {"direct": Decimal(1), "strong_transfer": Decimal("0.85"),
             "partial_transfer": Decimal("0.5"), "missing": Decimal(0),
             "unknown": Decimal(0), "transferable": Decimal("0.5")}
RESUME_STRENGTHS = {key: value for key, value in STRENGTHS.items() if key != "unknown"}
CATEGORIES = {"AI Agent", "Computer Vision", "Hybrid"}


def policy():
    return {"version": 2, "budgets": BUDGETS,
            "strengths": {key: str(value) for key, value in STRENGTHS.items()},
            "unknown": "0–100% range; review when qualification depends on it"}


class InvalidSubmissionError(ValueError):
    """Working judgment fields can be corrected against the saved packet."""
    def __init__(self, diagnostics):
        self.diagnostics = diagnostics
        super().__init__('invalid judgment submission: ' + '; '.join(row['message'] for row in diagnostics))


class CitationValidationError(InvalidSubmissionError):
    """A repairable judgment error; never relax verification to accept it."""
    def __init__(self, diagnostics):
        self.diagnostics = diagnostics
        ValueError.__init__(self, "scored citation was not retrieved from current verified evidence: "
                            + "; ".join(f"{row['requirement_id']}: {row['citation']}" for row in diagnostics))


def evidence_catalog(retrieval):
    import hashlib
    import json
    catalog = {}
    for row in retrieval.get('results', []):
        for match in row.get('matches', []):
            key = (match['path'], match['heading'])
            identifier = 'ev_' + hashlib.sha256(json.dumps(key, ensure_ascii=False).encode()).hexdigest()
            catalog[identifier] = {'evidence_id': identifier, **{key: match[key] for key in ('path', 'heading', 'text', 'source')}}
    return list(catalog.values())


def qualification_threshold():
    import yaml
    threshold = yaml.safe_load((PROJECT_ROOT/"config/search_targets.yaml").read_text())["ats_threshold_exclusive"]
    if type(threshold) is not int or not 0 <= threshold <= 100:
        raise ValueError("qualification threshold must be an integer from 0 to 100")
    return threshold


def education_only(text: str) -> bool:
    import re
    # A qualification or its equivalent remains a gate, never a scoring requirement.
    degree = re.search(r"\b(?:bachelor(?:['’]s)?|master(?:['’]s)?|ph\.?d|doctorate|doctoral|tertiary\s+(?:education|qualifications?)|degree|diploma)\b", text, re.I)
    if not degree or re.search(r"\bdegree\s+of\b",text,re.I):
        return False
    other = re.search(r"\b(?:\d+\s*\+?\s*years?|experience\s+(?:in|with|of|using)|proven|demonstrated|ability\s+to|knowledge\s+of|skills\s+in|familiarity|expertise|proficien|certif(?:ication|ied)|licen[cs]e|key\s+responsibilities)\w*", text, re.I)
    return other is None


def nearest_integer(value: Decimal) -> int:
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def display_points(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


def eligible_citations(vault: Path) -> dict[tuple[str, str], tuple[str, ...]]:
    notes, errors = scan_vault(vault)
    if errors:
        raise ValueError("vault contains an unreadable evidence note")
    return {
        (candidate.note.path.as_posix(), candidate.section.heading): candidate.note.sources
        for candidate in build_candidates(notes)
    }


def require_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty text")
    return value.strip()


def calculate(data: Any, *, state: Path, vault: Path, resumes_dir: Path, pdftotext: str | None = None) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("score input must be a JSON object")
    job = data.get("job")
    if not isinstance(job, dict) or any(not isinstance(job.get(key), str) or not job[key].strip() for key in ("company", "position", "description_text", "job_url")):
        raise ValueError("score input requires the complete original job")
    if data.get("input_fingerprint") != support.evidence_fingerprint(vault, resumes_dir):
        raise ValueError("assessment inputs changed; review current evidence/profile/resumes again")
    profile = support.current_profile(vault)
    reviewed_condition = assessment_validation.validate_condition(job, profile, data.get("condition_review"))
    if data.get("condition_status") != reviewed_condition:
        raise ValueError("condition status conflicts with Codex review")
    frozen = support.trusted_assessment(state, data, vault, resumes_dir)
    if support.load_state(state).get("scoring_policy") != policy():
        raise ValueError("scoring policy changed; prepare a new scoring directory/run")
    raw_rows = data.get("requirements")
    if not isinstance(raw_rows, list) or any(not isinstance(row, dict) or not isinstance(row.get("id"), str) for row in raw_rows):
        raise ValueError("requirements must preserve every frozen requirement")
    expected = {row["id"]: row for row in frozen}
    if len(raw_rows) != len(frozen) or {row.get("id") for row in raw_rows} != set(expected):
        raise ValueError("Judgments omitted, duplicated, or invented frozen requirement IDs")
    for row in raw_rows:
        if any(row.get(key) != value for key, value in expected[row["id"]].items()):
            raise ValueError("reviewed requirement differs from original frozen JD wording/category/priority")
    extracted = support.load_resumes(resumes_dir, pdftotext)
    actual_lines = {name: {row["id"]: row["text"] for row in support.units_from_jd(text)} for name, text in extracted.items()}
    if not isinstance(data.get("resumes"), list) or any(not isinstance(name, str) for name in data["resumes"]):
        raise ValueError("resumes must list current PDF filenames")
    if set(data["resumes"]) != set(extracted):
        raise ValueError("score input must assess every current extractable resume")
    if not isinstance(data.get("retrieval"), dict):
        raise ValueError("retrieval must be a batch result object")
    retrieval = data["retrieval"].get("results")
    if not isinstance(retrieval, list) or any(not isinstance(row, dict) for row in retrieval) or len(retrieval) != len(frozen) or any(row.get("requirement") != requirement["requirement"] for row, requirement in zip(retrieval, frozen)):
        raise ValueError("retrieval must include every original frozen requirement wording")
    linked_sources = data.get("linked_sources", {})
    if not isinstance(linked_sources, dict) or any(not isinstance(key, str) or not isinstance(value, str) for key, value in linked_sources.items()):
        raise ValueError("linked source excerpts must map source names to inspected text")
    notes, errors = scan_vault(vault)
    if errors:
        raise ValueError("vault contains unreadable evidence")
    candidates = {(candidate.note.path.as_posix(), candidate.section.heading): candidate
                  for candidate in build_candidates(notes) if candidate.note.note_type not in {"constraint", "preferences", "profile-links"}}
    retrieved_citations = {}
    for retrieved in retrieval:
        if not isinstance(retrieved.get("matches"), list):
            raise ValueError("retrieval matches must be an array")
        for match in retrieved["matches"]:
            if not isinstance(match, dict) or not isinstance(match.get("path"), str) or not isinstance(match.get("heading"), str):
                raise ValueError("retrieved citation needs path and heading")
            key = (match.get("path"), match.get("heading"))
            candidate = candidates.get(key)
            if candidate is None or match.get("text") != candidate.section.text or match.get("source") != list(candidate.note.sources):
                raise ValueError("retrieved citation is unverified, changed, or missing")
            retrieved_citations[key] = candidate
    catalog = {row['evidence_id']: row for row in evidence_catalog(data['retrieval'])}
    citation_errors = []
    for requirement in data.get('requirements', []):
        if not isinstance(requirement, dict) or not isinstance(requirement.get('evidence', []), list):
            continue
        for item in requirement.get('evidence', []):
            if not isinstance(item, dict):
                continue
            entry = catalog.get(item.get('evidence_id')) if 'evidence_id' in item else None
            key = (entry['path'], entry['heading']) if entry else (item.get('path'), item.get('heading'))
            if ('evidence_id' in item and (entry is None or any(field in item and item[field] != entry[field] for field in ('path', 'heading')))) or key not in retrieved_citations:
                citation_errors.append({'requirement_id': requirement.get('id'), 'citation': item,
                                        'allowed_evidence_ids': list(catalog), 'error_code': 'citation_not_retrieved'})
    if citation_errors:
        raise CitationValidationError(citation_errors)
    judgment_errors = []
    def invalid(requirement_id, field, message, **details):
        judgment_errors.append({'requirement_id': requirement_id, 'field': field,
                                'error_code': 'invalid_judgment_field', 'message': message, **details})
    if not isinstance(data.get('category'), str) or data['category'] not in CATEGORIES:
        invalid(None, 'category', 'category must be AI Agent, Computer Vision, or Hybrid', allowed_values=sorted(CATEGORIES))
    for requirement in raw_rows:
        identifier = requirement['id']
        if not isinstance(requirement.get('candidate_strength'), str) or requirement['candidate_strength'] not in STRENGTHS:
            invalid(identifier, 'candidate_strength', 'invalid candidate strength', allowed_values=list(STRENGTHS))
        if not isinstance(requirement.get('candidate_reason'), str) or not requirement['candidate_reason'].strip():
            invalid(identifier, 'candidate_reason', 'candidate judgment reason must be nonempty text')
        evidence = requirement.get('evidence', [])
        if not isinstance(evidence, list) or any(not isinstance(item, dict) for item in evidence):
            invalid(identifier, 'evidence', 'evidence must be an array of catalog references')
        elif isinstance(requirement.get('candidate_strength'), str) and STRENGTHS.get(requirement['candidate_strength'], Decimal(0)) > 0 and not evidence:
            invalid(identifier, 'evidence', 'positive candidate judgment needs verified evidence', allowed_evidence_ids=list(catalog))
        strengths = requirement.get('resume_strengths')
        if not isinstance(strengths, dict) or set(strengths) != set(extracted):
            invalid(identifier, 'resume_strengths', 'every current resume needs a strength', required_resumes=list(extracted))
        elif any(value not in RESUME_STRENGTHS for value in strengths.values() if isinstance(value, str)) or any(not isinstance(value, str) for value in strengths.values()):
            invalid(identifier, 'resume_strengths', 'invalid resume strength; inspect the current resume', allowed_values=list(RESUME_STRENGTHS))
        line_ids = requirement.get('resume_lines')
        if not isinstance(line_ids, dict) or set(line_ids) != set(extracted):
            invalid(identifier, 'resume_lines', 'every current resume needs supporting line IDs', required_resumes=list(extracted))
        else:
            for name, indices in line_ids.items():
                if not isinstance(indices, list) or any(type(index) is not int or index not in actual_lines[name] for index in indices) or len(indices) != len(set(indices)):
                    invalid(identifier, 'resume_lines', 'invalid current resume excerpt line ID', resume=name, allowed_line_ids=list(actual_lines[name]))
                elif isinstance(strengths, dict) and isinstance(strengths.get(name), str) and strengths[name] in STRENGTHS and (strengths[name] == 'missing') != (not indices):
                    invalid(identifier, 'resume_lines', 'positive resume judgments need lines; missing judgments must have no lines', resume=name)
    if judgment_errors:
        raise InvalidSubmissionError(judgment_errors)
    threshold = qualification_threshold()
    condition = data.get("condition_status")
    if not isinstance(condition, str) or condition not in {"passed", "manual_review"}:
        raise ValueError("a failed or missing condition cannot receive fit or resume scores")
    category = data.get("category")
    if not isinstance(category, str) or category not in CATEGORIES:
        raise ValueError("category must be AI Agent, Computer Vision, or Hybrid")
    resumes = data.get("resumes")
    if not isinstance(resumes, list) or len(resumes) < 2 or any(not isinstance(name, str) for name in resumes):
        raise ValueError("resumes must list at least two distinct PDF filenames")
    if len(resumes) != len(set(resumes)):
        raise ValueError("resumes must list at least two distinct PDF filenames")
    for resume in resumes:
        if not isinstance(resume, str) or Path(resume).name != resume or not resume.lower().endswith(".pdf"):
            raise ValueError("resume entries must be PDF filenames in resumes/")
        if not (resumes_dir / resume).is_file():
            raise ValueError(f"resume PDF does not exist: {resume}")

    requirements = data.get("requirements")
    if not isinstance(requirements, list) or not requirements:
        raise ValueError("requirements must be a nonempty array")
    citations = eligible_citations(vault)
    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    category_priorities = {name: 0 for name in BUDGETS}
    for index, requirement in enumerate(requirements):
        if not isinstance(requirement, dict):
            raise ValueError(f"requirement {index} must be an object")
        identifier = require_text(requirement.get("id"), f"requirement {index} id")
        if identifier in seen_ids:
            raise ValueError(f"duplicate requirement id: {identifier}")
        seen_ids.add(identifier)
        wording = require_text(requirement.get("requirement"), f"requirement {identifier} wording")
        if education_only(wording):
            raise ValueError("Education-only requirements cannot earn scoring points")
        component = requirement.get("category")
        if not isinstance(component, str) or component not in BUDGETS:
            raise ValueError(f"requirement {identifier} has an invalid scoring category")
        priority = requirement.get("priority")
        if type(priority) is not int or priority not in {1, 2, 3}:
            raise ValueError(f"requirement {identifier} priority must be 1, 2, or 3")
        strength = requirement.get("candidate_strength")
        if not isinstance(strength, str) or strength not in STRENGTHS:
            raise ValueError(f"requirement {identifier} has an invalid candidate strength")
        raw_evidence = requirement.get("evidence", [])
        if not isinstance(raw_evidence, list):
            raise ValueError(f"requirement {identifier} evidence must be an array")
        if STRENGTHS[strength] > 0 and not raw_evidence:
            raise ValueError(f"requirement {identifier} awards points without a vault citation")
        reason = require_text(requirement.get("candidate_reason"), "candidate judgment reason")
        resolved: list[dict[str, Any]] = []
        for item in raw_evidence:
            if not isinstance(item, dict):
                raise ValueError(f"requirement {identifier} has an invalid citation")
            entry = catalog[item['evidence_id']] if 'evidence_id' in item else item
            path = require_text(entry.get("path"), "citation path")
            heading = require_text(entry.get("heading"), "citation heading")
            source = citations.get((path, heading))
            if (path, heading) not in retrieved_citations:
                raise ValueError("scored citation was not retrieved from current verified evidence")
            support.source_excerpts(list(source or []), extracted, vault, linked_sources)
            if source is None:
                raise ValueError(f"requirement {identifier} cites an unverified or missing vault section")
            resolved.append({"path": path, "heading": heading, "source": list(source)})
        resume_strengths = requirement.get("resume_strengths")
        if not isinstance(resume_strengths, dict) or set(resume_strengths) != set(resumes):
            raise ValueError(f"requirement {identifier} needs a strength for every resume")
        if any(not isinstance(value, str) or value not in RESUME_STRENGTHS for value in resume_strengths.values()):
            raise ValueError(f"requirement {identifier} has an invalid resume strength")
        line_ids = requirement.get("resume_lines")
        if not isinstance(line_ids, dict) or set(line_ids) != set(resumes):
            raise ValueError("every resume judgment needs supporting line IDs")
        excerpts = {}
        for name in resumes:
            indices = line_ids[name]
            if not isinstance(indices, list) or any(type(index) is not int or index not in actual_lines[name] for index in indices) or len(indices) != len(set(indices)):
                raise ValueError("invalid current resume excerpt line ID")
            if (resume_strengths[name] == "missing") != (not indices):
                raise ValueError("positive resume judgments need lines; missing judgments must have no lines")
            excerpts[name] = [actual_lines[name][index] for index in indices]
        rows.append({
            "id": identifier,
            "requirement": wording,
            "category": component,
            "priority": priority,
            "candidate_strength": strength,
            "candidate_reason": reason,
            "resume_lines": line_ids,
            "resume_excerpts": excerpts,
            "evidence": resolved,
            "resume_strengths": resume_strengths,
        })
        category_priorities[component] += priority

    present = [name for name in BUDGETS if category_priorities[name]]
    original_total = sum(BUDGETS[name] for name in present)
    effective_budgets = {
        name: Decimal(100) * Decimal(BUDGETS[name]) / Decimal(original_total)
        for name in present
    }
    candidate_total = Decimal(0)
    unknown_points = Decimal(0)
    resume_totals = {name: Decimal(0) for name in resumes}
    evidence_table: list[dict[str, Any]] = []
    for row in rows:
        component = row["category"]
        allocated = effective_budgets[component] * Decimal(row["priority"]) / Decimal(category_priorities[component])
        candidate_earned = allocated * STRENGTHS[row["candidate_strength"]]
        candidate_total += candidate_earned
        if row["candidate_strength"] == "unknown":
            unknown_points += allocated
        resume_earned = {}
        for resume in resumes:
            earned = allocated * STRENGTHS[row["resume_strengths"][resume]]
            resume_totals[resume] += earned
            resume_earned[resume] = display_points(earned)
        evidence_table.append({
            **row,
            "allocated_points": display_points(allocated),
            "candidate_earned_points": display_points(candidate_earned),
            "candidate_possible_points": display_points(allocated if row["candidate_strength"] == "unknown" else candidate_earned),
            "resume_earned_points": resume_earned,
        })

    coverage = {name: nearest_integer(total) for name, total in resume_totals.items()}
    high_priority_coverage = {
        name: tuple(
            sum(row["priority"] == priority and row["resume_strengths"][name] != "missing" for row in rows)
            for priority in (3, 2, 1)
        )
        for name in resumes
    }
    recommended = min(
        resumes,
        key=lambda name: (-coverage[name], tuple(-count for count in high_priority_coverage[name]), name),
    )
    fit = nearest_integer(candidate_total)
    upper = nearest_integer(candidate_total + unknown_points)
    status = "qualified" if fit > threshold else "evidence_review" if upper > threshold else "below_threshold"
    return {
        "schema_version": 2,
        "scoring_policy": policy(),
        "condition_status": condition,
        "match": {"category": category, "recommended_resume": recommended, "ATS_score": fit},
        "resume_coverage": coverage,
        "status": status,
        "score_range": {"lower": fit, "upper": upper},
        "evidence_coverage_percent": display_points(Decimal(100) - unknown_points),
        "unknown_requirements": [row["id"] for row in rows if row["candidate_strength"] == "unknown"],
        "category_budgets": {name: display_points(value) for name, value in effective_budgets.items()},
        "evidence_table": evidence_table,
    }
