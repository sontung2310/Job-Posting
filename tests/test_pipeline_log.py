from __future__ import annotations

import json
import sys
import tempfile
import unittest
from argparse import Namespace
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
import pipeline_log  # noqa: E402


class PipelineLogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.log_root = self.root / "logs"
        self.state_dir = self.root / "state"
        self.run_id = "2026-09-27-test"
        started = datetime(2026, 9, 27, 10, 0, tzinfo=ZoneInfo("Australia/Melbourne")).timestamp()
        pipeline_log.run_init(
            Namespace(
                run_id=self.run_id,
                started_epoch_seconds=started,
                write_notion="false",
                write_obsidian="true",
                log_root=self.log_root,
                state_dir=self.state_dir,
            )
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def args(self, stage: str, **values: object) -> Namespace:
        defaults = {
            "run_id": self.run_id,
            "stage": stage,
            "log_root": self.log_root,
            "state_dir": self.state_dir,
        }
        defaults.update(values)
        return Namespace(**defaults)

    def records(self, stage: str) -> list[dict[str, object]]:
        path = self.log_root / "27-09-2026" / f"{stage}.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def test_discovery_counts_are_explicitly_mutually_exclusive(self) -> None:
        pipeline_log.run_discovery_summary(
            self.args(
                "discovery",
                platform="Indeed",
                fetch=2,
                reject=3,
                retain=4,
                error=None,
            )
        )
        record = self.records("discovery")[0]
        self.assertEqual(record["counts"], {"fetch": 2, "reject": 3, "retain": 4})
        self.assertEqual(record["total"], 9)
        self.assertTrue(record["outcomes_mutually_exclusive"])

    def test_storage_summary_distinguishes_disabled_destinations(self) -> None:
        pipeline_log.run_storage_job(
            self.args(
                "storage",
                job_id="job-1",
                job_url=None,
                company="Example",
                position="AI Engineer",
                approved="true",
                write_obsidian="true",
                obsidian_status="written",
                obsidian_reference="career-vault/07 Applications/01 Active/example.md",
                write_notion="false",
                notion_status="failed",
                notion_reference=None,
            )
        )
        pipeline_log.run_storage_summary(self.args("storage"))
        records = self.records("storage")
        summary = records[-1]
        self.assertEqual(summary["approved_total"], 1)
        self.assertEqual(summary["destinations"]["obsidian"]["written_or_confirmed"], 1)
        self.assertEqual(summary["destinations"]["notion"]["skipped"], 1)
        self.assertTrue(summary["all_requested_writes_successful"])

    def test_scoring_job_keeps_usage_unknown_when_not_available(self) -> None:
        pipeline_log.run_scoring_job(
            self.args(
                "scoring",
                job_id="job-2",
                job_url=None,
                company="Example",
                position="AI Engineer",
                score=82,
                status="qualified",
                reason="Verified evidence supports the core AI and retrieval requirements.",
                input_tokens=None,
                cached_input_tokens=None,
                output_tokens=None,
                reasoning_output_tokens=None,
                cost_estimate_usd=None,
                elapsed_seconds=1.25,
            )
        )
        record = self.records("scoring")[0]
        self.assertEqual(record["candidate_evidence_fit"], 82)
        self.assertIsNone(record["cost_estimate_usd"])
        self.assertEqual(record["elapsed_seconds"], 1.25)
        self.assertFalse(record["usage_available"])

    def test_condition_failure_is_logged_without_score_or_profile_data(self) -> None:
        private_url = "https://jobs.example.test/role?candidate=private"
        pipeline_log.run_condition_check_job(
            self.args(
                "scoring",
                job_id=None,
                job_url=private_url,
                company="Example",
                position="AI Engineer",
                status="failed",
                reason="Explicit work-authorization condition is unmet.",
            )
        )
        record = self.records("scoring")[0]
        rendered = json.dumps(record)
        self.assertEqual(record["record_type"], "condition_check_job")
        self.assertEqual(record["status"], "failed")
        self.assertNotIn("candidate_evidence_fit", record)
        self.assertNotIn(private_url, rendered)
        self.assertNotIn("Temporary Graduate", rendered)
        self.assertEqual(record["job_id"], pipeline_log.require_job_id(None, private_url))

    def test_manual_review_condition_can_continue_without_becoming_a_failure(self) -> None:
        pipeline_log.run_condition_check_job(
            self.args(
                "scoring",
                job_id="job-manual-review",
                job_url=None,
                company="Example",
                position="AI Engineer",
                status="manual_review",
                reason="The JD condition needs manual checking.",
            )
        )
        record = self.records("scoring")[0]
        self.assertEqual(record["status"], "manual_review")
        self.assertNotIn("candidate_evidence_fit", record)

    def test_ineligible_cannot_be_logged_as_a_scored_job(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid scoring status"):
            pipeline_log.run_scoring_job(
                self.args(
                    "scoring",
                    job_id="job-3",
                    job_url=None,
                    company="Example",
                    position="AI Engineer",
                    score=90,
                    status="ineligible",
                    reason="A gate failed.",
                    input_tokens=None,
                    cached_input_tokens=None,
                    output_tokens=None,
                    reasoning_output_tokens=None,
                    cost_estimate_usd=None,
                    elapsed_seconds=None,
                )
            )

    def test_stage_timing_uses_a_real_start_and_stop_clock(self) -> None:
        args = self.args(
            "scoring",
            phase="stage2",
            timer_dir=self.root / "timers",
        )
        with patch.object(pipeline_log.time, "monotonic_ns", side_effect=[1_000_000_000, 1_500_000_000, 2_250_000_000]):
            pipeline_log.run_timing_start(args)
            with self.assertRaisesRegex(ValueError, "already started"):
                pipeline_log.run_timing_start(args)
            pipeline_log.run_timing_stop(args)
        record = self.records("scoring")[0]
        self.assertEqual(record["record_type"], "stage_timing")
        self.assertEqual(record["phase"], "stage2")
        self.assertEqual(record["elapsed_seconds"], 1.25)
        self.assertIn("started_at", record)
        self.assertIn("finished_at", record)
        with self.assertRaisesRegex(ValueError, "not started"):
            pipeline_log.run_timing_stop(args)


if __name__ == "__main__":
    unittest.main()
