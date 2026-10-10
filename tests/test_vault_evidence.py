from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
import vault_evidence  # noqa: E402


FIXTURE_VAULT = PROJECT_ROOT / "tests" / "fixtures" / "vault"


class VaultEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.notes, self.parse_errors = vault_evidence.scan_vault(FIXTURE_VAULT)

    @staticmethod
    def semantic_scores_for_rag(_requirement, candidates):
        """A deterministic local-model stand-in for hybrid-retrieval unit tests."""

        return [
            0.91 if candidate.note.path.as_posix() == "05 Evidence/Production RAG.md" else 0.08
            for candidate in candidates
        ]

    @staticmethod
    def no_semantic_signal(_requirement, candidates):
        return [0.0] * len(candidates)

    def test_verified_source_linked_notes_are_eligible(self) -> None:
        paths = {note.path.as_posix() for note in vault_evidence.eligible_notes(self.notes)}

        self.assertIn("05 Evidence/Production RAG.md", paths)
        self.assertNotIn("05 Evidence/Unverified Secret.md", paths)
        self.assertNotIn("05 Evidence/Missing Verification Date.md", paths)
        self.assertNotIn("05 Evidence/Evidence Index.md", paths)
        self.assertEqual(self.parse_errors, [])

    def test_check_requires_profile_preferences_and_evidence(self) -> None:
        self.assertEqual(vault_evidence.validation_errors(self.notes, self.parse_errors), [])

        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_vault = Path(temporary_directory) / "vault"
            shutil.copytree(FIXTURE_VAULT, temporary_vault)
            (temporary_vault / "01 Profile" / "Target Roles.md").unlink()
            notes, parse_errors = vault_evidence.scan_vault(temporary_vault)
            errors = vault_evidence.validation_errors(notes, parse_errors)

        self.assertIn("missing verified target-role preferences note", errors)

    def test_check_command_reports_named_prerequisite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_vault = Path(temporary_directory) / "vault"
            shutil.copytree(FIXTURE_VAULT, temporary_vault)
            (temporary_vault / "01 Profile" / "Career Profile.md").unlink()
            result = subprocess.run(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "scripts" / "vault_evidence.py"),
                    "check",
                    "--vault",
                    str(temporary_vault),
                ],
                capture_output=True,
                check=False,
                text=True,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("missing verified profile note", result.stderr)

    def test_keyword_search_returns_direct_match(self) -> None:
        matches = vault_evidence.search_notes(
            self.notes,
            "Build RAG systems",
            ["RAG"],
            limit=8,
            semantic_scorer=self.no_semantic_signal,
        )

        self.assertEqual(matches[0]["path"], "05 Evidence/Production RAG.md")
        self.assertIn("RAG", matches[0]["matched_terms"])
        self.assertEqual(matches[0]["heading"], "Claim")
        self.assertEqual(matches[0]["retrieval_methods"], ["keyword"])
        self.assertNotIn("Related notes", [match["heading"] for match in matches])

    def test_semantic_retrieval_finds_conceptually_related_evidence_without_aliases(self) -> None:
        matches = vault_evidence.search_notes(
            self.notes,
            "Generate answers from an indexed knowledge collection",
            [],
            limit=8,
            semantic_scorer=self.semantic_scores_for_rag,
        )

        self.assertTrue(matches)
        self.assertEqual(matches[0]["path"], "05 Evidence/Production RAG.md")
        self.assertEqual(matches[0]["matched_terms"], [])
        self.assertEqual(matches[0]["retrieval_methods"], ["semantic"])
        self.assertGreater(matches[0]["semantic_score"], 0.35)

    def test_search_returns_no_match_without_exposing_ineligible_notes(self) -> None:
        matches = vault_evidence.search_notes(
            self.notes,
            "Kubernetes",
            ["Kubernetes"],
            limit=8,
            semantic_scorer=self.no_semantic_signal,
        )
        output = json.dumps(matches)

        self.assertEqual(matches, [])
        self.assertNotIn("DO NOT EXPOSE", output)

    def test_application_workspace_is_excluded_from_parsing_and_retrieval(self) -> None:
        paths = {note.path.as_posix() for note in self.notes}
        output = json.dumps(vault_evidence.search_notes(
            self.notes,
            "application-only-claim",
            ["application-only-claim"],
            limit=8,
            semantic_scorer=self.no_semantic_signal,
        ))

        self.assertNotIn("07 Applications/01 Active/Unsafe Application Note.md", paths)
        self.assertEqual(self.parse_errors, [])
        self.assertNotIn("application-only-claim", output)

    def test_hybrid_score_reports_both_retrieval_signals(self) -> None:
        matches = vault_evidence.search_notes(
            self.notes,
            "Build retrieval-augmented generation systems",
            ["RAG"],
            limit=8,
            semantic_scorer=self.semantic_scores_for_rag,
        )

        best = matches[0]
        self.assertEqual(best["path"], "05 Evidence/Production RAG.md")
        self.assertEqual(best["retrieval_methods"], ["keyword", "semantic"])
        self.assertGreater(best["keyword_score"], 0)
        self.assertGreater(best["semantic_score"], 0.35)
        self.assertGreater(best["hybrid_score"], best["keyword_score"] * 0.4)

    def test_hybrid_search_requires_a_semantic_scorer(self) -> None:
        with self.assertRaises(vault_evidence.SemanticSearchUnavailable):
            vault_evidence.search_notes(
                self.notes,
                "Build retrieval-augmented generation systems",
                [],
                limit=8,
            )

    def test_related_note_links_are_not_semantic_candidates(self) -> None:
        matches = vault_evidence.search_notes(
            self.notes,
            "Generate answers from an indexed knowledge collection",
            [],
            limit=8,
            semantic_scorer=self.semantic_scores_for_rag,
        )

        self.assertNotIn("Related notes", [match["heading"] for match in matches])

    def test_compact_matches_keeps_source_and_truncates_evidence(self) -> None:
        matches = vault_evidence.search_notes(
            self.notes,
            "Build RAG systems",
            ["RAG"],
            limit=1,
            semantic_scorer=self.no_semantic_signal,
        )
        compact = vault_evidence.compact_matches(matches, text_limit=20)

        self.assertNotIn("text", compact[0])
        self.assertEqual(compact[0]["path"], matches[0]["path"])
        self.assertEqual(compact[0]["source"], matches[0]["source"])
        self.assertLessEqual(len(compact[0]["text_excerpt"]), 21)
        self.assertTrue(compact[0]["text_excerpt"].endswith("…"))

    def test_batch_service_deduplicates_queries_and_caches_complete_results(self) -> None:
        import numpy as np

        class FakeModel:
            def __init__(self) -> None:
                self.calls = []

            def encode_queries(self, queries, **_kwargs):
                self.calls.append(list(queries))
                return np.ones((len(queries), 2), dtype="float32")

        with tempfile.TemporaryDirectory() as temporary_directory:
            service = vault_evidence.EmbeddingIndexService.__new__(
                vault_evidence.EmbeddingIndexService
            )
            service.np = np
            service.vault_path = FIXTURE_VAULT
            service.model_name = "test-model"
            service.model_cache = Path(temporary_directory)
            service.index_path = Path(temporary_directory)
            service.notes = self.notes
            service.parse_errors = self.parse_errors
            service.candidates = vault_evidence.build_candidates(self.notes)
            service.fingerprint = "fixture"
            service.model = FakeModel()
            service.embeddings = np.ones((len(service.candidates), 2), dtype="float32")
            service.query_cache_path = service.index_path / "query-cache.json"
            service.query_cache = {
                "schema_version": vault_evidence.CHROMA_INDEX_SCHEMA_VERSION,
                "model": service.model_name,
                "vault_fingerprint": service.fingerprint,
                "entries": {},
            }
            service._refresh_if_needed = lambda: None

            requests = [
                {"requirement": "Build RAG systems", "terms": ["RAG"], "limit": 1},
                {"requirement": "Build RAG systems", "terms": ["RAG"], "limit": 1},
                {"requirement": "Build RAG systems", "terms": ["RAG", "Docker"], "limit": 1},
            ]
            results = service.search_requests(requests)

            self.assertEqual(len(results), 3)
            self.assertEqual(service.model.calls, [["Build RAG systems"]])
            self.assertEqual(len(service.query_cache["entries"]), 2)

            service.search_requests(requests)
            self.assertEqual(service.model.calls, [["Build RAG systems"]])


if __name__ == "__main__":
    unittest.main()
