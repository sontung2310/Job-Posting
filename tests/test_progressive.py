import json
from charge_contract_fixture import mock_charge_contracts
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CLI=ROOT/'.agents/skills/job-search/scripts/progressive.py'
class ProgressiveCLI(unittest.TestCase):
    def test_round_robin_waits_for_batch_and_resume_keeps_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            run=Path(tmp)/'run'
            def call(*args):
                if args[0]=='ingest':
                    cp=Path(args[args.index('--coverage')+1]);cov=json.loads(cp.read_text());pending=json.loads((run/'session.json').read_text())['pending'];cov['acquisition']={k:pending[k] for k in ('source','title','location','lookback_hours','max_results')};cp.write_text(json.dumps(cov))
                p=subprocess.run([sys.executable,str(CLI),*args,'--run',str(run),'--charge-contracts',str(mock_charge_contracts(Path(tmp))),'--acquisition-cache',str(Path(tmp)/'cache'),'--outcome-cache',str(Path(tmp)/'outcome-cache'),*(['--config',str(root/'config.yaml')] if 'root' in locals() and (root/'config.yaml').exists() else [])],capture_output=True,text=True)
                self.assertEqual(p.returncode,0,p.stderr)
                return json.loads(p.stdout)
            call('init','--queries',json.dumps([{'title':'AI Engineer','location':'Melbourne'},{'title':'AI Engineer','location':'Sydney'}]))
            first=call('next')
            self.assertEqual(first['source'],'seek')
            self.assertEqual(call('next'),first)
            handoff=Path(tmp)/'jobs.json';handoff.write_text('[]')
            coverage=Path(tmp)/'coverage.json';coverage.write_text('{"raw_count":0,"status":"complete","source_unavailable":true}')
            relevance=Path(tmp)/'relevance.json';relevance.write_text('[]')
            call('ingest','--handoff',str(handoff),'--coverage',str(coverage),'--relevance',str(relevance))
            self.assertEqual(call('next')['source'],'linkedin')
            self.assertGreater(float(call('status')['reserved_usd']),0)
            self.assertEqual(call('status')['query_positions']['seek'],2)

    def test_fifth_qualifier_preserves_queue_and_report_selects_original_evidence(self):
        import sys
        sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'.agents/skills/job-scoring/scripts')]
        import assessment
        import assessment_validation as validation
        from assessment_fixture import fixture
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run=root/'session';vault,resumes=fixture(root)
            import yaml
            settings=yaml.safe_load((ROOT/'config/search_targets.yaml').read_text());settings['hybrid_search']=False
            config=root/'config.yaml';config.write_text(yaml.safe_dump(settings))
            def call(*args):
                if args[0]=='ingest':
                    cp=Path(args[args.index('--coverage')+1]);cov=json.loads(cp.read_text());pending=json.loads((run/'session.json').read_text())['pending'];cov['acquisition']={k:pending[k] for k in ('source','title','location','lookback_hours','max_results')};cp.write_text(json.dumps(cov))
                p=subprocess.run([sys.executable,str(CLI),*args,'--run',str(run),'--charge-contracts',str(mock_charge_contracts(Path(tmp))),'--acquisition-cache',str(Path(tmp)/'cache'),'--outcome-cache',str(Path(tmp)/'outcome-cache'),*(['--config',str(root/'config.yaml')] if 'root' in locals() and (root/'config.yaml').exists() else [])],capture_output=True,text=True)
                self.assertEqual(p.returncode,0,p.stderr)
                return json.loads(p.stdout)
            call('init','--queries','[{"title":"AI Engineer","location":"Melbourne"}]')
            call('next')
            jobs=[{'job_url':f'https://example.test/{i}','company':f'Co{i}','position':'AI Engineer','description_text':'Build Python services.'} for i in range(10)]
            handoff=root/'jobs.json';handoff.write_text(json.dumps(jobs))
            coverage=root/'coverage.json';coverage.write_text('{"raw_row_count":10}')
            relevance=root/'relevance.json';relevance.write_text(json.dumps([{'job_id':validation.job_id(j),'status':'relevant','reason':'Python AI service role'} for j in jobs]))
            call('ingest','--handoff',str(handoff),'--coverage',str(coverage),'--relevance',str(relevance))
            for _ in range(5):
                action=call('next');self.assertEqual(action['action'],'assess')
                state=Path(action['assessment_run'])
                manifest=assessment.prepare_run(Path(action['input']),state,vault,resumes,hybrid_search=False)
                identifier=action['job_id']
                assessment.submit_requirements(state,{'jobs':[{'job_handle':identifier,'condition':{'reviewer':'codex','status':'passed','reason':'No required conditions','clauses':[]},'classified':{'units':[{'id':1,'category':'ignore','priority':1,'reason':'Title'},{'id':2,'category':'Skills','priority':3,'reason':'Required delivery'}]}}]})
                template=json.loads((state/f'{identifier}-review-template.json').read_text())
                req=template['requirements'][0]
                req.update(candidate_strength='direct',candidate_reason='Verified Python delivery',evidence=[{'path':'05 Evidence/Python.md','heading':'Claim'}],resume_strengths={'ai.pdf':'direct','cv.pdf':'missing'},resume_lines={'ai.pdf':[1],'cv.pdf':[]})
                assessment.submit_judgments(state,{'jobs':[{'job_handle':identifier,'category':'AI Agent','requirements':[req]}]})
                call('assessed','--assessment-run',str(state))
            self.assertEqual(call('next')['reason'],'eligible_target')
            summary=call('status');self.assertEqual(summary['assessed'],5);self.assertEqual(len(summary['queue']),5)
            published=call('report');self.assertTrue(published['selectable'])
            frozen=(Path(published['run_handle'])/'report.json').read_bytes()
            rejected=subprocess.run([sys.executable,str(CLI),'assessed','--run',str(run),'--assessment-run',str(state)],capture_output=True,text=True)
            self.assertNotEqual(rejected.returncode,0)
            self.assertIn('session stopped',rejected.stderr)
            call('report')
            self.assertEqual((Path(published['run_handle'])/'report.json').read_bytes(),frozen)
            sys.path.insert(0,str(ROOT/'.agents/skills/job-suggestions/scripts'))
            import approved_preparation
            selected=approved_preparation.select_candidates(Path(published['run_handle']),published['report_id'],[1])
            self.assertEqual(len(selected['selected']),1)
            other=root/'other-session'
            def other_call(*args):
                if args[0]=='ingest':
                    cp=Path(args[args.index('--coverage')+1]);cov=json.loads(cp.read_text());pending=json.loads((other/'session.json').read_text())['pending'];cov['acquisition']={k:pending[k] for k in ('source','title','location','lookback_hours','max_results')};cp.write_text(json.dumps(cov))
                p=subprocess.run([sys.executable,str(CLI),*args,'--run',str(other),'--charge-contracts',str(mock_charge_contracts(Path(tmp))),'--acquisition-cache',str(Path(tmp)/'cache'),'--outcome-cache',str(Path(tmp)/'outcome-cache'),'--config',str(config)],capture_output=True,text=True)
                self.assertEqual(p.returncode,0,p.stderr);return json.loads(p.stdout)
            other_call('init','--queries','[{"title":"AI Engineer","location":"Melbourne"}]')
            other_call('next')
            other_call('ingest','--handoff',str(handoff),'--coverage',str(coverage),'--relevance',str(relevance))
            self.assertTrue(other_call('next')['reused'])
            cached=Path(other_call('next')['assessment_run'])
            other_call('assessed','--assessment-run',str(cached))
            self.assertEqual(other_call('status')['assessed'],1)
            evidence=vault/'05 Evidence/Python.md'
            evidence.write_text(evidence.read_text()+'\nChanged verified evidence.\n')
            other=root/'changed-session'
            other_call('init','--queries','[{"title":"AI Engineer","location":"Melbourne"}]')
            other_call('next')
            other_call('ingest','--handoff',str(handoff),'--coverage',str(coverage),'--relevance',str(relevance))
            self.assertNotIn('reused',other_call('next'))

    def test_budget_reservations_survive_restart_without_paid_prefetch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run=root/'session'
            def call(*args):
                if args[0]=='ingest':
                    cp=Path(args[args.index('--coverage')+1]);cov=json.loads(cp.read_text());pending=json.loads((run/'session.json').read_text())['pending'];cov['acquisition']={k:pending[k] for k in ('source','title','location','lookback_hours','max_results')};cp.write_text(json.dumps(cov))
                p=subprocess.run([sys.executable,str(CLI),*args,'--run',str(run),'--charge-contracts',str(mock_charge_contracts(Path(tmp))),'--acquisition-cache',str(Path(tmp)/'cache'),'--outcome-cache',str(Path(tmp)/'outcome-cache'),*(['--config',str(root/'config.yaml')] if 'root' in locals() and (root/'config.yaml').exists() else [])],capture_output=True,text=True)
                self.assertEqual(p.returncode,0,p.stderr)
                return json.loads(p.stdout)
            queries=[{'title':'AI Engineer','location':f'City{i}'} for i in range(50)]
            call('init','--queries',json.dumps(queries))
            jobs=root/'jobs.json';jobs.write_text('[]')
            cov=root/'coverage.json';cov.write_text('{"raw_row_count":0}')
            rel=root/'relevance.json';rel.write_text('[]')
            for _ in range(150):
                action=call('next')
                if action['action']=='report':break
                self.assertEqual(call('next'),action)
                call('ingest','--handoff',str(jobs),'--coverage',str(cov),'--relevance',str(rel))
            self.assertLessEqual(float(call('status')['reserved_usd']),.5)
            self.assertEqual(call('next')['action'],'report')

    def test_condition_failures_count_toward_configured_admission_limit(self):
        sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'.agents/skills/job-scoring/scripts')]
        import assessment
        import assessment_validation as validation
        from assessment_fixture import fixture
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run=root/'session';vault,resumes=fixture(root)
            config=root/'config.yaml'
            config.write_text('sources: {seek: {enabled: true, actor: "websift/seek-job-scraper"}, linkedin: {enabled: true, actor: "valig/linkedin-jobs-scraper"}, indeed: {enabled: true}}\nsearches: []\nhybrid_search: false\nprogressive_search: {assessment_limit: 100, batch_size: 100}\n')
            def call(*args):
                if args[0]=='ingest':
                    cp=Path(args[args.index('--coverage')+1]);cov=json.loads(cp.read_text());pending=json.loads((run/'session.json').read_text())['pending'];cov['acquisition']={k:pending[k] for k in ('source','title','location','lookback_hours','max_results')};cp.write_text(json.dumps(cov))
                p=subprocess.run([sys.executable,str(CLI),*args,'--run',str(run),'--charge-contracts',str(mock_charge_contracts(Path(tmp))),'--acquisition-cache',str(Path(tmp)/'cache'),'--outcome-cache',str(Path(tmp)/'outcome-cache'),*(['--config',str(root/'config.yaml')] if 'root' in locals() and (root/'config.yaml').exists() else [])],capture_output=True,text=True)
                self.assertEqual(p.returncode,0,p.stderr);return json.loads(p.stdout)
            call('init','--config',str(config),'--queries','[{"title":"AI Engineer","location":"Melbourne"}]')
            call('next')
            jobs=[{'job_url':f'https://example.test/fail{i}','company':f'Co{i}','position':'AI Engineer','description_text':'Australian citizenship required.'} for i in range(100)]
            handoff=root/'jobs.json';handoff.write_text(json.dumps(jobs))
            coverage=root/'coverage.json';coverage.write_text('{"raw_row_count":100}')
            relevance=root/'relevance.json';relevance.write_text(json.dumps([{'job_id':validation.job_id(j),'status':'uncertain','reason':'Role duties not available'} for j in jobs]))
            call('ingest','--handoff',str(handoff),'--coverage',str(coverage),'--relevance',str(relevance))
            for _ in range(100):
                action=call('next');state=Path(action['assessment_run']);identifier=action['job_id']
                assessment.prepare_run(Path(action['input']),state,vault,resumes,hybrid_search=False)
                assessment.submit_requirements(state,{'jobs':[{'job_handle':identifier,'condition':{'reviewer':'codex','status':'failed','reason':'Verified mismatch','clauses':[{'wording':'Australian citizenship required.','kind':'work_rights','status':'failed','reason':'Verified mismatch','profile_fields':['work_authorization.australian_citizen']}]}}]})
                call('assessed','--assessment-run',str(state))
            self.assertEqual(call('next')['reason'],'assessment_limit')
            self.assertEqual(call('status')['eligible'],0)
            self.assertEqual(len(call('status')['queue']),0)

    def test_two_low_relevance_batches_stop_only_that_query(self):
        sys.path.insert(0,str(ROOT/'scripts'))
        import assessment_validation as validation
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run=root/'session'
            config=root/'config.yaml';config.write_text('sources: {seek: {enabled: true, actor: "websift/seek-job-scraper"}}\nsearches: []\n')
            contract=root/'contract.json';contract.write_text('{"seek":{"continuation":true,"evidence":"Mocked provider contract supports a nonrepeat cursor"}}')
            def call(*args):
                if args[0]=='ingest':
                    cp=Path(args[args.index('--coverage')+1]);cov=json.loads(cp.read_text());pending=json.loads((run/'session.json').read_text())['pending'];cov['acquisition']={k:pending[k] for k in ('source','title','location','lookback_hours','max_results')};cp.write_text(json.dumps(cov))
                p=subprocess.run([sys.executable,str(CLI),*args,'--run',str(run),'--charge-contracts',str(mock_charge_contracts(Path(tmp))),'--acquisition-cache',str(Path(tmp)/'cache'),'--outcome-cache',str(Path(tmp)/'outcome-cache'),*(['--config',str(root/'config.yaml')] if 'root' in locals() and (root/'config.yaml').exists() else [])],capture_output=True,text=True)
                self.assertEqual(p.returncode,0,p.stderr);return json.loads(p.stdout)
            call('init','--config',str(config),'--capabilities',str(contract),'--queries','[{"title":"AI Engineer","location":"Melbourne"},{"title":"Machine Learning Engineer","location":"Melbourne"}]')
            for batch in range(2):
                action=call('next');self.assertEqual(action['title'],'AI Engineer')
                jobs=[{'job_url':f'https://example.test/unrelated-{batch}-{i}','company':f'Co{i}','position':'Plumber','description_text':'Repair pipes.'} for i in range(10)]
                handoff=root/'jobs.json';handoff.write_text(json.dumps(jobs))
                coverage=root/'coverage.json';coverage.write_text(json.dumps({'raw_row_count':10,'continuation':'verified','cursor':f'page{batch+2}'}))
                relevance=root/'relevance.json';relevance.write_text(json.dumps([{'job_id':validation.job_id(j),'status':'irrelevant','reason':'Plumbing duties, unrelated role family'} for j in jobs]))
                call('ingest','--handoff',str(handoff),'--coverage',str(coverage),'--relevance',str(relevance))
            self.assertEqual(call('next')['title'],'Machine Learning Engineer')
            self.assertEqual(call('status')['coverage'][-1]['stop_reason'],'low_relevance')

    def test_downloaded_surplus_is_consumed_before_another_paid_query(self):
        sys.path.insert(0,str(ROOT/'scripts'))
        import assessment_validation as validation
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run=root/'session'
            config=root/'config.yaml';config.write_text('sources: {seek: {enabled: true, actor: "websift/seek-job-scraper"}}\nsearches: []\n')
            def call(*args):
                if args[0]=='ingest':
                    cp=Path(args[args.index('--coverage')+1]);cov=json.loads(cp.read_text());pending=json.loads((run/'session.json').read_text())['pending'];cov['acquisition']={k:pending[k] for k in ('source','title','location','lookback_hours','max_results')};cp.write_text(json.dumps(cov))
                p=subprocess.run([sys.executable,str(CLI),*args,'--run',str(run),'--charge-contracts',str(mock_charge_contracts(Path(tmp))),'--acquisition-cache',str(Path(tmp)/'cache'),'--outcome-cache',str(Path(tmp)/'outcome-cache'),*(['--config',str(root/'config.yaml')] if 'root' in locals() and (root/'config.yaml').exists() else [])],capture_output=True,text=True)
                self.assertEqual(p.returncode,0,p.stderr);return json.loads(p.stdout)
            call('init','--config',str(config),'--queries','[{"title":"AI Engineer","location":"Melbourne"},{"title":"Machine Learning Engineer","location":"Melbourne"}]')
            call('next')
            jobs=[{'job_url':f'https://example.test/cached-{i}','company':f'Co{i}','position':'Plumber','description_text':'Repair pipes.'} for i in range(20)]
            handoff=root/'jobs.json';handoff.write_text(json.dumps(jobs))
            coverage=root/'coverage.json';coverage.write_text('{"raw_row_count":20,"reused":true}')
            relevance=root/'relevance.json';relevance.write_text(json.dumps([{'job_id':validation.job_id(j),'status':'irrelevant','reason':'Plumbing role outside query family'} for j in jobs]))
            call('ingest','--handoff',str(handoff),'--coverage',str(coverage),'--relevance',str(relevance))
            self.assertEqual(float(call('status')['reserved_usd']),0)
            self.assertEqual(call('next')['title'],'Machine Learning Engineer')
            self.assertEqual(call('status')['coverage'][-1]['stop_reason'],'low_relevance')
