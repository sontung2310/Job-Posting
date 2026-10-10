"""Repository-backed evidence stays inspectable after reference renames."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".agents/skills/job-scoring/scripts"))
import assessment
from assessment_fixture import fixture


class ReferenceSources(unittest.TestCase):
    def test_legacy_and_current_adapter_citations_inspect_current_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'docs').mkdir()
            (root / 'docs/additional-source-adapters.md').write_text('Verified adapter contract.')
            vault = root / 'vault'; vault.mkdir()
            sources = ['Job-Search repository docs/06-source-adapters.md',
                       'Job-Search repository docs/additional-source-adapters.md']
            with patch.object(assessment, 'ROOT', root):
                excerpts = assessment.source_excerpts(sources, {}, vault)
            self.assertEqual(excerpts, [{'source': source, 'text': 'Verified adapter contract.'} for source in sources])

    def test_reference_changes_invalidate_legacy_evidence_fingerprint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vault, resumes = fixture(root)
            note = vault / '05 Evidence/Python.md'
            note.write_text(note.read_text().replace('user-confirmed: fixture', 'Job-Search repository docs/06-source-adapters.md'))
            (root / 'docs').mkdir()
            reference = root / 'docs/additional-source-adapters.md'
            reference.write_text('Original supported scope.')
            with patch.object(assessment, 'ROOT', root):
                before = assessment.evidence_fingerprint(vault, resumes)
                reference.write_text('Changed supported scope.')
                after = assessment.evidence_fingerprint(vault, resumes)
            self.assertNotEqual(before, after)

    def test_repository_citation_cannot_escape_through_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'repo'; root.mkdir()
            outside = Path(directory) / 'private.txt'; outside.write_text('private')
            (root / 'README.md').symlink_to(outside)
            vault = root / 'vault'; vault.mkdir()
            with patch.object(assessment, 'ROOT', root):
                with self.assertRaises(ValueError):
                    assessment.source_excerpts(['Job-Search repository README.md'], {}, vault)


if __name__ == '__main__':
    unittest.main()
