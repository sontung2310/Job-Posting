from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
import condition_profile  # noqa: E402


class ConditionProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.vault = self.root / "vault"
        self.profile_dir = self.vault / "01 Profile"
        self.profile_dir.mkdir(parents=True)
        self.output = self.root / ".state" / "condition-check.json"
        (self.profile_dir / "Work Authorization.md").write_text(
            """---
type: constraint
status: verified
source:
  - "user-confirmed: 2026-10-01"
last_verified: 2026-10-01
visa_type: "Temporary Graduate visa"
work_rights_regions: "Australia"
full_current_work_rights: "Australia"
sponsorship_required: null
permanent_resident: "false"
australian_citizen: "false"
new_zealand_citizen: "false"
---
""",
            encoding="utf-8",
        )
        self.career_note = self.profile_dir / "Career Profile.md"
        self.career_note.write_text(
            """---
type: profile
status: verified
source:
  - "resume.pdf"
last_verified: 2026-09-26
education:
  - "Master of Applied Artificial Intelligence (Professional), Deakin University."
  - "Bachelor of Engineering — Electronics and Telecommunications."
---
""",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_generates_source_linked_profile_from_verified_notes(self) -> None:
        profile = condition_profile.build_condition_profile(self.vault, self.output)
        saved = json.loads(self.output.read_text(encoding="utf-8"))

        self.assertEqual(profile, saved)
        self.assertEqual(profile["work_authorization"]["visa_type"], "Temporary Graduate visa")
        self.assertEqual(profile["work_authorization"]["authorized_regions"], ["Australia"])
        self.assertTrue(profile["work_authorization"]["full_current_work_rights_regions"])
        self.assertIsNone(profile["work_authorization"]["sponsorship_required"])
        self.assertFalse(profile["work_authorization"]["permanent_resident"])
        self.assertFalse(profile["work_authorization"]["new_zealand_citizen"])
        self.assertEqual(len(profile["education"]), 2)
        self.assertEqual(profile["sources"]["education"]["last_verified"], "2026-09-26")
        self.assertIn("user-confirmed: 2026-10-01", profile["sources"]["work_authorization"]["source"])
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o600)

    def test_refreshed_profile_tracks_obsidian_changes(self) -> None:
        condition_profile.build_condition_profile(self.vault, self.output)
        auth_note = self.profile_dir / "Work Authorization.md"
        auth_note.write_text(
            auth_note.read_text(encoding="utf-8").replace(
                'visa_type: "Temporary Graduate visa"', 'visa_type: "Updated visa"'
            ),
            encoding="utf-8",
        )
        self.career_note.write_text(
            self.career_note.read_text(encoding="utf-8").replace(
                "Master of Applied Artificial Intelligence (Professional)", "Updated master's degree"
            ),
            encoding="utf-8",
        )

        refreshed = condition_profile.build_condition_profile(self.vault, self.output)

        self.assertEqual(refreshed["work_authorization"]["visa_type"], "Updated visa")
        self.assertIn("Updated master's degree", refreshed["education"][0])

    def test_rejects_unverified_or_unlinked_profile_notes(self) -> None:
        auth_note = self.profile_dir / "Work Authorization.md"
        auth_note.write_text(
            auth_note.read_text(encoding="utf-8").replace("status: verified", "status: draft"),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "not verified and source-linked"):
            condition_profile.build_condition_profile(self.vault, self.output)


if __name__ == "__main__":
    unittest.main()
