import json, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CLI=ROOT/'.agents/skills/job-search/scripts/progressive.py'
class ProgressiveRepairs(unittest.TestCase):
    def test_unverified_paid_sources_are_blocked_while_indeed_proceeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            run=Path(tmp)/'run'
            def call(command):
                p=subprocess.run([sys.executable,str(CLI),command,'--run',str(run),'--acquisition-cache',tmp+'/cache'],capture_output=True,text=True)
                self.assertEqual(p.returncode,0,p.stderr);return json.loads(p.stdout)
            call('init');action=call('next')
            self.assertEqual(action['source'],'indeed')
            self.assertEqual(float(call('status')['reserved_usd']),0)
            self.assertEqual(len([r for r in call('status')['coverage'] if r.get('stop_reason')=='unverified_charge_ceiling']),2)

    def test_configured_cap_is_used_and_connector_ceiling_is_forwarded(self):
        from charge_contract_fixture import mock_charge_contracts
        import yaml
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);config=root/'config.yaml';settings=yaml.safe_load((ROOT/'config/search_targets.yaml').read_text());settings['max_results_per_search_per_source']=1;config.write_text(yaml.safe_dump(settings));contract=mock_charge_contracts(root)
            def call(command):
                p=subprocess.run([sys.executable,str(CLI),command,'--run',tmp+'/run','--config',str(config),'--charge-contracts',str(contract),'--acquisition-cache',tmp+'/cache'],capture_output=True,text=True)
                self.assertEqual(p.returncode,0,p.stderr);return json.loads(p.stdout)
            call('init');action=call('next');self.assertEqual(action['max_results'],1);self.assertEqual(action['charge_limit_usd'],'0.0025')
            discovery=ROOT/'.agents/skills/job-retrieval/scripts/discovery.py'
            args=[sys.executable,str(discovery),'--run-id','a','--state-root',tmp+'/acq','--cache-root',tmp+'/cache','--config',str(config),'--charge-contracts',str(contract),'--charge-limit-usd',action['charge_limit_usd']]
            p=subprocess.run(args+['init','--acquisition','--platform','seek','--title',action['title'],'--location',action['location'],'--max-results','1'],capture_output=True,text=True);self.assertEqual(p.returncode,0,p.stderr)
            p=subprocess.run(args+['next'],capture_output=True,text=True);self.assertEqual(p.returncode,0,p.stderr)
            request=json.loads(p.stdout)['requests'][0];self.assertEqual(request['args']['maxResults'],1);self.assertEqual(request['args']['maxTotalChargeUsd'],.0025)

    def test_exhausted_budget_still_probes_later_query_cache(self):
        from charge_contract_fixture import mock_charge_contracts
        import yaml
        from datetime import datetime,UTC
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);config=root/'config.yaml';settings=yaml.safe_load((ROOT/'config/search_targets.yaml').read_text());settings['sources']['linkedin']['enabled']=False;settings['sources']['indeed']['enabled']=False;settings['max_results_per_search_per_source']=1;settings['searches']=[{'title':'AI Engineer','location':['Melbourne']},{'title':'Machine Learning Engineer','location':['Melbourne']}];settings['progressive_search']={'budget_usd':'0.0001'};config.write_text(yaml.safe_dump(settings));contract=mock_charge_contracts(root)
            discovery=ROOT/'.agents/skills/job-retrieval/scripts/discovery.py'
            def acquire(command,extra=(),payload=None):
                args=[sys.executable,str(discovery),command,'--run-id','cached','--state-root',tmp+'/acq','--cache-root',tmp+'/cache','--config',str(config),'--charge-contracts',str(contract),'--charge-limit-usd','0.0025',*extra]
                p=subprocess.run(args,input=json.dumps(payload) if payload else None,capture_output=True,text=True);self.assertEqual(p.returncode,0,p.stderr);return json.loads(p.stdout)
            acquire('init',['--acquisition','--platform','seek','--title','Machine Learning Engineer','--location','Melbourne','--max-results','1'])
            request=acquire('next')['requests'][0]
            acquire('accept',['--request-id',request['id']],{'structuredContent':{'runId':'run','status':'SUCCEEDED','storages':{'datasets':{'default':{'id':'data','itemCount':1}}}}})
            request=acquire('next')['requests'][0]
            row={'id':'1','jobLink':'https://www.seek.com.au/job/1','title':'Machine Learning Engineer','listedAt':datetime.now(UTC).isoformat(),'advertiser':{'name':'Co'},'content':{'unEditedContent':'Build machine learning services.'}}
            acquire('accept',['--request-id',request['id']],{'structuredContent':{'datasetId':'data','offset':0,'totalItemCount':1,'items':[row]}})
            acquire('finish')
            def session(command):
                p=subprocess.run([sys.executable,str(CLI),command,'--run',tmp+'/run','--config',str(config),'--charge-contracts',str(contract),'--acquisition-cache',tmp+'/cache'],capture_output=True,text=True);self.assertEqual(p.returncode,0,p.stderr);return json.loads(p.stdout)
            session('init');action=session('next');self.assertTrue(action['reused']);self.assertEqual(action['title'],'Machine Learning Engineer');self.assertEqual(float(session('status')['reserved_usd']),0)

    def test_35_replay_labels_preserve_ambiguity_and_exclude_irrelevance(self):
        from charge_contract_fixture import mock_charge_contracts
        import hashlib,yaml
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);config=root/'config.yaml';settings=yaml.safe_load((ROOT/'config/search_targets.yaml').read_text());settings['progressive_search']={'batch_size':35};config.write_text(yaml.safe_dump(settings));contract=mock_charge_contracts(root)
            def call(command,extra=()):
                p=subprocess.run([sys.executable,str(CLI),command,'--run',tmp+'/run','--config',str(config),'--charge-contracts',str(contract),'--acquisition-cache',tmp+'/cache',*extra],capture_output=True,text=True);self.assertEqual(p.returncode,0,p.stderr);return json.loads(p.stdout)
            call('init');action=call('next')
            jobs=[{'job_url':f'https://example.test/replay{i}','company':f'Co{i}','position':'Fixture role','description_text':f'Adjudicated fixture duties {i}'} for i in range(35)]
            labels=['irrelevant']*18+['relevant']*6+['uncertain']*11
            judgments=[{'job_id':hashlib.sha256(j['job_url'].encode()).hexdigest()[:16],'status':status,'reason':'Saved benchmark adjudication policy fixture'} for j,status in zip(jobs,labels)]
            handoff=root/'jobs.json';handoff.write_text(json.dumps(jobs));coverage=root/'coverage.json';coverage.write_text(json.dumps({'raw_row_count':35,'acquisition':{k:action[k] for k in ('source','title','location','lookback_hours','max_results')}}));relevance=root/'relevance.json';relevance.write_text(json.dumps(judgments))
            result=call('ingest',['--handoff',str(handoff),'--coverage',str(coverage),'--relevance',str(relevance)]);self.assertEqual(result['queued'],17)
            self.assertEqual(len(call('status')['seen']),35)
            self.assertEqual([j['job_url'] for j in call('status')['queue']],[j['job_url'] for j in jobs[18:]])

    def test_unknown_cached_submission_requires_reconciliation_before_budget(self):
        from charge_contract_fixture import mock_charge_contracts
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);contract=mock_charge_contracts(root);discovery=ROOT/'.agents/skills/job-retrieval/scripts/discovery.py'
            args=[sys.executable,str(discovery),'--run-id','unknown','--state-root',tmp+'/acq','--cache-root',tmp+'/cache','--charge-contracts',str(contract),'--charge-limit-usd','0.025']
            for command in (['init','--acquisition','--platform','seek','--title','AI Engineer','--location','Melbourne','--max-results','10'],['next']):
                p=subprocess.run(args+command,capture_output=True,text=True);self.assertEqual(p.returncode,0,p.stderr)
            def call(command):
                p=subprocess.run([sys.executable,str(CLI),command,'--run',tmp+'/run','--acquisition-cache',tmp+'/cache'],capture_output=True,text=True);self.assertEqual(p.returncode,0,p.stderr);return json.loads(p.stdout)
            call('init');action=call('next');self.assertEqual(action['action'],'reconcile');self.assertEqual(call('next'),action)
            self.assertEqual(float(call('status')['reserved_usd']),0)
