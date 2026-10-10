"""Local recovery tests: no provider calls or paid work."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('progressive_recovery',ROOT/'.agents/skills/job-search/scripts/progressive.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.run=self.root/'run';self.checkpoint=self.root/'checkpoint.json';self.checkpoint.write_text('{}')
        config=self.root/'config.yaml';config.write_text('sources: {indeed: {enabled: true}}\nsearches: []\n')
        self.s=p.initialize(self.run,[{'title':'AI Engineer','location':'Melbourne'},{'title':'AI Engineer','location':'Sydney'}],config,self.root/'outcomes',acquisition_cache=self.root/'cache')
        self.jobs=[{'job_url':f'https://example.test/{i}','company':f'Co{i}','position':'AI Engineer','description_text':'Build models'} for i in range(2)]
    def defer(self,target='assessment',kind='validation_input'):
        return p.defer_work(self.run,self.s,target,kind,'Fixture failure',self.checkpoint)
    def test_new_default_has_no_assessment_cap_and_resume_keeps_legacy_policy(self):
        self.assertIsNone(self.s['policy']['assessment_limit'])
        self.s['policy']['assessment_limit']=100;p.save(self.run,self.s)
        restored=p.initialize(self.run,None,ROOT/'config/search_targets.yaml',self.root/'outcomes')
        self.assertEqual(restored['policy']['assessment_limit'],100)
    def test_bad_job_is_preserved_while_next_job_proceeds_and_report_stays_nonselectable(self):
        self.s['queue']=self.jobs.copy();self.s['reserved_usd']='0.115'
        result=self.defer();self.assertEqual(self.s['queue'],[self.jobs[1]])
        self.assertEqual(p.next_action(self.run,self.s)['job_id'],p.validation.job_id(self.jobs[1]))
        report=p.report(self.run,self.s);self.assertFalse(report['selectable'])
        self.assertEqual(report['summary']['pending_job_count'],2)
        self.assertEqual(report['summary']['deferred_job_count'],1)
        self.assertEqual(self.s['assessed'],0);self.assertEqual(self.s['eligible'],0)
        p.resume_work(self.run,self.s,result['deferred_id']);self.assertEqual(self.s['queue'],self.jobs)
        self.assertEqual(self.s['reserved_usd'],'0.115')

    def test_unknown_evidence_is_deferred_without_stopping_independent_jobs(self):
        from assessment_fixture import fixture
        import assessment
        self.s['scoring_policy']['hybrid_search'] = False
        self.s['queue'] = self.jobs.copy()
        action = p.next_action(self.run, self.s)
        vault, resumes = fixture(self.root)
        state = Path(action['assessment_run'])
        prepared = assessment.prepare_run(Path(action['input']), state, vault, resumes, hybrid_search=False)
        decision = prepared['requirements_template']['jobs'][0]
        decision['condition'].update(status='passed', reason='No gate applies')
        for unit in decision['classified']['units']:
            unit.update(category='ignore' if unit['id'] == 1 else 'Skills', reason='Fixture skill')
        judgment = assessment.submit_requirements(state, {'jobs': [decision]})['judgments_template']['jobs'][0]
        judgment['category'] = 'Hybrid'
        for row in judgment['requirements']:
            row['candidate_reason'] = 'Confirm comparable model delivery.'
        assessment.submit_judgments(state, {'jobs': [judgment]})
        result = p.accept_assessment(self.run, self.s, state)
        self.assertIn('deferred_id', result)
        self.assertEqual(self.s['queue'], [self.jobs[1]])
        self.assertEqual((self.s['assessed'], self.s['eligible']), (0, 0))
        self.assertIsNone(self.s['stop_reason'])
        self.assertEqual(p.next_action(self.run, self.s)['job_id'], p.validation.job_id(self.jobs[1]))
        self.assertIn('0–100', self.s['deferred'][0]['reason'])
        progress = p.progress_report(self.run, self.s)
        self.assertEqual(progress['summary']['evidence_review_job_count'], 1)
        self.assertEqual(progress['summary']['failed_job_count'], 0)
    def test_duplicate_defer_and_resume_do_not_lose_next_job(self):
        self.s['queue']=self.jobs.copy();result=self.defer()
        self.assertEqual(self.defer(),result);self.assertEqual(self.s['queue'],[self.jobs[1]])
        p.resume_work(self.run,self.s,result['deferred_id']);before=json.dumps(self.s,sort_keys=True)
        with self.assertRaisesRegex(ValueError,'unknown deferred-id'):p.resume_work(self.run,self.s,result['deferred_id'])
        self.assertEqual(json.dumps(self.s,sort_keys=True),before)
    def test_wrong_target_and_invalid_checkpoint_do_not_mutate(self):
        self.s['queue']=self.jobs.copy();before=json.dumps(self.s,sort_keys=True)
        with self.assertRaises(ValueError):self.defer('acquisition','source_unavailable')
        with self.assertRaises(ValueError):p.defer_work(self.run,self.s,'assessment','validation_input','bad',self.root/'missing')
        self.assertEqual(json.dumps(self.s,sort_keys=True),before)
    def test_unknown_paid_request_keeps_reservation_and_independent_source_runs(self):
        self.s['search_config']['sources']['seek']={'enabled':True,'actor':'websift/seek-job-scraper'};self.s['enabled_sources']=['seek','indeed'];self.s['reserved_usd']='0.055'
        request={'action':'acquire','source':'seek','title':'AI Engineer','location':'Melbourne','lookback_hours':24,'max_results':10,'acquisition_id':'seek-0','reservation_usd':'0.055'}
        self.s['pending']=request.copy();result=self.defer('acquisition','unknown_submission')
        with patch('discovery.probe_cache',return_value={'reusable':False}):action=p.next_action(self.run,self.s)
        self.assertEqual(action['source'],'indeed');self.assertEqual(self.s['reserved_usd'],'0.055')
        with self.assertRaises(ValueError):p.resume_work(self.run,self.s,result['deferred_id'])
        self.s['pending']=None;p.resume_work(self.run,self.s,result['deferred_id'])
        self.assertEqual(self.s['pending']['reservation_usd'],'0.055')
        self.assertEqual(self.s['pending']['query_position'],0)
    def test_deferred_only_session_is_blocked_not_exhausted(self):
        self.s['queue']=[self.jobs[0]];self.defer();self.s['query_positions']={k:2 for k in p.SOURCES}
        result=p.next_action(self.run,self.s)
        self.assertEqual(result['action'],'blocked');self.assertIsNone(self.s['stop_reason'])
    def ingest_empty(self,raw):
        self.s['pending']={'action':'acquire','source':'indeed','title':'AI Engineer','location':'Melbourne','lookback_hours':24,'max_results':1,'acquisition_id':'indeed-0','reservation_usd':'0'}
        handoff=self.root/'jobs.json';handoff.write_text('[]')
        cov=self.root/'coverage.json';cov.write_text(json.dumps({'raw_row_count':raw,'acquisition':{k:self.s['pending'][k] for k in ('source','title','location','lookback_hours','max_results')}}))
        rel=self.root/'rel.json';rel.write_text('[]');p.ingest(self.run,self.s,handoff,cov,rel)
    def test_reduced_provider_cap_never_claims_exhaustion(self):
        self.ingest_empty(1);self.assertEqual(self.s['coverage'][-1]['stop_reason'],'capped_noncontinuable')
        self.s['query_positions']={k:2 for k in p.SOURCES}
        self.assertEqual(p.next_action(self.run,self.s)['reason'],'coverage_limited')
    def test_uncapped_empty_queries_report_exhaustion(self):
        self.ingest_empty(0);self.s['query_positions']={k:2 for k in p.SOURCES}
        self.assertEqual(p.next_action(self.run,self.s)['reason'],'sources_exhausted')
    def test_resuming_old_acquisition_does_not_reset_later_position(self):
        self.s['pending']={'action':'acquire','source':'indeed','title':'AI Engineer','location':'Melbourne','lookback_hours':24,'max_results':1,'acquisition_id':'indeed-0','reservation_usd':'0'}
        result=self.defer('acquisition','source_unavailable');self.s['query_positions']['indeed']=2
        p.resume_work(self.run,self.s,result['deferred_id'])
        handoff=self.root/'jobs.json';handoff.write_text('[]');rel=self.root/'rel.json';rel.write_text('[]')
        cov=self.root/'coverage.json';cov.write_text(json.dumps({'raw_row_count':0,'acquisition':{k:self.s['pending'][k] for k in ('source','title','location','lookback_hours','max_results')}}))
        p.ingest(self.run,self.s,handoff,cov,rel);self.assertEqual(self.s['query_positions']['indeed'],2)

    def test_terminal_target_can_resolve_deferred_assessment_without_acquiring_more(self):
        from assessment_fixture import fixture
        import assessment
        self.jobs[0]['description_text']='Australian citizenship required.'
        self.s['queue']=self.jobs.copy();result=self.defer()
        self.s['eligible']=5;self.s['stop_reason']='eligible_target'
        p.resume_work(self.run,self.s,result['deferred_id'])
        action=p.next_action(self.run,self.s);self.assertEqual(action['action'],'assess')
        self.assertFalse(p.report(self.run,self.s)['selectable'])
        vault,resumes=fixture(self.root);state=Path(action['assessment_run']);identifier=action['job_id']
        assessment.prepare_run(Path(action['input']),state,vault,resumes,hybrid_search=self.s['scoring_policy']['hybrid_search'])
        assessment.submit_requirements(state,{'jobs':[{'job_handle':identifier,'condition':{'reviewer':'codex','status':'failed','reason':'Verified mismatch','clauses':[{'wording':'Australian citizenship required.','kind':'work_rights','status':'failed','reason':'Verified mismatch','profile_fields':['work_authorization.australian_citizen']}]}}]})
        p.accept_assessment(self.run,self.s,state)
        self.assertEqual(p.next_action(self.run,self.s)['action'],'report')
        self.assertEqual(self.s['queue'],[self.jobs[1]]);self.assertEqual(self.s['eligible'],5)
    def test_partial_failure_does_not_claim_source_exhaustion(self):
        self.ingest_empty(0)
        self.s['pending']={'action':'acquire','source':'indeed','title':'AI Engineer','location':'Sydney','lookback_hours':24,'max_results':1,'acquisition_id':'indeed-1','reservation_usd':'0'}
        cov=self.root/'coverage.json';cov.write_text(json.dumps({'raw_row_count':0,'status':'partial','searches':[{'error_type':'ReadRetryLimit'}],'acquisition':{k:self.s['pending'][k] for k in ('source','title','location','lookback_hours','max_results')}}))
        p.ingest(self.run,self.s,self.root/'jobs.json',cov,self.root/'rel.json')
        self.assertEqual(self.s['coverage'][-1]['stop_reason'],'coverage_incomplete')
        self.s['query_positions']={k:2 for k in p.SOURCES}
        self.assertEqual(p.next_action(self.run,self.s)['reason'],'coverage_limited')
    def test_explicit_code_migration_keeps_progress_and_rejects_wrong_expected_version(self):
        self.s['scoring_policy']['code_fingerprint']='old-repair-version';self.s['reserved_usd']='0.115'
        before=json.dumps(self.s,sort_keys=True)
        with self.assertRaises(ValueError):p.migrate_code(self.run,self.s,'wrong','Approved local repair')
        self.assertEqual(json.dumps(self.s,sort_keys=True),before)
        result=p.migrate_code(self.run,self.s,'old-repair-version','Approved local repair')
        self.assertEqual(result['reserved_usd'],'0.115');self.assertEqual(self.s['scoring_policy']['code_fingerprint'],p.scoring_code_fingerprint())

    def test_migration_rejects_changed_scores_without_mutating_state(self):
        origin=self.root/'admitted';origin.mkdir();identifier=p.validation.job_id(self.jobs[0])
        outcome={'status':'qualified','condition_review':{},'result':{'score':80}}
        (origin/f'{identifier}-scored.json').write_text(json.dumps(outcome));(origin/f'{identifier}-reviewed.json').write_text('{}')
        self.s['admissions']=[{'job_id':identifier,'run':str(origin),'outcome_fingerprint':p.validation.fingerprint(outcome)}]
        manifest={'threshold':self.s['scoring_policy']['threshold'],'hybrid_search':self.s['scoring_policy']['hybrid_search'],'vault':str(self.root),'resumes_dir':str(self.root),'pdftotext':None,'jobs':[{'job':self.jobs[0]}]}
        before=json.dumps(self.s,sort_keys=True)
        with patch('assessment.load_state',return_value=manifest),patch('assessment.require_unchanged_finalized'),patch('assessment.current_profile',return_value={}),patch('assessment_validation.validate_condition',return_value='passed'),patch('scoring.calculate',return_value={'score':79}):
            with self.assertRaisesRegex(ValueError,'score semantics changed'):p.migrate_code(self.run,self.s,self.s['scoring_policy']['code_fingerprint'],'Approved repair')
        self.assertEqual(json.dumps(self.s,sort_keys=True),before)
    def test_terminal_acquisition_recovery_never_reserves_a_new_submission(self):
        self.s['pending']={'action':'reconcile','source':'indeed','checkpoint_path':str(self.checkpoint)}
        result=self.defer('acquisition','unknown_submission');self.s['stop_reason']='budget_cap'
        p.resume_work(self.run,self.s,result['deferred_id']);before=self.s['reserved_usd']
        with patch('discovery.probe_cache',return_value={'reusable':False}):action=p.next_action(self.run,self.s)
        self.assertEqual(action['action'],'blocked');self.assertEqual(self.s['reserved_usd'],before)
        self.assertEqual(self.s['pending']['checkpoint_path'],str(self.checkpoint))
    def test_empty_stopped_report_preserves_cost_and_stop_metadata(self):
        self.s['stop_reason']='coverage_limited';self.s['reserved_usd']='0.115'
        report=p.report(self.run,self.s)
        self.assertEqual(report['summary']['reserved_usd'],'0.115')
        self.assertEqual(report['summary']['stop_reason'],'coverage_limited')
        self.assertIsNone(report['summary']['actual_billing_usd'])
