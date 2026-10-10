#!/usr/bin/env python3
"""Validate original jobs and Codex-reviewed conditions; never interpret gates."""
from __future__ import annotations
import hashlib
import json


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def profile_fingerprint(profile):
    return fingerprint({key: value for key, value in profile.items() if key != "generated_at"})


def require_profile(profile):
    if not isinstance(profile, dict) or profile.get("schema_version") != 1:
        raise ValueError("condition profile is missing or unsupported")
    if not isinstance(profile.get("work_authorization"), dict) or not isinstance(profile.get("education"), list):
        raise ValueError("condition profile is incomplete")
    for name in ("work_authorization", "education"):
        source = profile.get("sources", {}).get(name, {})
        if not source.get("last_verified") or not source.get("source"):
            raise ValueError("condition profile lacks verified sources")
    return profile


def job_id(job):
    return hashlib.sha256(job["job_url"].strip().encode()).hexdigest()[:16]


def jd_fingerprint(job):
    return fingerprint({key: job[key] for key in ("company", "position", "description_text")})


def validate_condition(job, profile, review):
    require_profile(profile)
    if not isinstance(review, dict) or review.get("reviewer") != "codex":
        raise ValueError("condition requires an explicit Codex review")
    if review.get("jd_fingerprint") != jd_fingerprint(job) or review.get("profile_fingerprint") != profile_fingerprint(profile):
        raise ValueError("condition review has stale JD or profile inputs")
    status = review.get("status")
    if status not in {"passed", "manual_review", "failed"} or not isinstance(review.get("reason"), str) or not review["reason"].strip():
        raise ValueError("condition review needs a status and reason")
    clauses = review.get("clauses")
    if not isinstance(clauses, list):
        raise ValueError("condition review needs original clauses (empty only when no condition applies)")
    for clause in clauses:
        if not isinstance(clause, dict) or clause.get("kind") not in {"work_rights", "degree"}:
            raise ValueError("only work-rights or required-degree clauses may gate a job")
        if not isinstance(clause.get("wording"), str) or not clause["wording"].strip() or clause["wording"] not in job["position"] + "\n" + job["description_text"]:
            raise ValueError("condition clause must preserve original JD wording")
        if clause.get("status") not in {"passed", "manual_review", "failed"} or not isinstance(clause.get("reason"), str) or not clause["reason"].strip():
            raise ValueError("every condition clause needs a judgment and reason")
        fields = clause.get("profile_fields")
        if not isinstance(fields, list) or not fields:
            raise ValueError("condition clause needs verified profile field references")
        for field in fields:
            if field == "education" and clause["kind"] == "degree":
                continue
            if not isinstance(field, str) or clause["kind"] != "work_rights" or not field.startswith("work_authorization.") or field.split(".", 1)[1] not in profile["work_authorization"]:
                raise ValueError("condition clause references an unknown verified profile field")
    expected = "failed" if any(c["status"] == "failed" for c in clauses) else "manual_review" if any(c["status"] == "manual_review" for c in clauses) else "passed"
    if status != expected:
        raise ValueError("condition overall status conflicts with reviewed clauses")
    return status


def prepare_jobs(jobs, profile):
    """Validate unique original jobs and return their immutable input identities."""
    require_profile(profile)
    if isinstance(jobs, dict):
        jobs = jobs.get("jobs")
    if not isinstance(jobs, list):
        raise ValueError("input must be jobs array or object with jobs")
    rows, seen = [], set()
    for job in jobs:
        if not isinstance(job, dict) or any(not isinstance(job.get(key), str) or not job[key].strip() for key in ("job_url", "company", "position", "description_text")):
            raise ValueError("every job needs URL, company, position and full description")
        identifier = job_id(job)
        if identifier in seen:
            raise ValueError("duplicate canonical job URL")
        seen.add(identifier)
        rows.append({"job_id": identifier, "jd_fingerprint": jd_fingerprint(job)})
    return {"schema_version": 1, "profile_fingerprint": profile_fingerprint(profile), "jobs": rows}
