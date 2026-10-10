"""Configured actor contracts through the retrieval CLI; no paid calls."""
import json, subprocess, sys, tempfile, unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CLI=ROOT/'.agents/skills/job-retrieval/scripts/discovery.py'

class ActorMigration(unittest.TestCase):
    def test_new_actor_requests_and_output_fields(self):
        for source in ('seek','linkedin'):
            with self.subTest(source=source), tempfile.TemporaryDirectory() as tmp:
                config = Path(tmp)/'config.yaml'
                config.write_text((ROOT/'config/search_targets.yaml').read_text().replace('websift/seek-job-scraper','bovi/seek-jobs-scraper'))
                def call(command,extra=(),payload=None):
                    p=subprocess.run([sys.executable,str(CLI),command,'--run-id','migration','--state-root',tmp,'--log-root',tmp+'/logs','--config',str(config),*extra],input=json.dumps(payload) if payload else None,capture_output=True,text=True)
                    self.assertEqual(p.returncode,0,p.stderr);return json.loads(p.stdout)
                call('init',['--smoke','--platform',source,'--title','AI Engineer','--location','Melbourne'])
                request=call('next')['requests'][0]
                self.assertIn('bovi' if source=='seek' else 'valig',request['tool'])
                if source=='seek':
                    self.assertFalse(request['args']['includeDescriptions']);self.assertNotIn('dateRange',request['args'])
                else:self.assertEqual(request['args']['datePosted'],'r86400')
                call('accept',['--request-id',request['id']],{'structuredContent':{'runId':'run','status':'SUCCEEDED','storages':{'datasets':{'default':{'id':'data','itemCount':2}}}}})
                request=call('next')['requests'][0]
                now=datetime.now(UTC)-timedelta(minutes=1)
                if source=='seek':
                    rows=[{'job_id':'1','url':'https://www.seek.com.au/job/1','title':'AI Engineer','company':'Acme','location':'Melbourne','listing_date':now.isoformat(),'description_text':'Build machine learning services.'}]
                    self.assertIn('description_text',request['args']['fields'])
                    old=dict(rows[0],job_id='2',url='https://www.seek.com.au/job/2',listing_date=(now-timedelta(days=4)).isoformat())
                else:
                    rows=[{'id':'1','url':'https://www.linkedin.com/jobs/view/1','title':'AI Engineer','companyName':'Acme','location':'Melbourne','postedDate':now.replace(hour=0,minute=0,second=0,microsecond=0).isoformat(),'description':'Build machine learning services.'}]
                    self.assertIn('postedDate',request['args']['fields'])
                    old=dict(rows[0],id='2',url='https://www.linkedin.com/jobs/view/2',postedDate=(now-timedelta(days=4)).date().isoformat())
                call('accept',['--request-id',request['id']],{'structuredContent':{'datasetId':'data','offset':0,'totalItemCount':2,'items':rows+[old]}})
                result=call('finish');jobs=json.loads(Path(result['jobs_path']).read_text())
                self.assertEqual(len(jobs),1);self.assertEqual(jobs[0]['source_job_id'],'1');self.assertEqual(jobs[0]['company'],'Acme');self.assertEqual(jobs[0]['description_text'],'Build machine learning services.')
                self.assertEqual(jobs[0]['freshness_provenance']['provider_filtered'],source=='linkedin')
                if source=='linkedin':self.assertNotEqual(jobs[0]['freshness_provenance']['precision'],'exact')

    def test_longer_linkedin_window_uses_supported_covering_preset(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=[sys.executable,str(CLI),'--run-id','long','--state-root',tmp]
            p=subprocess.run(base+['init','--smoke','--platform','linkedin','--title','AI Engineer','--location','Melbourne','--lookback-hours','48'],capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr)
            p=subprocess.run(base+['next'],capture_output=True,text=True);self.assertEqual(p.returncode,0,p.stderr)
            self.assertEqual(json.loads(p.stdout)['requests'][0]['args']['datePosted'],'r604800')
