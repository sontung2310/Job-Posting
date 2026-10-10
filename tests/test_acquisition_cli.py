from charge_contract_fixture import mock_charge_contracts
import json, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT/'.agents/skills/job-retrieval/scripts/discovery.py'
class AcquisitionCLI(unittest.TestCase):
    def test_bounded_seek_request_uses_date_filter_and_disables_salary_lookup(self):
        with tempfile.TemporaryDirectory() as tmp:
            contract=mock_charge_contracts(Path(tmp))
            base=[sys.executable,str(CLI),'--run-id','a','--state-root',tmp,'--cache-root',tmp+'/cache','--charge-contracts',str(contract),'--charge-limit-usd','0.5']
            r=subprocess.run(base+['init','--acquisition','--platform','seek','--title','AI Engineer','--location','Melbourne','--max-results','10'],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            r=subprocess.run(base+['next'],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            result=json.loads(r.stdout)
            self.assertEqual(len(result['requests']),1)
            self.assertEqual(result['requests'][0]['args']['dateRange'],1)
            self.assertFalse(result['requests'][0]['args']['findSalaries'])
            self.assertEqual(result['requests'][0]['args']['maxResults'],10)
    def test_filtered_calendar_date_retained_with_uncertainty_and_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            contract=mock_charge_contracts(Path(tmp))
            def call(run,command,extra=(),payload=None):
                r=subprocess.run([sys.executable,str(CLI),command,'--run-id',run,'--state-root',tmp,'--cache-root',tmp+'/cache','--charge-contracts',str(contract),'--charge-limit-usd','0.5','--log-root',tmp+'/logs',*extra],input=json.dumps(payload) if payload else None,capture_output=True,text=True)
                self.assertEqual(r.returncode,0,r.stderr)
                return json.loads(r.stdout)
            call('a','init',['--acquisition','--platform','linkedin','--title','AI Engineer','--location','Melbourne','--max-results','10'])
            request=call('a','next')['requests'][0]
            call('a','accept',['--request-id',request['id']],{'structuredContent':{'runId':'run1','status':'SUCCEEDED','storages':{'datasets':{'default':{'id':'data1','itemCount':1}}}}})
            request=call('a','next')['requests'][0]
            from datetime import datetime, UTC
            row={'id':'1','link':'https://www.linkedin.com/jobs/view/1','companyName':'Acme','title':'AI Engineer','location':'Melbourne','postedAt':datetime.now(UTC).date().isoformat(),'descriptionText':'Build AI applications'}
            call('a','accept',['--request-id',request['id']],{'structuredContent':{'datasetId':'data1','offset':0,'totalItemCount':1,'items':[row]}})
            summary=call('a','finish')
            jobs=json.loads(Path(summary['jobs_path']).read_text())
            self.assertEqual(jobs[0]['freshness_class'],'uncertain')
            self.assertTrue(jobs[0]['freshness_provenance']['provider_filtered'])
            result=call('b','init',['--acquisition','--platform','linkedin','--title','AI Engineer','--location','Melbourne','--max-results','10'])
            self.assertTrue(result['reused'])
            self.assertEqual(call('b','next')['requests'],[])
    def test_unknown_submission_cannot_be_relaunched_in_another_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            contract=mock_charge_contracts(Path(tmp))
            def call(root,command):
                args=[sys.executable,str(CLI),command,'--run-id','a','--state-root',root,'--cache-root',tmp+'/cache','--charge-contracts',str(contract),'--charge-limit-usd','0.5']
                if command=='init': args+=['--acquisition','--platform','seek','--title','AI Engineer','--location','Melbourne','--max-results','10']
                return subprocess.run(args,capture_output=True,text=True)
            self.assertEqual(call(tmp+'/first','init').returncode,0)
            self.assertEqual(call(tmp+'/first','next').returncode,0)
            retry=call(tmp+'/second','init')
            self.assertNotEqual(retry.returncode,0)
            self.assertIn('reconciliation/resume',retry.stderr)
    def test_expired_completed_cache_allows_fresh_daily_acquisition(self):
        with tempfile.TemporaryDirectory() as tmp:
            contract=mock_charge_contracts(Path(tmp))
            def call(run,command):
                args=[sys.executable,str(CLI),command,'--run-id',run,'--state-root',tmp,'--cache-root',tmp+'/cache','--charge-contracts',str(contract),'--charge-limit-usd','0.5']
                if command=='init': args+=['--acquisition','--platform','seek','--title','AI Engineer','--location','Melbourne','--max-results','10']
                r=subprocess.run(args,capture_output=True,text=True)
                self.assertEqual(r.returncode,0,r.stderr)
                return json.loads(r.stdout)
            call('a','init');call('a','next')
            checkpoint=Path(tmp)/'a/checkpoint.json'
            saved=json.loads(checkpoint.read_text());saved['tasks'][0].update(phase='done',inflight=None,window_end='2026-01-01T00:00:00+00:00')
            checkpoint.write_text(json.dumps(saved))
            result=call('b','init')
            self.assertFalse(result['reused'])
            self.assertEqual(len(call('b','next')['requests']),1)
            self.assertEqual(result['acquisition']['max_results'],10)
    def test_new_full_retrieval_uses_rolling_filter_without_widening(self):
        with tempfile.TemporaryDirectory() as tmp:
            contract=mock_charge_contracts(Path(tmp))
            args=[sys.executable,str(CLI),'--run-id','full','--state-root',tmp,'--cache-root',tmp+'/cache','--charge-contracts',str(contract),'--charge-limit-usd','0.5']
            result=subprocess.run(args+['init'],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run(args+['next','--limit','4'],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            requests=json.loads(result.stdout)['requests']
            seek=next(r for r in requests if 'seek' in r['tool'])
            self.assertEqual(seek['args']['dateRange'],1)
            linkedin=next(r for r in requests if 'linkedin' in r['tool'])
            self.assertEqual(linkedin['args']['datePosted'],'r86400')
