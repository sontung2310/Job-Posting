import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from assessment_fixture import fixture, write_pdf
import readiness

PDF = os.environ.get('PDFTOTEXT_BIN') or shutil.which('pdftotext')

class ReadinessTests(unittest.TestCase):
    def test_local_readiness_reuses_text_and_invalidates_changed_resumes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vault, resumes = fixture(root)
            (vault/'01 Profile/Target Roles.md').write_text('---\ntype: preferences\nstatus: verified\nsource: user-confirmed: fixture\nlast_verified: 2026-10-01\n---\nPython roles\n')
            options = dict(vault=vault, resumes_dir=resumes, hybrid_search=False, pdftotext=PDF, cache_path=root/'private/readiness.json')
            first = readiness.check(**options)
            self.assertFalse(first['reused'])
            self.assertIn('Built Python services.', first['resumes']['ai.pdf'])
            self.assertTrue(readiness.check(**options)['reused'])
            write_pdf(resumes/'ai.pdf', 'Updated Python services.')
            changed = readiness.check(**options)
            self.assertFalse(changed['reused'])
            self.assertIn('Updated Python services.', changed['resumes']['ai.pdf'])
            self.assertNotEqual(first['input_fingerprint'], changed['input_fingerprint'])
            self.assertEqual((root/'private/readiness.json').stat().st_mode & 0o777, 0o600)

    def test_discovery_needs_no_resumes_profile_extraction_or_cloud(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); vault, _ = fixture(root)
            (vault/'01 Profile/Target Roles.md').write_text('---\ntype: preferences\nstatus: verified\nsource: user-confirmed: fixture\nlast_verified: 2026-10-01\n---\nPython roles\n')
            with patch.object(readiness, 'build_condition_profile', side_effect=AssertionError('profile extraction')), \
                 patch.object(readiness, 'build_chroma_index', side_effect=AssertionError('cloud')), \
                 patch.object(readiness, 'run_check_index', side_effect=AssertionError('cloud')), \
                 patch.object(readiness.subprocess, 'run', side_effect=AssertionError('PDF extraction')):
                result = readiness.check('discovery', vault=vault, resumes_dir=root/'missing', hybrid_search=True)
            self.assertEqual(result['resumes'], {})
            (vault/'05 Evidence/Python.md').unlink()
            with self.assertRaisesRegex(ValueError, 'Vault readiness failed'):
                readiness.check('discovery', vault=vault, resumes_dir=root/'missing')

    def test_failed_hybrid_readiness_cannot_repeat_paid_work_without_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); vault, resumes = fixture(root)
            (vault/'01 Profile/Target Roles.md').write_text('---\ntype: preferences\nstatus: verified\nsource: user-confirmed: fixture\nlast_verified: 2026-10-01\n---\nPython roles\n')
            options = dict(vault=vault, resumes_dir=resumes, hybrid_search=True,
                           pdftotext=PDF, cache_path=root/'private/readiness.json')
            with patch.object(readiness, 'build_chroma_index') as build, \
                 patch.object(readiness, 'run_check_index', side_effect=readiness.SemanticSearchUnavailable('unknown usage')):
                with self.assertRaises(readiness.SemanticSearchUnavailable): readiness.check(**options)
                with self.assertRaisesRegex(ValueError, 'approval'): readiness.check(**options)
                self.assertEqual(build.call_count, 1)
            with patch.object(readiness, 'build_chroma_index'), patch.object(readiness, 'run_check_index'):
                readiness.check(**options, authorize_paid_retry=True)
            self.assertFalse((root/'private/readiness.json.hybrid-pending.json').exists())
            # A failure on the cached path must not fall back to rebuilding vectors.
            with patch.object(readiness, 'build_chroma_index') as build, \
                 patch.object(readiness, 'run_check_index', side_effect=readiness.SemanticSearchUnavailable('unknown cached usage')) as check:
                with self.assertRaises(readiness.SemanticSearchUnavailable): readiness.check(**options)
                with self.assertRaisesRegex(ValueError, 'approval'): readiness.check(**options)
                self.assertEqual(check.call_count, 1)
                build.assert_not_called()

    def test_local_scoring_preparation_defers_cloud_and_pending_index_work(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);vault,resumes=fixture(root)
            cache=root/'private/readiness.json'
            cache.parent.mkdir();cache.with_name(cache.name+'.hybrid-pending.json').write_text('{}')
            with patch.object(readiness,'build_chroma_index',side_effect=AssertionError('cloud')), \
                 patch.object(readiness,'run_check_index',side_effect=AssertionError('cloud')):
                result=readiness.check(vault=vault,resumes_dir=resumes,hybrid_search=True,
                    pdftotext=PDF,cache_path=cache,defer_hybrid=True)
                self.assertTrue(result['hybrid_search'])
                self.assertIn('Built Python services.',result['resumes']['ai.pdf'])

    def test_pending_index_is_shared_across_cache_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);vault,resumes=fixture(root)
            options=dict(vault=vault,resumes_dir=resumes,hybrid_search=True,pdftotext=PDF)
            with patch.object(readiness,'build_chroma_index') as build, \
                 patch.object(readiness,'run_check_index',side_effect=readiness.SemanticSearchUnavailable('unknown usage')):
                with self.assertRaises(readiness.SemanticSearchUnavailable):
                    readiness.check(**options,cache_path=root/'a/readiness.json')
                with self.assertRaisesRegex(ValueError,'approval'):
                    readiness.check(**options,cache_path=root/'b/readiness.json')
                self.assertEqual(build.call_count,1)

    def test_overlapping_index_work_is_busy_then_reuses_completed_index(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);vault,resumes=fixture(root)
            options=dict(vault=vault,resumes_dir=resumes,hybrid_search=True,pdftotext=PDF,cache_path=root/'private/readiness.json')
            entered=threading.Event();release=threading.Event()
            def running(*args):
                entered.set()
                if not release.wait(5):raise AssertionError('fixture release timeout')
            with patch.object(readiness,'build_chroma_index',side_effect=running) as build, \
                 patch.object(readiness,'run_check_index'),ThreadPoolExecutor(max_workers=1) as workers:
                first=workers.submit(readiness.check,**options)
                try:
                    self.assertTrue(entered.wait(3))
                    with self.assertRaisesRegex(ValueError,'busy'):
                        readiness.check(**options,authorize_paid_retry=True)
                finally:release.set()
                first.result(timeout=5)
                result=readiness.check(**options)
                self.assertTrue(result['reused'])
                self.assertEqual(build.call_count,1)

    def test_hybrid_diagnostics_do_not_pollute_json_stdout(self):
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as directory:
            vault, _ = fixture(Path(directory))
            output = io.StringIO()
            with patch.object(readiness, 'build_chroma_index', side_effect=lambda *args: print('index progress')), \
                 patch.object(readiness, 'run_check_index', side_effect=lambda *args: print('index current')), \
                 contextlib.redirect_stdout(output):
                readiness.ensure_hybrid(vault)
            self.assertEqual(output.getvalue(), '')
