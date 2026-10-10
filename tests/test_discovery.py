import copy
import hashlib
import json
import sys
import subprocess
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".agents/skills/job-retrieval/scripts"))
import discovery as runner

CONFIG = {'lookback_hours':24,'max_results_per_search_per_source':100,'sources':{'indeed':{'enabled':True},'linkedin':{'enabled':True,'actor':'curious_coder/linkedin-jobs-scraper'},'seek':{'enabled':True,'actor':'websift/seek-job-scraper'}},'searches':[{'title':'AI Engineer','location':['Melbourne','Sydney']},{'title':'ai engineer','location':['melbourne']}]}

def state():
    return {'run_id':'test-stage1','started_epoch':datetime.now(UTC).timestamp(),'tasks':runner.plan(CONFIG,cap=3)[:3],'accepted':[],'events':[],'smoke_test':False}

def actor(run='actor1',status='SUCCEEDED',count=2):
    return {'structuredContent':{'runId':run,'status':status,'storages':{'datasets':{'default':{'id':'dataset1','itemCount':count}}}}}

class Stage1Tests(unittest.TestCase):
    def test_config_generates_unique_searches_and_bounded_smoke(self):
        self.assertEqual(len(runner.plan(CONFIG)),6)
        tasks=runner.plan(CONFIG,smoke=True,cap=3,platform='linkedin',title='AI Engineer',location='Melbourne')
        self.assertEqual(len(tasks),1)
        self.assertEqual(tasks[0]['cap'],3)
        self.assertIn('f_TPR=r86400',tasks[0]['args']['urls'][0])
        self.assertEqual(len(runner.plan(CONFIG,smoke=True)),1)
        with self.assertRaises(ValueError):
            runner.plan(CONFIG,platform='linkedin')
        with self.assertRaises(ValueError):
            runner.plan(CONFIG,smoke=True,location='Darwin')

    def test_cli_window_override_and_resume_are_immutable(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = [sys.executable, str(Path(runner.__file__)), '--run-id', 'window', '--state-root', tmp]
            first = subprocess.run(args + ['init', '--smoke', '--platform', 'linkedin', '--lookback-hours', '48'], capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            original = json.loads(first.stdout)
            self.assertEqual(original['lookback_hours'], 48)
            self.assertEqual(datetime.fromisoformat(original['window_end']) - datetime.fromisoformat(original['window_start']), timedelta(hours=48))
            checkpoint = Path(tmp)/'window'/'checkpoint.json'
            saved = checkpoint.read_bytes()
            conflict = subprocess.run(args + ['init', '--lookback-hours', '24'], capture_output=True, text=True)
            self.assertNotEqual(conflict.returncode, 0)
            self.assertEqual(checkpoint.read_bytes(), saved)
            resumed = subprocess.run(args + ['init'], capture_output=True, text=True)
            self.assertEqual(json.loads(resumed.stdout)['window_start'], original['window_start'])

    def test_selected_window_provider_coverage_and_dates(self):
        for configured, override, expected in ((None, None, 24), (72, None, 72), (24, 48, 48)):
            config = copy.deepcopy(CONFIG)
            if configured is None: config.pop('lookback_hours')
            else: config['lookback_hours'] = configured
            tasks = runner.plan(config, lookback_hours=override)
            self.assertIn(f'f_TPR=r{expected*3600}', tasks[1]['args']['urls'][0])
            self.assertEqual(tasks[2]['args']['dateRange'], (expected+23)//24)
        for bad in (0, -1, 1.5, '48', True, None):
            config = dict(CONFIG, lookback_hours=bad)
            with self.subTest(value=bad), self.assertRaises(ValueError): runner.plan(config)
        s = state()
        start = datetime.fromtimestamp(s['started_epoch'], UTC)
        s.update(lookback_hours=48, window_start=(start-timedelta(hours=48)).isoformat(), window_end=start.isoformat())
        self.assertTrue(runner.fresh((start-timedelta(hours=48)).isoformat(), 'seek', start, 48))
        self.assertFalse(runner.fresh((start-timedelta(hours=48, seconds=1)).isoformat(), 'seek', start, 48))
        s['tasks'] = [s['tasks'][2]]
        s['supervision_deadline'] = s['started_epoch'] + 30*60  # Explicitly extended supervision of a delayed saved window.
        s['started_epoch'] -= 3*3600
        start -= timedelta(hours=3)
        s.update(window_start=(start-timedelta(hours=48)).isoformat(), window_end=start.isoformat())
        self.assertEqual(runner.next_requests(s)[0]['args']['dateRange'], 3)

    def test_uncoverable_source_and_ambiguous_legacy_cannot_submit(self):
        s = state()
        s['tasks'] = [s['tasks'][2]]
        start = datetime.fromtimestamp(s['started_epoch'], UTC)
        s.update(lookback_hours=9000, window_start=(start-timedelta(hours=9000)).isoformat(), window_end=start.isoformat())
        self.assertEqual(runner.next_requests(s), [])
        self.assertEqual(s['tasks'][0]['phase'], 'failed')
        self.assertEqual(s['tasks'][0]['attempts'], 0)
        ambiguous = state()
        ambiguous['tasks'][1]['args']['urls'] = ['https://www.linkedin.com/jobs/search/']
        with self.assertRaisesRegex(ValueError, 'legacy'): runner.next_requests(ambiguous)

    def test_legacy_exact_endpoints_survive_and_partial_metadata_is_rejected(self):
        s = state()
        start = datetime.fromtimestamp(s['started_epoch'], UTC)
        s.update(window_start=(start-timedelta(hours=72)).isoformat(), window_end=start.isoformat())
        before = runner.progress(s, Path('/fixture'))
        runner.next_requests(s)
        self.assertEqual(runner.progress(s, Path('/fixture'))['window_start'], before['window_start'])
        self.assertEqual(s['lookback_hours'], 72)
        malformed = state()
        malformed['window_start'] = start.isoformat()
        with self.assertRaises(ValueError): runner.next_requests(malformed)
        malformed = state()
        malformed['tasks'][1]['args']['urls'][0] = malformed['tasks'][1]['args']['urls'][0].replace('r86400', 'r864000')
        with self.assertRaises(ValueError): runner.next_requests(malformed)

    def test_cli_selects_smoke_and_returns_read_only_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=[sys.executable,str(Path(runner.__file__)), '--run-id', 'fixture-smoke', '--state-root',tmp]
            init=subprocess.run(args+['init','--smoke','--platform','linkedin','--title','AI Engineer','--location','Melbourne'],capture_output=True,text=True)
            self.assertEqual(init.returncode,0,init.stderr)
            self.assertEqual(json.loads(init.stdout)['search_count'],1)
            status=subprocess.run(args+['status'],capture_output=True,text=True)
            self.assertEqual(status.returncode,0,status.stderr)
            self.assertEqual(json.loads(status.stdout)['remaining'],1)
            self.assertEqual(json.loads(status.stdout)['searches'][0]['attempts'],0)

    def test_cli_durably_saves_connector_response_and_actor_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=[sys.executable,str(Path(runner.__file__)), '--run-id', 'fixture-response', '--state-root',tmp,'--log-root',str(Path(tmp)/'logs')]
            def cli(command,extra=(),payload=None):
                result=subprocess.run(args+[command]+list(extra),input=json.dumps(payload) if payload else None,capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
                return json.loads(result.stdout)
            cli('init',['--smoke','--platform','linkedin'])
            request=cli('next')['requests'][0]
            response=actor(status='RUNNING',count=0)
            saved=cli('accept',['--request-id',request['id']],response)
            self.assertEqual(json.loads(Path(saved['response_path']).read_text()),response)
            self.assertEqual(cli('status')['searches'][0]['actor_run_id'],'actor1')
            self.assertEqual(cli('next')['requests'][0]['args']['runId'],'actor1')

    def test_finished_blocked_actor_can_reconcile_without_another_submission(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = [sys.executable, str(Path(runner.__file__)), '--run-id', 'reconcile',
                    '--state-root', str(root/'state'), '--log-root', str(root/'logs')]
            def cli(command, extra=(), payload=None):
                result = subprocess.run(args+[command]+list(extra), input=json.dumps(payload) if payload else None,
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                return json.loads(result.stdout)
            cli('init', ['--smoke', '--platform', 'linkedin'])
            request = cli('next')['requests'][0]
            cli('next')  # Interrupted search becomes blocked, never resubmitted.
            self.assertEqual(cli('finish')['status'], 'partial')
            directory = root/'state/reconcile'
            # Simulate a legacy checkpoint which had already finalized the unknown run.
            checkpoint = json.loads((directory/'checkpoint.json').read_text())
            checkpoint['finished'] = True
            (directory/'checkpoint.json').write_text(json.dumps(checkpoint))
            old_log = runner.log.stage_path(root/'logs', runner.log.local_run_date(checkpoint['started_epoch']), 'discovery')
            runner.log.append_record(old_log, {'run_id': 'reconcile', 'record_type': 'stage1_summary', 'status': 'partial'})
            (root/'logs/log.txt').write_text('Stage 1 reconcile: partial; unresolved submission.\n')
            cli('attach', ['--search-id', checkpoint['tasks'][0]['key'], '--actor-run-id', 'existing'])
            poll = cli('next')['requests'][0]
            self.assertEqual(poll['args']['runId'], 'existing')
            cli('accept', ['--request-id', poll['id']], actor(run='existing', count=1))
            page = cli('next')['requests'][0]
            raw = {'id': 'reconciled', 'link': 'https://example.test/reconciled', 'companyName': 'Fixture Co',
                   'title': 'AI Engineer', 'location': 'Melbourne',
                   'postedAt': datetime.fromtimestamp(checkpoint['started_epoch']-60, UTC).isoformat(),
                   'descriptionText': 'Build reliable Python services.'}
            cli('accept', ['--request-id', page['id']], {'structuredContent': {'datasetId': 'dataset1',
                'offset': 0, 'totalItemCount': 1, 'items': [raw]}})
            self.assertEqual(cli('finish')['status'], 'completed')
            cli('finish')
            self.assertEqual(json.loads((directory/'coverage.json').read_text())['status'], 'completed')
            self.assertEqual(len(json.loads((directory/'jobs.json').read_text())), 1)
            records = [json.loads(line) for line in next((root/'logs').rglob('discovery.jsonl')).read_text().splitlines()]
            outcomes = [row for row in records if row['record_type'] == 'discovery_job']
            self.assertEqual(len(outcomes), 1)
            self.assertEqual(outcomes[0]['outcome'], 'retain')
            self.assertEqual([row for row in records if row['record_type'] == 'stage1_summary'][-1]['status'], 'completed')
            self.assertIn('reconcile: completed', (root/'logs/log.txt').read_text())
            final = json.loads((directory/'checkpoint.json').read_text())
            self.assertEqual(final['tasks'][0]['attempts'], 1)

    def test_current_config_retains_all_configured_searches(self):
        config=runner.yaml.safe_load((Path(__file__).resolve().parents[1]/'config/search_targets.yaml').read_text())
        tasks=runner.plan(config)
        actual={(t['source'], t['title'].casefold(), t['location'].casefold()) for t in tasks}
        expected={(source, target['title'].strip().casefold(), city.strip().casefold())
                  for source, settings in config['sources'].items() if settings.get('enabled')
                  for target in config['searches']
                  for city in (target['location'] if isinstance(target['location'], list) else [target['location']])}
        self.assertEqual(actual,expected)
        self.assertEqual(len(tasks),len(expected))
        self.assertEqual({t['cap'] for t in tasks},{config['max_results_per_search_per_source']})

    def test_legacy_multi_platform_smoke_never_starts_a_submission(self):
        s=state();s['smoke_test']=True
        with self.assertRaises(ValueError):
            runner.next_requests(s)
        self.assertEqual([t['attempts'] for t in s['tasks']],[0,0,0])

    def test_legacy_logged_winner_survives_reconciled_cross_source_duplicates(self):
        s = state(); started = datetime.fromtimestamp(s['started_epoch'], UTC).isoformat()
        for task in s['tasks']: task.update(phase='done', jobs=[])
        seek = {'id': 'seek-one', 'jobLink': 'https://seek.com/job/2', 'advertiser.name': 'Fixture Co',
                'title': 'AI Engineer', 'joblocationInfo.displayLocation': 'Melbourne', 'listedAt': started,
                'content.unEditedContent': 'Original short description'}
        linkedin = {'id': 'linkedin-one', 'link': 'https://example.test/recovered', 'companyName': 'Fixture Co',
                    'title': 'AI Engineer', 'location': 'Melbourne', 'postedAt': started,
                    'descriptionText': 'Reconciled description with significantly more candidate requirements'}
        s['tasks'][1]['jobs'] = [linkedin]; s['tasks'][2]['jobs'] = [seek]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); logs = root/'logs'; directory = root/'state'
            path = runner.log.stage_path(logs, runner.log.local_run_date(s['started_epoch']), 'discovery')
            identity = runner.normalize('seek', seek)['job_url']
            runner.log.append_record(path, {'run_id': s['run_id'], 'record_type': 'discovery_job', 'platform': 'seek',
                'job_id': hashlib.sha256(identity.encode()).hexdigest()[:16], 'outcome': 'retain', 'reason': 'retained'})
            runner.log.append_record(path, {'run_id': s['run_id'], 'record_type': 'stage1_summary', 'status': 'partial'})
            (logs/'log.txt').write_text(f"Stage 1 {s['run_id']}: partial; blocked Actor.\n")
            summary = runner.finish(s, directory, logs, root/'vault')
            self.assertEqual(summary['status'], 'completed')
            self.assertEqual(json.loads((directory/'jobs.json').read_text())[0]['job_url'], identity)
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            outcomes = [row for row in rows if row['record_type'] == 'discovery_job']
            self.assertEqual(len(outcomes), 2)
            self.assertEqual(len({(row['platform'], row['job_id']) for row in outcomes}), 2)
            self.assertEqual([row for row in rows if row['record_type'] == 'stage1_summary'][-1]['status'], 'completed')
            self.assertIn(f"Stage 1 {s['run_id']}: completed", (logs/'log.txt').read_text())

    def test_resume_never_relaunches_actor_and_saves_pages_once(self):
        s=state(); s['tasks']=[s['tasks'][1]]
        search=runner.next_requests(s)[0]
        runner.accept(s,search['id'],actor(status='RUNNING',count=0))
        poll=runner.next_requests(s)[0]
        self.assertEqual(poll['args']['runId'],'actor1')
        runner.accept(s,poll['id'],actor())
        page=runner.next_requests(s)[0]
        response={'structuredContent':{'datasetId':'dataset1','offset':0,'totalItemCount':2,'items':[{'id':'one'},{'id':'two'}]}}
        runner.accept(s,page['id'],response)
        self.assertEqual(runner.accept(s,page['id'],response)['status'],'already_saved')
        self.assertEqual(len(s['tasks'][0]['jobs']),2)
        self.assertEqual(runner.next_requests(s),[])
        self.assertEqual(s['tasks'][0]['attempts'],1)

    def test_interrupted_submission_is_blocked_but_read_is_resumable(self):
        s=state(); s['tasks']=[s['tasks'][1]]
        runner.next_requests(s)
        self.assertEqual(runner.next_requests(s),[])
        self.assertEqual(s['tasks'][0]['phase'],'blocked')
        s['tasks'][0].update(phase='poll',actor_run_id='existing',inflight=None)
        first=runner.next_requests(s)[0]
        resumed=runner.next_requests(s)[0]
        self.assertEqual(resumed['args'],first['args'])
        self.assertNotEqual(resumed['id'],first['id'])
        self.assertEqual(s['tasks'][0]['attempts'],1)

    def test_repeated_polls_have_unique_telemetry_ids(self):
        s=state();s['tasks']=[s['tasks'][1]]
        request=runner.next_requests(s)[0]
        runner.accept(s,request['id'],actor(status='RUNNING',count=0))
        first=runner.next_requests(s)[0]
        runner.accept(s,first['id'],actor(status='RUNNING',count=0))
        second=runner.next_requests(s)[0]
        self.assertNotEqual(first['id'],second['id'])
        self.assertEqual(first['args'],second['args'])

    def test_empty_dataset_skips_reads_and_empty_run_id_never_polled(self):
        s=state();s['tasks']=[s['tasks'][1]]
        request=runner.next_requests(s)[0]
        runner.accept(s,request['id'],actor(count=0))
        self.assertEqual(runner.next_requests(s),[])
        s=state();s['tasks']=[s['tasks'][1]]
        request=runner.next_requests(s)[0]
        runner.accept(s,request['id'],actor(run=''))
        self.assertEqual(s['tasks'][0]['phase'],'blocked')
        self.assertEqual(runner.next_requests(s),[])

    def test_ambiguous_paid_rate_limit_does_not_resubmit(self):
        s = state(); s['tasks'] = [s['tasks'][1]]
        request = runner.next_requests(s)[0]
        runner.accept(s, request['id'], {'isError': True, 'content': [
            {'text': 'Actor submitted but response unavailable: rate limit'}]})
        s['tasks'][0]['next_after'] = 0
        self.assertEqual(runner.next_requests(s), [])
        self.assertEqual(s['tasks'][0]['phase'], 'blocked')
        self.assertEqual(s['tasks'][0]['attempts'], 1)

    def test_running_actor_pauses_and_explicit_resume_preserves_window(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); checkpoint_dir = root/'test-stage1'
            s = state(); s['tasks'] = [s['tasks'][1]]
            request = runner.next_requests(s)[0]
            runner.accept(s, request['id'], actor(status='RUNNING'))
            original = runner.window(s)
            s['supervision_deadline'] = 0
            self.assertEqual(runner.next_requests(s), [])
            self.assertTrue(runner.progress(s, checkpoint_dir)['terminal'])
            summary = runner.finish(s, checkpoint_dir, root/'logs', root/'vault')
            self.assertEqual(summary['status'], 'partial')
            self.assertTrue(summary['supervision_paused'])
            self.assertEqual(json.loads((checkpoint_dir/'coverage.json').read_text())['status'], 'partial')
            self.assertFalse(s['finished'])
            runner.save(checkpoint_dir/'checkpoint.json', s)
            command = [sys.executable, str(Path(runner.__file__)), 'resume', '--run-id', s['run_id'],
                       '--state-root', str(root), '--supervision-minutes', '5']
            response = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(response.returncode, 0, response.stderr)
            resumed = json.loads((checkpoint_dir/'checkpoint.json').read_text())
            self.assertFalse(resumed['supervision_paused'])
            self.assertEqual(runner.window(resumed), original)
            following = runner.next_requests(resumed)[0]
            self.assertEqual(following['args']['runId'], 'actor1')
            self.assertEqual(resumed['tasks'][0]['attempts'], 1)

    def test_rate_limit_backoff_does_not_retry_immediately(self):
        s=state();s['tasks']=[s['tasks'][0]]
        request=runner.next_requests(s)[0]
        runner.accept(s,request['id'],{'isError':True,'content':[{'text':'Rate limit exceeded. Try again in 23 seconds.'}]})
        self.assertEqual(runner.next_requests(s),[])
        self.assertGreater(s['tasks'][0]['next_after'],s['started_epoch']+50)

    def test_smoke_error_never_resubmits_paid_search(self):
        s=state();s['smoke_test']=True;s['tasks']=[s['tasks'][1]]
        request=runner.next_requests(s)[0]
        runner.accept(s,request['id'],{'isError':True,'content':[{'text':'Rate limit exceeded. Try again in 23 seconds.'}]})
        s['tasks'][0]['next_after']=0
        self.assertEqual(runner.next_requests(s),[])
        self.assertEqual(s['tasks'][0]['attempts'],1)
        self.assertEqual(s['tasks'][0]['phase'],'blocked')

    def test_provider_hard_limit_is_failed_without_paid_retry(self):
        s=state();s['tasks']=[s['tasks'][1]]
        request=runner.next_requests(s)[0]
        runner.accept(s,request['id'],{'isError':True,'content':[{'text':'Monthly usage hard limit exceeded (platform-feature-disabled)'}]})
        self.assertEqual(s['tasks'][0]['phase'],'failed')
        self.assertEqual(s['tasks'][0]['error_type'],'ProviderUsageLimit')
        self.assertEqual(runner.next_requests(s),[])
        self.assertEqual(s['tasks'][0]['attempts'],1)

    def test_exact_cutoff_and_unreliable_indeed_dates(self):
        started=datetime.now(UTC)
        self.assertFalse(runner.fresh((started-timedelta(hours=24,seconds=1)).isoformat(),'seek',started))
        self.assertTrue(runner.fresh((started-timedelta(hours=23)).isoformat(),'seek',started))
        self.assertFalse(runner.fresh((started+timedelta(seconds=1)).isoformat(),'seek',started))
        self.assertFalse(runner.fresh('2026-10-06','indeed',started))
        self.assertFalse(runner.fresh('24 hours ago','indeed',started))

    def test_resumed_sources_need_absolute_timestamps_in_original_window(self):
        started = datetime(2026, 10, 6, tzinfo=UTC)
        for source in ('indeed', 'linkedin', 'seek'):
            for unreliable in (None, '', '2026-10-06', '1 hour ago', '5 minutes ago', '2026-10-05T23:00:00'):
                with self.subTest(source=source, posted=unreliable):
                    self.assertFalse(runner.fresh(unreliable, source, started))
            self.assertFalse(runner.fresh('2026-10-06T01:00:00Z', source, started))
            self.assertTrue(runner.fresh('2026-10-05T00:00:00Z', source, started))
            self.assertTrue(runner.fresh('2026-10-06T00:00:00Z', source, started))

    def test_finished_legacy_checkpoint_gains_handoff_without_new_work(self):
        s=state()
        for task in s['tasks']: task['phase']='done'
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);directory=root/'state'
            runner.finish(s,directory,root/'logs',root/'vault')
            (directory/'coverage.json').unlink()
            runner.finish(s,directory,root/'logs',root/'vault')
            self.assertEqual(json.loads((directory/'coverage.json').read_text())['completed_searches'],3)
            self.assertEqual(s['events'],[])

    def test_empty_and_partial_handoff_preserve_cutoff_and_every_search(self):
        s=state()
        for task in s['tasks']: task['phase']='done'
        s['tasks'][1]['phase']='failed'
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            summary=runner.finish(s,root/'state',root/'logs',root/'vault')
            coverage=json.loads((root/'state'/'coverage.json').read_text())
            self.assertEqual(summary['status'],'partial')
            self.assertEqual(coverage['run_id'],'test-stage1')
            self.assertEqual(coverage['window_end'],datetime.fromtimestamp(s['started_epoch'],UTC).isoformat())
            self.assertEqual(coverage['window_start'],(datetime.fromtimestamp(s['started_epoch'],UTC)-timedelta(hours=24)).isoformat())
            self.assertEqual(len(coverage['searches']),3)
            self.assertEqual(json.loads(Path(coverage['jobs_path']).read_text()),[])
            self.assertEqual(coverage['completed_searches'],2)

    def test_finish_deduplicates_prefers_fullest_excludes_existing_and_logs_once(self):
        s=state(); now=datetime.fromtimestamp(s['started_epoch'],UTC).isoformat()
        raw={'id':'one','link':'https://example.com/job/1?utm_source=linkedin','companyName':'Acme','title':'AI Engineer','location':'Melbourne','postedAt':now,'descriptionText':'Full JD with evidence requirements'}
        s['tasks'][0].update(phase='done',jobs=[])
        s['tasks'][1].update(phase='done',jobs=[raw,dict(raw,descriptionText='Short')])
        seek={'id':'two','jobLink':'https://seek.com/job/2','advertiser.name':'Acme','title':'AI Engineer','joblocationInfo.displayLocation':'Melbourne VIC','listedAt':now,'content.unEditedContent':'short JD'}
        s['tasks'][2].update(phase='done',jobs=[seek])
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);directory=root/'state'; logs=root/'logs'; vault=root/'vault'
            first=runner.finish(s,directory,logs,vault)
            second=runner.finish(s,directory,logs,vault)
            self.assertEqual(first['retained_job_count'],1)
            self.assertEqual(second['retained_job_count'],1)
            self.assertEqual(first['elapsed_seconds'],second['elapsed_seconds'])
            jobs=json.loads((directory/'jobs.json').read_text())
            self.assertEqual(jobs[0]['description_text'],raw['descriptionText'])
            self.assertEqual(jobs[0]['job_url'],'https://example.com/job/1')
            records=[json.loads(x) for x in next(logs.rglob('discovery.jsonl')).read_text().splitlines()]
            self.assertEqual(len([x for x in records if x['record_type']=='discovery_job']),2)
            self.assertNotIn(raw['descriptionText'],json.dumps(records))
            active=vault/'07 Applications'/'01 Active';active.mkdir(parents=True)
            (active/'saved.md').write_text('Acme AI Engineer https://example.com/job/1')
            self.assertEqual(runner.finish(s,root/'other',root/'other_logs',vault)['retained_job_count'],0)

if __name__=='__main__': unittest.main()
