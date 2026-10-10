"""Launcher checks real local inputs without contacting job sources."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from assessment_fixture import fixture

ROOT = Path(__file__).resolve().parents[1]
PDF = os.environ.get('PDFTOTEXT_BIN') or shutil.which('pdftotext')

class LauncherTests(unittest.TestCase):
    def test_saved_jobs_readiness_needs_no_source_credentials_and_reuses_current_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT/'scripts', root/'scripts')
            shutil.copytree(ROOT/'.agents', root/'.agents')
            vault, resumes = fixture(root)
            vault.rename(root/'career-vault')
            (root/'career-vault/01 Profile/Target Roles.md').write_text('---\ntype: preferences\nstatus: verified\nsource: user-confirmed: fixture\nlast_verified: 2026-10-01\n---\nPython roles\n')
            (root/'config').mkdir()
            (root/'config/search_targets.yaml').write_text('hybrid_search: false\nsources: {linkedin: {enabled: true}}\n')
            (root/'.venv/bin').mkdir(parents=True)
            (root/'.venv/bin/python').write_text('#!/bin/sh\nexec '+sys.executable+' \"$@\"\n')
            (root/'.venv/bin/python').chmod(0o755)
            env = {k:v for k,v in os.environ.items() if not any(x in k for x in ('APIFY','OPENAI','CHROMA'))}
            env['PDFTOTEXT_BIN'] = PDF
            command = ['bash', str(root/'scripts/run.sh'), '--check', '--scoring-only']
            first = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertFalse(json.loads(first.stdout.splitlines()[0])['reused'])
            second = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertTrue(json.loads(second.stdout.splitlines()[0])['reused'])
            (root/'career-vault/05 Evidence/Python.md').write_text((root/'career-vault/05 Evidence/Python.md').read_text()+'Updated claim\n')
            third = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertEqual(third.returncode, 0, third.stderr)
            self.assertFalse(json.loads(third.stdout.splitlines()[0])['reused'])
            (root/'config/search_targets.yaml').write_text('hybrid_search: false\nsources: {}\n')
            # Substitute only the external Codex/usage boundary to observe routing.
            (root/'scripts/scoring_ledger.py').write_text('import sys\nif "finalize" in sys.argv: sys.stdin.read()\n')
            codex = root/'codex'
            codex.write_text('#!/bin/sh\nprevious=\"\"\nfor argument in \"$@\"; do\n  if [ \"$previous\" = --output-last-message ]; then echo private > \"$argument\"; fi\n  previous=\"$argument\"\ndone\nprintf "%s\\n" "$@" > "'+str(root/'invocation')+'"\necho "{}"\n')
            codex.chmod(0o755)
            env['CODEX_BIN'] = str(codex)
            jobs = root/'saved.json'; jobs.write_text('[]')
            for options, required, excluded in [
                ([], 'job-search/SKILL.md', None),
                (['--retrieval-only', '--lookback-hours', '48'], 'job-retrieval/SKILL.md', 'job-scoring/SKILL.md'),
                (['--scoring-only', '--input', str(jobs)], 'job-scoring/SKILL.md', 'job-retrieval/SKILL.md'),
            ]:
                run = subprocess.run(['bash', str(root/'scripts/run.sh')]+options, env=env, capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertEqual((root/'invocation').stat().st_mode & 0o777, 0o600)
                self.assertEqual((root/'reports').stat().st_mode & 0o777, 0o700)
                self.assertTrue(list((root/'reports').glob('*.md')))
                self.assertTrue(all(path.stat().st_mode & 0o777 == 0o600 for path in (root/'reports').glob('*.md')))
                invocation = (root/'invocation').read_text()
                self.assertIn(required, invocation)
                if excluded: self.assertNotIn(excluded, invocation)
                if not options:
                    self.assertIn('progressive', invocation)
                    self.assertIn('Continue through the ranked scoring report', invocation)
                if '--retrieval-only' not in options:
                    self.assertIn('await current-report selection', invocation)
                if '--lookback-hours' in options: self.assertIn('override hours: 48', invocation)
            invalid = subprocess.run(command+['--lookback-hours', '0'], env=env, capture_output=True, text=True)
            self.assertNotEqual(invalid.returncode, 0)

if __name__ == '__main__':
    unittest.main()
