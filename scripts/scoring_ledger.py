#!/usr/bin/env python3
"""Record private, batch-level Candidate Evidence Fit cost and timing estimates.

The scoring agent records one short draft per retained JD. After its single Codex
turn finishes, this utility reads the `turn.completed` JSONL event, calculates the
batch token-cost estimate, and divides tokens, cost, and elapsed time equally
across all recorded JDs. It intentionally never stores full job descriptions or
vault evidence text.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo


MAX_REASON_LENGTH = 240
MAX_LABEL_LENGTH = 120


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_state_dir() -> Path:
    return project_root() / ".state" / "scoring-ledger"


def default_log_dir() -> Path:
    return project_root() / "logs" / "scoring"


def daily_log_target(log_root: Path, run_date: str, stage: str) -> Path:
    display_date = datetime.fromisoformat(run_date).strftime("%d-%m-%Y")
    return log_root / display_date / f"{stage}.jsonl"


def default_rates_path() -> Path:
    return project_root() / "config" / "scoring_cost_rates.json"


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def compact_text(value: str, maximum_length: int) -> str:
    compact = " ".join(value.split())
    if not compact:
        raise ValueError("a non-empty value is required")
    if len(compact) > maximum_length:
        raise ValueError(f"value must be at most {maximum_length} characters")
    return compact


def run_state_path(state_dir: Path, run_id: str) -> Path:
    if not run_id or any(character not in "-_abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" for character in run_id):
        raise ValueError("run id may contain only letters, numbers, hyphens, and underscores")
    return state_dir / f"{run_id}.jsonl"


def job_id(job_url: str) -> str:
    return hashlib.sha256(job_url.strip().encode("utf-8")).hexdigest()[:16]


def append_json_line(path: Path, item: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True))
        handle.write("\n")


def enrich_daily_suggestions(
    path: Path,
    run_id: str,
    estimates: dict[str, dict[str, Any]],
    expected_job_ids: set[str] | None = None,
) -> int:
    """Attach finalized batch telemetry to this run's suggestion records.

    Suggestions are recorded while the Codex turn is still running, so their
    usage fields cannot be known at creation time.  The finalizer is the first
    reliable point at which the completed-turn usage event is available.
    """

    if not path.is_file():
        if expected_job_ids:
            raise ValueError(
                "suggestion telemetry validation failed: "
                f"missing suggestion log for qualified jobs: {sorted(expected_job_ids)}"
            )
        return 0

    changed = 0
    seen_job_ids: set[str] = set()
    temporary_path: str | None = None
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.seek(0)
            records: list[dict[str, Any]] = []
            for line_number, line in enumerate(handle.read().splitlines(), start=1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(
                        f"invalid suggestion JSON on line {line_number}: {path}"
                    ) from error
                if not isinstance(value, dict):
                    raise ValueError(f"suggestion JSON on line {line_number} must be an object")
                records.append(value)

            for record in records:
                if (
                    record.get("record_type") != "suggestion_job"
                    or record.get("run_id") != run_id
                ):
                    continue
                job_identifier = record.get("job_id")
                estimate = estimates.get(job_identifier)
                if estimate is None:
                    raise ValueError(
                        "suggestion job has no matching scored JD: "
                        f"run_id={run_id}, job_id={job_identifier}"
                    )
                seen_job_ids.add(str(job_identifier))
                record.update(
                    {
                        "token_usage": estimate["token_usage"],
                        "cost_estimate_usd": estimate["cost_estimate_usd"],
                        "elapsed_seconds": estimate["elapsed_seconds"],
                        "usage_available": True,
                        "usage_source": "turn.completed",
                        "usage_scope": "full CLI turn",
                        "allocation_method": (
                            "equal share of the completed CLI turn across scored JDs"
                        ),
                    }
                )
                changed += 1

            if expected_job_ids is not None and seen_job_ids != expected_job_ids:
                missing = sorted(expected_job_ids - seen_job_ids)
                unexpected = sorted(seen_job_ids - expected_job_ids)
                details: list[str] = []
                if missing:
                    details.append(f"missing qualified suggestions: {missing}")
                if unexpected:
                    details.append(f"unexpected suggestions: {unexpected}")
                raise ValueError(f"suggestion telemetry validation failed: {'; '.join(details)}")

            if changed:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=path.parent,
                    prefix=f".{path.name}.",
                    suffix=".tmp",
                    delete=False,
                ) as temporary:
                    temporary_path = temporary.name
                    for record in records:
                        temporary.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
                        temporary.write("\n")
                    temporary.flush()
                    os.fsync(temporary.fileno())
                os.replace(temporary_path, path)
                temporary_path = None
        finally:
            if temporary_path is not None:
                try:
                    os.unlink(temporary_path)
                except FileNotFoundError:
                    pass
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return changed


def read_json_lines(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ValueError(f"no scoring drafts exist for this run: {path}")

    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid draft JSON on line {line_number}") from error
        if not isinstance(value, dict):
            raise ValueError(f"draft JSON on line {line_number} must be an object")
        records.append(value)
    return records


def run_begin(state_dir: Path, run_id: str) -> int:
    path = run_state_path(state_dir, run_id)
    if path.exists():
        raise ValueError(f"scoring ledger already exists for run id: {run_id}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return 0


def run_record(
    state_dir: Path,
    run_id: str,
    job_url: str,
    company: str,
    position: str,
    score: int,
    status: str,
    reason: str,
) -> int:
    if not 0 <= score <= 100:
        raise ValueError("score must be between 0 and 100")
    if status not in {"qualified", "below_threshold"}:
        raise ValueError("status must be qualified or below_threshold")
    if not job_url.strip():
        raise ValueError("a canonical job URL is required")

    path = run_state_path(state_dir, run_id)
    identifier = job_id(job_url)
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        try:
            existing_ids = {record.get("job_id") for record in read_json_lines(path)}
            if identifier in existing_ids:
                raise ValueError("this job already has a scoring ledger record in the run")

            append_json_line(
                path,
                {
                    "record_type": "jd_score_draft",
                    "run_id": run_id,
                    "job_id": identifier,
                    "company": compact_text(company, MAX_LABEL_LENGTH),
                    "position": compact_text(position, MAX_LABEL_LENGTH),
                    "candidate_evidence_fit": score,
                    "status": status,
                    "reason": compact_text(reason, MAX_REASON_LENGTH),
                    "recorded_at": utc_now(),
                },
            )
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
    return 0


def turn_usage(events: Iterable[str]) -> dict[str, int]:
    completed_usage: dict[str, Any] | None = None
    for line_number, line in enumerate(events, start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid Codex JSONL event on line {line_number}") from error
        if event.get("type") == "turn.completed":
            usage = event.get("usage")
            if not isinstance(usage, dict):
                raise ValueError("turn.completed event did not contain usage")
            completed_usage = usage

    if completed_usage is None:
        raise ValueError("Codex JSONL did not contain a turn.completed usage event")

    def count(name: str) -> int:
        value = completed_usage.get(name, 0)
        if not isinstance(value, int) or value < 0:
            raise ValueError(f"turn usage field {name} must be a non-negative integer")
        return value

    return {
        "input_tokens": count("input_tokens"),
        "cached_input_tokens": count("cached_input_tokens"),
        "output_tokens": count("output_tokens"),
        "reasoning_output_tokens": count("reasoning_output_tokens"),
    }


def load_rates(path: Path, model: str) -> tuple[dict[str, float], dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(f"cost-rate file does not exist: {path}") from error

    if not isinstance(data, dict) or not isinstance(data.get("models"), dict):
        raise ValueError("cost-rate file must contain a models object")
    raw_rates = data["models"].get(model)
    if not isinstance(raw_rates, dict):
        raise ValueError(f"no token rates configured for model: {model}")

    required_fields = (
        "input_usd_per_million_tokens",
        "cached_input_usd_per_million_tokens",
        "output_usd_per_million_tokens",
    )
    rates: dict[str, float] = {}
    for field in required_fields:
        value = raw_rates.get(field)
        if not isinstance(value, (int, float)) or value < 0:
            raise ValueError(f"invalid {field} for model: {model}")
        rates[field] = float(value)
    return rates, data


def estimate_cost(usage: dict[str, int], rates: dict[str, float]) -> tuple[float, int, int]:
    cached = min(usage["cached_input_tokens"], usage["input_tokens"])
    uncached = usage["input_tokens"] - cached
    if usage["reasoning_output_tokens"] > usage["output_tokens"]:
        raise ValueError("reasoning output tokens cannot exceed total output tokens")
    # Reasoning tokens are already included in output_tokens.
    billable_output = usage["output_tokens"]
    estimated_cost = (
        uncached * rates["input_usd_per_million_tokens"]
        + cached * rates["cached_input_usd_per_million_tokens"]
        + billable_output * rates["output_usd_per_million_tokens"]
    ) / 1_000_000
    return estimated_cost, uncached, billable_output


def run_finalize(
    state_dir: Path,
    log_dir: Path,
    rates_path: Path,
    run_id: str,
    model: str,
    started_epoch_seconds: float,
    codex_events: Iterable[str],
    daily_log_root: Path | None = None,
) -> int:
    drafts = read_json_lines(run_state_path(state_dir, run_id))
    usage = turn_usage(codex_events)
    rates, rate_card = load_rates(rates_path, model)
    total_cost, uncached_input, billable_output = estimate_cost(usage, rates)
    elapsed_seconds = max(0.0, time.time() - started_epoch_seconds)
    jd_count = len(drafts)
    run_date = datetime.fromtimestamp(
        started_epoch_seconds, ZoneInfo("Australia/Melbourne")
    ).date().isoformat()
    target = log_dir / f"{run_date}.jsonl"
    daily_target = (
        daily_log_target(daily_log_root, run_date, "scoring")
        if daily_log_root is not None
        else None
    )

    batch_record = {
        "record_type": "batch_summary",
        "run_id": run_id,
        "completed_at": utc_now(),
        "model": model,
        "scored_jd_count": jd_count,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "usage_source": "turn.completed",
        "token_usage": {
            **usage,
            "uncached_input_tokens": uncached_input,
            "billable_output_tokens": billable_output,
        },
        "estimated_token_cost_usd": round(total_cost, 8),
        "rate_card": {
            "checked_on": rate_card.get("checked_on"),
            "source": rate_card.get("source"),
            "scope": rate_card.get("scope"),
            "rates_usd_per_million_tokens": rates,
        },
    }
    per_jd_estimates: dict[str, dict[str, Any]] = {}
    per_jd_records: list[dict[str, Any]] = []
    if jd_count:
        per_jd_token_usage = {
            field: round(value / jd_count, 3)
            for field, value in batch_record["token_usage"].items()
        }
        per_jd_cost = round(total_cost / jd_count, 8)
        per_jd_time = round(elapsed_seconds / jd_count, 3)
        for draft in drafts:
            per_jd_estimates[str(draft["job_id"])] = {
                "token_usage": per_jd_token_usage,
                "cost_estimate_usd": per_jd_cost,
                "elapsed_seconds": per_jd_time,
            }
            record = {
                **draft,
                "record_type": "jd_score",
                "batch_estimate": {
                    "model": model,
                    "usage_source": "turn.completed",
                    "usage_scope": "full CLI turn",
                    "estimated_time_seconds": per_jd_time,
                    "estimated_token_cost_usd": per_jd_cost,
                    "estimated_token_usage": per_jd_token_usage,
                    "allocation_method": "equal share of the completed batch across scored JDs",
                },
            }
            per_jd_records.append(record)

    enriched_suggestions = 0
    if daily_target is not None:
        qualified_job_ids = {
            str(draft["job_id"])
            for draft in drafts
            if draft.get("status") == "qualified"
        }
        enriched_suggestions = enrich_daily_suggestions(
            daily_log_target(daily_log_root, run_date, "suggestion"),
            run_id,
            per_jd_estimates,
            expected_job_ids=qualified_job_ids,
        )

    append_json_line(target, batch_record)
    if daily_target is not None:
        append_json_line(daily_target, batch_record)
    for record in per_jd_records:
        append_json_line(target, record)
        if daily_target is not None:
            append_json_line(daily_target, record)

    run_state_path(state_dir, run_id).unlink()
    print(
        f"Scoring ledger finalized: {jd_count} JD records, "
        f"${total_cost:.6f} estimated token cost, {elapsed_seconds:.1f}s total, "
        f"{enriched_suggestions} suggestion records enriched."
    )
    return 0


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    begin = subparsers.add_parser("begin", help="create an empty private ledger for a batch run")
    begin.add_argument("--run-id", required=True)
    begin.add_argument("--state-dir", type=Path, default=default_state_dir())

    record = subparsers.add_parser("record", help="append one short per-JD scoring draft")
    record.add_argument("--run-id", required=True)
    record.add_argument("--state-dir", type=Path, default=default_state_dir())
    record.add_argument("--job-url", required=True)
    record.add_argument("--company", required=True)
    record.add_argument("--position", required=True)
    record.add_argument("--score", required=True, type=int)
    record.add_argument("--status", required=True)
    record.add_argument("--reason", required=True)

    finalize = subparsers.add_parser("finalize", help="allocate batch usage equally across recorded JDs")
    finalize.add_argument("--run-id", required=True)
    finalize.add_argument("--model", required=True)
    finalize.add_argument("--started-epoch-seconds", required=True, type=float)
    finalize.add_argument("--state-dir", type=Path, default=default_state_dir())
    finalize.add_argument("--log-dir", type=Path, default=default_log_dir())
    finalize.add_argument(
        "--daily-log-root",
        type=Path,
        default=None,
        help="also write logs/DD-MM-YYYY/scoring.jsonl without changing the legacy ledger",
    )
    finalize.add_argument("--rates", type=Path, default=default_rates_path())

    validate_rates = subparsers.add_parser(
        "validate-rates", help="verify that a configured scoring model has a rate card"
    )
    validate_rates.add_argument("--model", required=True)
    validate_rates.add_argument("--rates", type=Path, default=default_rates_path())
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    if args.command == "begin":
        return run_begin(args.state_dir, args.run_id)
    if args.command == "record":
        return run_record(
            args.state_dir,
            args.run_id,
            args.job_url,
            args.company,
            args.position,
            args.score,
            args.status,
            args.reason,
        )
    if args.command == "finalize":
        return run_finalize(
            args.state_dir,
            args.log_dir,
            args.rates,
            args.run_id,
            args.model,
            args.started_epoch_seconds,
            sys.stdin,
            args.daily_log_root,
        )
    if args.command == "validate-rates":
        load_rates(args.rates, args.model)
        print(f"Cost-rate card is available for {args.model}.")
        return 0
    raise ValueError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"scoring_ledger: {error}", file=sys.stderr)
        raise SystemExit(1) from error
