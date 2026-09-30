#!/usr/bin/env python3
"""Write privacy-safe daily discovery, scoring, suggestion, and storage logs."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


LOCAL_ZONE = ZoneInfo("Australia/Melbourne")
DISCOVERY_OUTCOMES = {"fetch", "reject", "retain"}
OBSIDIAN_STATUSES = {"written", "failed", "skipped"}
NOTION_STATUSES = {"confirmed", "failed", "skipped"}
SUCCESS_STATUSES = {"written", "confirmed"}
SCORING_STATUSES = {"qualified", "below_threshold", "ineligible"}


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_log_root() -> Path:
    return project_root() / "logs"


def default_state_dir() -> Path:
    return project_root() / ".state" / "pipeline-logs"


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def compact(value: str, maximum: int = 240) -> str:
    normalized = " ".join(value.split())
    if len(normalized) > maximum:
        raise ValueError(f"value must be at most {maximum} characters")
    return normalized


def parse_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False
    raise ValueError(f"invalid boolean value: {value!r}")


def require_job_id(job_id: str | None, job_url: str | None) -> str:
    if job_id and job_id.strip():
        return compact(job_id.strip(), 120)
    if job_url and job_url.strip():
        return hashlib.sha256(job_url.strip().encode("utf-8")).hexdigest()[:16]
    raise ValueError("provide --job-id or --job-url")


def run_state_path(state_dir: Path, run_id: str) -> Path:
    if not run_id or any(
        character not in "-_abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        for character in run_id
    ):
        raise ValueError("run id may contain only letters, numbers, hyphens, and underscores")
    return state_dir / f"{run_id}.json"


def local_run_date(started_epoch_seconds: float) -> str:
    return datetime.fromtimestamp(started_epoch_seconds, LOCAL_ZONE).strftime("%d-%m-%Y")


def load_manifest(state_dir: Path, run_id: str) -> dict[str, Any]:
    path = run_state_path(state_dir, run_id)
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(f"pipeline run has not been initialized: {run_id}") from error
    if not isinstance(manifest, dict) or not manifest.get("run_date"):
        raise ValueError(f"invalid pipeline run manifest: {path}")
    return manifest


def stage_path(log_root: Path, run_date: str, stage: str) -> Path:
    if stage not in {"discovery", "scoring", "suggestion", "storage"}:
        raise ValueError(f"unsupported pipeline stage: {stage}")
    return log_root / run_date / f"{stage}.jsonl"


def append_record(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.seek(0, os.SEEK_END)
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
            handle.flush()
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def context(args: argparse.Namespace) -> tuple[dict[str, Any], Path]:
    manifest = load_manifest(args.state_dir, args.run_id)
    return manifest, stage_path(args.log_root, str(manifest["run_date"]), args.stage)


def base_record(manifest: dict[str, Any], record_type: str) -> dict[str, Any]:
    return {
        "record_type": record_type,
        "run_id": manifest["run_id"],
        "run_date": manifest["run_date"],
        "recorded_at": utc_now(),
    }


def run_init(args: argparse.Namespace) -> int:
    started = args.started_epoch_seconds
    run_date = local_run_date(started)
    manifest = {
        "run_id": args.run_id,
        "run_date": run_date,
        "started_at": datetime.fromtimestamp(started, UTC).isoformat(timespec="seconds"),
        "write_notion": parse_bool(args.write_notion),
        "write_obsidian": parse_bool(args.write_obsidian),
        "created_at": utc_now(),
    }
    path = run_state_path(args.state_dir, args.run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ValueError(f"pipeline log manifest already exists: {args.run_id}")
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    for stage in ("discovery", "scoring", "suggestion", "storage"):
        target = stage_path(args.log_root, run_date, stage)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch(exist_ok=True)
    print(f"Pipeline logs initialized: {args.log_root / run_date}")
    return 0


def run_discovery_job(args: argparse.Namespace) -> int:
    manifest, path = context(args)
    outcome = args.outcome
    record = base_record(manifest, "discovery_job")
    record.update(
        {
            "platform": compact(args.platform, 80),
            "job_id": require_job_id(args.job_id, args.job_url),
            "outcome": outcome,
        }
    )
    if args.reason:
        record["reason"] = compact(args.reason)
    append_record(path, record)
    return 0


def run_discovery_summary(args: argparse.Namespace) -> int:
    manifest, path = context(args)
    counts = {
        "fetch": args.fetch,
        "reject": args.reject,
        "retain": args.retain,
    }
    if any(value < 0 for value in counts.values()):
        raise ValueError("discovery counts must be non-negative")
    record = base_record(manifest, "discovery_summary")
    record.update(
        {
            "platform": compact(args.platform, 80),
            "counts": counts,
            "total": sum(counts.values()),
            "outcomes_mutually_exclusive": True,
        }
    )
    if args.error:
        record["error"] = compact(args.error)
    append_record(path, record)
    return 0


def usage_payload(args: argparse.Namespace) -> dict[str, int | None]:
    values = {
        "input_tokens": args.input_tokens,
        "cached_input_tokens": args.cached_input_tokens,
        "output_tokens": args.output_tokens,
        "reasoning_output_tokens": args.reasoning_output_tokens,
    }
    for name, value in values.items():
        if value is not None and value < 0:
            raise ValueError(f"{name} must be non-negative")
    return values


def run_suggestion(args: argparse.Namespace) -> int:
    manifest, path = context(args)
    cost = args.cost_estimate_usd
    elapsed_seconds = getattr(args, "elapsed_seconds", None)
    if cost is not None and cost < 0:
        raise ValueError("cost estimate must be non-negative")
    if elapsed_seconds is not None and elapsed_seconds < 0:
        raise ValueError("elapsed seconds must be non-negative")
    record = base_record(manifest, "suggestion_job")
    record.update(
        {
            "job_id": require_job_id(args.job_id, args.job_url),
            "company": compact(args.company, 120) if args.company else None,
            "position": compact(args.position, 120) if args.position else None,
            "status": args.status,
            "token_usage": usage_payload(args),
            "cost_estimate_usd": cost,
            "elapsed_seconds": elapsed_seconds,
            "usage_available": any(
                value is not None
                for value in (
                    args.input_tokens,
                    args.cached_input_tokens,
                    args.output_tokens,
                    args.reasoning_output_tokens,
                    cost,
                    elapsed_seconds,
                )
            ),
        }
    )
    append_record(path, record)
    return 0


def run_scoring_job(args: argparse.Namespace) -> int:
    manifest, path = context(args)
    if args.score < 0 or args.score > 100:
        raise ValueError("score must be between 0 and 100")
    if args.status not in SCORING_STATUSES:
        raise ValueError(f"invalid scoring status: {args.status}")
    if args.cost_estimate_usd is not None and args.cost_estimate_usd < 0:
        raise ValueError("cost estimate must be non-negative")
    if args.elapsed_seconds is not None and args.elapsed_seconds < 0:
        raise ValueError("elapsed seconds must be non-negative")
    record = base_record(manifest, "scoring_job")
    record.update(
        {
            "job_id": require_job_id(args.job_id, args.job_url),
            "company": compact(args.company, 120),
            "position": compact(args.position, 120),
            "candidate_evidence_fit": args.score,
            "status": args.status,
            "reason": compact(args.reason, 240),
            "token_usage": usage_payload(args),
            "cost_estimate_usd": args.cost_estimate_usd,
            "elapsed_seconds": args.elapsed_seconds,
            "usage_available": any(
                value is not None
                for value in (
                    args.input_tokens,
                    args.cached_input_tokens,
                    args.output_tokens,
                    args.reasoning_output_tokens,
                    args.cost_estimate_usd,
                    args.elapsed_seconds,
                )
            ),
        }
    )
    append_record(path, record)
    return 0


def destination_result(requested: bool, status: str, reference: str | None, field: str) -> dict[str, Any]:
    if not requested:
        status = "skipped"
    allowed = OBSIDIAN_STATUSES if field == "obsidian" else NOTION_STATUSES
    if status not in allowed:
        raise ValueError(f"invalid {field} status: {status}")
    return {
        "requested": requested,
        "status": status,
        "success": status in SUCCESS_STATUSES,
        "reference": compact(reference, 240) if reference else None,
    }


def run_storage_job(args: argparse.Namespace) -> int:
    manifest, path = context(args)
    obsidian_requested = parse_bool(args.write_obsidian)
    notion_requested = parse_bool(args.write_notion)
    record = base_record(manifest, "storage_job")
    record.update(
        {
            "job_id": require_job_id(args.job_id, args.job_url),
            "company": compact(args.company, 120) if args.company else None,
            "position": compact(args.position, 120) if args.position else None,
            "approved": parse_bool(args.approved),
            "destinations": {
                "obsidian": destination_result(
                    obsidian_requested, args.obsidian_status, args.obsidian_reference, "obsidian"
                ),
                "notion": destination_result(
                    notion_requested, args.notion_status, args.notion_reference, "notion"
                ),
            },
        }
    )
    append_record(path, record)
    return 0


def run_storage_summary(args: argparse.Namespace) -> int:
    manifest, path = context(args)
    records: list[dict[str, Any]] = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                value = json.loads(line)
                if value.get("record_type") == "storage_job":
                    records.append(value)

    approved = [record for record in records if record.get("approved") is True]
    destination_results: dict[str, dict[str, Any]] = {}
    for destination in ("obsidian", "notion"):
        requested = sum(
            bool(record.get("destinations", {}).get(destination, {}).get("requested"))
            for record in approved
        )
        written = sum(
            record.get("destinations", {}).get(destination, {}).get("status") in SUCCESS_STATUSES
            for record in approved
        )
        skipped = sum(
            record.get("destinations", {}).get(destination, {}).get("status") == "skipped"
            for record in approved
        )
        failed = sum(
            record.get("destinations", {}).get(destination, {}).get("status") == "failed"
            for record in approved
        )
        destination_results[destination] = {
            "requested": requested,
            "written_or_confirmed": written,
            "skipped": skipped,
            "failed": failed,
            "all_requested_successful": failed == 0 and written == requested,
        }

    record = base_record(manifest, "storage_summary")
    record.update(
        {
            "approved_total": len(approved),
            "storage_job_records": len(records),
            "destinations": destination_results,
            "all_requested_writes_successful": all(
                value["all_requested_successful"] for value in destination_results.values()
            ),
        }
    )
    append_record(path, record)
    return 0


def add_context_arguments(parser: argparse.ArgumentParser, stage: str) -> None:
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--stage", default=stage, choices=[stage])
    parser.add_argument("--log-root", type=Path, default=default_log_root())
    parser.add_argument("--state-dir", type=Path, default=default_state_dir())


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init")
    init.add_argument("--run-id", required=True)
    init.add_argument("--started-epoch-seconds", required=True, type=float)
    init.add_argument("--write-notion", default="false")
    init.add_argument("--write-obsidian", default="false")
    init.add_argument("--log-root", type=Path, default=default_log_root())
    init.add_argument("--state-dir", type=Path, default=default_state_dir())

    discovery_job = subparsers.add_parser("discovery-job")
    add_context_arguments(discovery_job, "discovery")
    discovery_job.add_argument("--platform", required=True)
    discovery_job.add_argument("--job-id")
    discovery_job.add_argument("--job-url")
    discovery_job.add_argument("--outcome", required=True, choices=sorted(DISCOVERY_OUTCOMES))
    discovery_job.add_argument("--reason")

    discovery_summary = subparsers.add_parser("discovery-summary")
    add_context_arguments(discovery_summary, "discovery")
    discovery_summary.add_argument("--platform", required=True)
    discovery_summary.add_argument("--fetch", type=int, default=0)
    discovery_summary.add_argument("--reject", type=int, default=0)
    discovery_summary.add_argument("--retain", type=int, default=0)
    discovery_summary.add_argument("--error")

    suggestion = subparsers.add_parser("suggestion")
    add_context_arguments(suggestion, "suggestion")
    suggestion.add_argument("--job-id")
    suggestion.add_argument("--job-url")
    suggestion.add_argument("--company")
    suggestion.add_argument("--position")
    suggestion.add_argument("--status", choices=("completed", "failed", "skipped"), default="completed")
    for field in ("input-tokens", "cached-input-tokens", "output-tokens", "reasoning-output-tokens"):
        suggestion.add_argument(f"--{field}", dest=field.replace("-", "_"), type=int)
    suggestion.add_argument("--cost-estimate-usd", type=float)
    suggestion.add_argument("--elapsed-seconds", type=float)

    scoring_job = subparsers.add_parser("scoring-job")
    add_context_arguments(scoring_job, "scoring")
    scoring_job.add_argument("--job-id")
    scoring_job.add_argument("--job-url")
    scoring_job.add_argument("--company", required=True)
    scoring_job.add_argument("--position", required=True)
    scoring_job.add_argument("--score", required=True, type=int)
    scoring_job.add_argument("--status", required=True, choices=sorted(SCORING_STATUSES))
    scoring_job.add_argument("--reason", required=True)
    for field in ("input-tokens", "cached-input-tokens", "output-tokens", "reasoning-output-tokens"):
        scoring_job.add_argument(f"--{field}", dest=field.replace("-", "_"), type=int)
    scoring_job.add_argument("--cost-estimate-usd", type=float)
    scoring_job.add_argument("--elapsed-seconds", type=float)

    storage_job = subparsers.add_parser("storage-job")
    add_context_arguments(storage_job, "storage")
    storage_job.add_argument("--job-id")
    storage_job.add_argument("--job-url")
    storage_job.add_argument("--company")
    storage_job.add_argument("--position")
    storage_job.add_argument("--approved", default="true")
    storage_job.add_argument("--write-obsidian", default="false")
    storage_job.add_argument("--obsidian-status", choices=sorted(OBSIDIAN_STATUSES), default="skipped")
    storage_job.add_argument("--obsidian-reference")
    storage_job.add_argument("--write-notion", default="false")
    storage_job.add_argument("--notion-status", choices=sorted(NOTION_STATUSES), default="skipped")
    storage_job.add_argument("--notion-reference")

    storage_summary = subparsers.add_parser("storage-summary")
    add_context_arguments(storage_summary, "storage")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    if args.command == "init":
        return run_init(args)
    if args.command == "discovery-job":
        return run_discovery_job(args)
    if args.command == "discovery-summary":
        return run_discovery_summary(args)
    if args.command == "suggestion":
        return run_suggestion(args)
    if args.command == "scoring-job":
        return run_scoring_job(args)
    if args.command == "storage-job":
        return run_storage_job(args)
    if args.command == "storage-summary":
        return run_storage_summary(args)
    raise ValueError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"pipeline_log: {error}", file=sys.stderr)
        raise SystemExit(1) from error
