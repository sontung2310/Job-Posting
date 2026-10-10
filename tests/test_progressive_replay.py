"""Public read-only saved-response audit; synthetic fixtures contain no personal data."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / '.agents/skills/job-retrieval/scripts/verify_saved_run.py'

class SavedRunAuditTests(unittest.TestCase):
    def test_reports_duplicates_and_dates_without_changing_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'checkpoint.json'
            data = {'tasks': [{'source':'linkedin','args':{},'jobs':[
                {'id':'a','postedAt':'2026-10-08'}, {'id':'a','postedAt':'2026-10-08'}]},
                {'source':'seek','args':{'dateRange':2},'jobs':[
                {'id':'b','listedAt':'2026-10-06T01:00:00Z'}]}]}
            path.write_text(json.dumps(data)); before = path.read_bytes()
            result = subprocess.run([sys.executable,str(SCRIPT),'--checkpoint',str(path)], capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report['sources']['linkedin']['raw'],2)
            self.assertEqual(report['sources']['linkedin']['unique'],1)
            self.assertEqual(report['sources']['linkedin']['duplicates'],1)
            self.assertEqual(report['sources']['linkedin']['calendar_only'],2)
            self.assertEqual(report['sources']['seek']['date_ranges'],[2])
            self.assertEqual(path.read_bytes(),before)
