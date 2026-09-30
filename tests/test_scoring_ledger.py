#!/usr/bin/env python3
"""Tests for privacy-safe equal-share Stage 2 scoring records."""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import scoring_ledger  # noqa: E402


class ScoringLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.state_dir = self.root / "state"
        self.log_dir = self.root / "logs"
        self.rates_path = self.root / "rates.json"
        self.rates_path.write_text(
            json.dumps(
                {
                    "checked_on": "2026-09-27",
                    "source": "https://example.test/rates",
                    "scope": "test only",
                    "models": {
                        "test-model": {
                            "input_usd_per_million_tokens": 2.0,
                            "cached_input_usd_per_million_tokens": 0.2,
                            "output_usd_per_million_tokens": 12.0,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def finalize(self, run_id: str) -> None:
        events = io.StringIO(
            '{"type":"thread.started"}\n'
            '{"type":"turn.completed","usage":'
            '{"input_tokens":1000,"cached_input_tokens":400,'
            '"output_tokens":100,"reasoning_output_tokens":50}}\n'
        )
        with patch.object(scoring_ledger.time, "time", return_value=1_120.0):
            scoring_ledger.run_finalize(
                self.state_dir,
                self.log_dir,
                self.rates_path,
                run_id,
                "test-model",
                1_000.0,
                events,
            )

    def records(self) -> list[dict[str, object]]:
        files = list(self.log_dir.glob("*.jsonl"))
        self.assertEqual(len(files), 1)
        return [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines()]

    def test_allocates_completed_batch_equally_without_raw_urls(self) -> None:
        run_id = "2026-09-27-test"
        scoring_ledger.run_begin(self.state_dir, run_id)
        first_url = "https://jobs.example.test/first?candidate=private"
        scoring_ledger.run_record(
            self.state_dir,
            run_id,
            first_url,
            "Example Co",
            "AI Engineer",
            82,
            "qualified",
            "Direct evidence supports RAG and deployment; one preferred tool is transferable.",
        )
        scoring_ledger.run_record(
            self.state_dir,
            run_id,
            "https://jobs.example.test/second",
            "Second Co",
            "Machine Learning Engineer",
            60,
            "below_threshold",
            "Relevant engineering evidence exists, but several required tools are unsupported.",
        )

        self.finalize(run_id)

        records = self.records()
        self.assertEqual([record["record_type"] for record in records], ["batch_summary", "jd_score", "jd_score"])
        batch = records[0]
        self.assertEqual(batch["scored_jd_count"], 2)
        self.assertEqual(batch["estimated_token_cost_usd"], 0.00308)
        self.assertEqual(batch["token_usage"]["uncached_input_tokens"], 600)
        self.assertEqual(batch["token_usage"]["billable_output_tokens"], 150)
        for record in records[1:]:
            estimate = record["batch_estimate"]
            self.assertEqual(estimate["estimated_time_seconds"], 60.0)
            self.assertEqual(estimate["estimated_token_cost_usd"], 0.00154)
            self.assertEqual(estimate["estimated_token_usage"]["input_tokens"], 500.0)
            self.assertEqual(
                estimate["allocation_method"],
                "equal share of the completed batch across scored JDs",
            )
        rendered = "\n".join(json.dumps(record) for record in records)
        self.assertNotIn(first_url, rendered)
        self.assertIn(scoring_ledger.job_id(first_url), rendered)
        self.assertFalse(scoring_ledger.run_state_path(self.state_dir, run_id).exists())

    def test_zero_jd_batch_is_successful_without_an_allocation(self) -> None:
        run_id = "2026-09-27-zero"
        scoring_ledger.run_begin(self.state_dir, run_id)

        self.finalize(run_id)

        records = self.records()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["record_type"], "batch_summary")
        self.assertEqual(records[0]["scored_jd_count"], 0)
        self.assertFalse(scoring_ledger.run_state_path(self.state_dir, run_id).exists())

    def test_qualified_jd_without_suggestion_blocks_daily_finalization(self) -> None:
        run_id = "2026-09-27-missing-suggestion"
        scoring_ledger.run_begin(self.state_dir, run_id)
        scoring_ledger.run_record(
            self.state_dir,
            run_id,
            "https://jobs.example.test/missing-suggestion",
            "Example Co",
            "AI Engineer",
            82,
            "qualified",
            "Verified evidence supports the role.",
        )
        events = io.StringIO(
            '{"type":"turn.completed","usage":'
            '{"input_tokens":100,"cached_input_tokens":20,'
            '"output_tokens":10,"reasoning_output_tokens":5}}\n'
        )
        daily_root = self.root / "daily"
        with patch.object(scoring_ledger.time, "time", return_value=1_120.0):
            with self.assertRaisesRegex(ValueError, "missing suggestion log"):
                scoring_ledger.run_finalize(
                    self.state_dir,
                    self.log_dir,
                    self.rates_path,
                    run_id,
                    "test-model",
                    1_000.0,
                    events,
                    daily_root,
                )
        self.assertFalse((daily_root / "01-01-1970" / "scoring.jsonl").exists())
        self.assertTrue(scoring_ledger.run_state_path(self.state_dir, run_id).exists())

    def test_optional_daily_folder_receives_a_scoring_copy(self) -> None:
        run_id = "2026-09-27-daily-copy"
        scoring_ledger.run_begin(self.state_dir, run_id)
        first_url = "https://jobs.example.test/daily-copy"
        scoring_ledger.run_record(
            self.state_dir,
            run_id,
            first_url,
            "Example Co",
            "AI Engineer",
            80,
            "qualified",
            "Verified evidence supports the role.",
        )
        events = io.StringIO(
            '{"type":"turn.completed","usage":'
            '{"input_tokens":100,"cached_input_tokens":20,'
            '"output_tokens":10,"reasoning_output_tokens":5}}\n'
        )
        daily_root = self.root / "daily"
        suggestion_path = daily_root / "01-01-1970" / "suggestion.jsonl"
        suggestion_path.parent.mkdir(parents=True)
        suggestion_path.write_text(
            json.dumps(
                {
                    "record_type": "suggestion_job",
                    "run_id": run_id,
                    "job_id": scoring_ledger.job_id(first_url),
                    "status": "completed",
                    "token_usage": {
                        "input_tokens": None,
                        "cached_input_tokens": None,
                        "output_tokens": None,
                        "reasoning_output_tokens": None,
                    },
                    "cost_estimate_usd": None,
                    "usage_available": False,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        with patch.object(scoring_ledger.time, "time", return_value=1_120.0):
            scoring_ledger.run_finalize(
                self.state_dir,
                self.log_dir,
                self.rates_path,
                run_id,
                "test-model",
                1_000.0,
                events,
                daily_root,
            )

        daily_file = daily_root / "01-01-1970" / "scoring.jsonl"
        self.assertTrue(daily_file.is_file())
        self.assertEqual(len(daily_file.read_text(encoding="utf-8").splitlines()), 2)
        suggestion = json.loads(suggestion_path.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(suggestion["token_usage"]["input_tokens"], 100.0)
        self.assertEqual(suggestion["cost_estimate_usd"], 0.000344)
        self.assertEqual(suggestion["elapsed_seconds"], 120.0)
        self.assertTrue(suggestion["usage_available"])
        self.assertEqual(suggestion["usage_source"], "turn.completed")


if __name__ == "__main__":
    unittest.main()
