from __future__ import annotations

import json
import sys
import tempfile
import unittest
from argparse import Namespace
from datetime import datetime
from pathlib import Path
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
                elapsed_seconds=None,
            )
        )
        record = self.records("scoring")[0]
        self.assertEqual(record["candidate_evidence_fit"], 82)
        self.assertIsNone(record["cost_estimate_usd"])
        self.assertIsNone(record["elapsed_seconds"])
        self.assertFalse(record["usage_available"])


if __name__ == "__main__":
    unittest.main()
