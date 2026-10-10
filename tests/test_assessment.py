import json
import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".agents/skills/job-scoring/scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".agents/skills/job-suggestions/scripts"))
from assessment_fixture import fixture
import assessment as support
import assessment_validation
import approved_preparation as preparation


class SavedHandoff(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.vault, self.resumes = fixture(self.root)
        self.source, self.state = self.root/'jobs.json', self.root/'assessment'
        self.job = {'job_url': 'https://example.test/one', 'company': 'Co', 'position': 'Engineer',
                    'description_text': 'Build Python services.'}
        self.handoff = {'jobs': [self.job], 'run_id': 'fixture', 'cutoff': '2026-10-05T00:00:00Z',
                        'coverage': {'status': 'partial', 'failed': 1}}
        self.source.write_text(json.dumps(self.handoff))

    def prepare(self):
        return support.prepare_assessment(self.source, self.state, self.vault, self.resumes, hybrid_search=False)

    def test_scoring_only_preserves_partial_coverage_and_all_original_failures(self):
        with patch.dict(os.environ, {}, clear=True):
            # Supplying pdftotext executable is local readiness, never source access.
            with patch.dict(os.environ, {'PDFTOTEXT_BIN': os.environ.get('PDFTOTEXT_BIN', self.pdf_binary)}):
                manifest = self.prepare()
                second = self.prepare()
                self.assertEqual(manifest['started_epoch_seconds'], second['started_epoch_seconds'])
                summary = support.finalize_assessment(self.state)
        self.assertEqual(summary['status'], 'failed')
        result = json.loads((self.state/'results.json').read_text())
        self.assertEqual(result['coverage'], self.handoff['coverage'])
        self.assertEqual(len(result['jobs']), 1)
        self.assertEqual(result['jobs'][0]['status'], 'failed')
        report = json.loads((self.state/'report.json').read_text())
        self.assertFalse(report['selectable'])
        self.assertEqual(report['unresolved'][0]['status'], 'failed')
        self.assertTrue(report['unresolved'][0]['error'])
        self.assertIsNone(summary['cost_estimate_usd'])
        self.assertEqual((self.state/'manifest.json').stat().st_mode & 0o777, 0o600)

    def review_job(self, manifest, identifier):
        review = {'reviewer': 'codex', 'status': 'passed', 'reason': 'No gate applies', 'clauses': [],
                  'jd_fingerprint': next(row['jd_fingerprint'] for row in manifest['prepared']['jobs'] if row['job_id'] == identifier),
                  'profile_fingerprint': manifest['prepared']['profile_fingerprint']}
        support.save_condition(self.state, identifier, review)
        support.freeze_job(self.state, identifier, {'units': [
            {'id': 1, 'category': 'Experience', 'priority': 2, 'reason': 'Role scope'},
            {'id': 2, 'category': 'Skills', 'priority': 3, 'reason': 'Required Python'}]})
        support.build_packet(self.state, identifier)
        template_path = self.state/f'{identifier}-review-template.json'
        template = json.loads(template_path.read_text())
        for index, requirement in enumerate(template['requirements']):
            requirement.update(candidate_strength='transferable' if index == 0 else 'direct',
                candidate_reason='Verified services delivery', evidence=[{'path': '05 Evidence/Python.md', 'heading': 'Claim'}],
                resume_strengths={'ai.pdf': 'transferable' if index == 0 else 'direct', 'cv.pdf': 'missing'},
                resume_lines={'ai.pdf': [1], 'cv.pdf': []})
        (self.state/f'{identifier}-reviewed.json').write_text(json.dumps(template))
        return review

    def test_saved_job_can_be_reviewed_without_source_credentials_and_resumed(self):
        manifest = self.prepare()
        identifier = manifest['jobs'][0]['job_id']
        review = self.review_job(manifest, identifier)
        summary = support.finalize_assessment(self.state, self.root/'logs')
        self.assertEqual(summary['status'], 'partial')
        self.assertEqual(summary['scored_job_count'], 1)
        support.finalize_assessment(self.state, self.root/'logs')
        records = [json.loads(line) for line in next((self.root/'logs').glob('*/scoring.jsonl')).read_text().splitlines()]
        self.assertEqual(len(records), 2)
        self.assertNotIn('Built Python', json.dumps(records))
        # A job with a known explicit gate failure needs no frozen requirements or retrieval.
        self.job['description_text'] = 'Australian citizenship required.'
        self.source.write_text(json.dumps(self.handoff))
        self.state = self.root/'revised-assessment'
        manifest = self.prepare()
        review.update(status='failed', reason='Explicit citizenship mismatch',
                      jd_fingerprint=manifest['prepared']['jobs'][0]['jd_fingerprint'],
                      clauses=[{'wording': 'Australian citizenship required.', 'kind': 'work_rights',
                                'status': 'failed', 'reason': 'Verified mismatch',
                                'profile_fields': ['work_authorization.australian_citizen']}])
        support.save_condition(self.state, identifier, review)
        with self.assertRaisesRegex(ValueError, 'failed condition'):
            support.build_packet(self.state, identifier)
        summary = support.finalize_assessment(self.state)
        self.assertEqual(summary['condition_failed_count'], 1)
        self.assertEqual(summary['scored_job_count'], 0)

    def test_malformed_job_does_not_discard_a_valid_original_job(self):
        second = dict(self.job, job_url='https://example.test/two')
        self.handoff['jobs'].append(second)
        self.source.write_text(json.dumps(self.handoff))
        manifest = self.prepare()
        for row in manifest['jobs']:
            self.review_job(manifest, row['job_id'])
        first = manifest['jobs'][0]['job_id']
        (self.state/f'{first}-reviewed.json').write_text('[]')
        summary = support.finalize_assessment(self.state)
        self.assertEqual(summary['failed_job_count'], 1)
        self.assertEqual(summary['scored_job_count'], 1)
        self.assertEqual([row['status'] for row in json.loads((self.state/'results.json').read_text())['jobs']], ['failed', 'qualified'])

    def test_finalized_assessments_cannot_change_under_existing_logs(self):
        manifest = self.prepare()
        identifier = manifest['jobs'][0]['job_id']
        self.review_job(manifest, identifier)
        support.finalize_assessment(self.state, self.root/'logs')
        old_result = (self.state/'results.json').read_text()
        log_path = next((self.root/'logs').glob('*/scoring.jsonl'))
        old_log = log_path.read_text()
        reviewed_path = self.state/f'{identifier}-reviewed.json'
        reviewed = json.loads(reviewed_path.read_text())
        reviewed['requirements'][1].update(candidate_strength='missing', evidence=[], candidate_reason='Corrected assessment')
        reviewed_path.write_text(json.dumps(reviewed))
        with self.assertRaisesRegex(ValueError, 'finalized'):
            support.finalize_assessment(self.state, self.root/'logs')
        self.assertEqual((self.state/'results.json').read_text(), old_result)
        self.assertEqual(log_path.read_text(), old_log)
        self.job['description_text'] += ' Changed scope.'
        self.source.write_text(json.dumps(self.handoff))
        with self.assertRaisesRegex(ValueError, 'finalized'):
            self.prepare()

    def test_finalizer_rejects_review_that_jointly_redefines_the_frozen_set(self):
        manifest = self.prepare()
        identifier = manifest['jobs'][0]['job_id']
        self.review_job(manifest, identifier)
        path = self.state/f'{identifier}-reviewed.json'
        reviewed = json.loads(path.read_text())
        reviewed['classified']['units'][0]['category'] = 'ignore'
        reviewed['requirements'] = reviewed['requirements'][1:]
        reviewed['retrieval']['results'] = reviewed['retrieval']['results'][1:]
        path.write_text(json.dumps(reviewed))
        summary = support.finalize_assessment(self.state)
        self.assertEqual(summary['failed_job_count'], 1)
        self.assertEqual(summary['scored_job_count'], 0)
        result = json.loads((self.state/'results.json').read_text())['jobs'][0]
        self.assertEqual(result['status'], 'failed')
        self.assertNotIn('result', result)

    def test_missing_linked_sources_wait_and_resume_cached_retrieval(self):
        note = self.vault/'05 Evidence/Python.md'
        note.write_text(note.read_text().replace('user-confirmed: fixture', 'https://example.test/project'))
        prepared = support.prepare_run(self.source, self.state, self.vault, self.resumes, hybrid_search=False)
        submission = prepared['requirements_template']
        row = submission['jobs'][0]
        row['condition'].update(status='passed', reason='No gate applies', clauses=[])
        row['classified'] = {'units': [
            {'id': 1, 'category': 'Experience', 'priority': 2, 'reason': 'Role scope'},
            {'id': 2, 'category': 'Skills', 'priority': 3, 'reason': 'Required Python'}]}
        response = support.submit_requirements(self.state, submission)
        self.assertEqual(response['failures'], [])
        self.assertEqual(response['awaiting_sources'][0]['source_urls'], ['https://example.test/project'])
        self.assertFalse((self.state/'report.json').exists())
        condition_path = support.condition_file(self.state, row['job_handle'])
        requirements_path = self.state/f"{row['job_handle']}-requirements.json"
        accepted_condition = condition_path.read_bytes()
        accepted_requirements = requirements_path.read_bytes()
        row['condition']['reason'] = 'No eligibility restrictions are stated'
        for unit in row['classified']['units']:
            unit['reason'] = 'Same classification with a reworded explanation'
        with patch.object(support.vault, 'run_batch_search', side_effect=AssertionError('retrieval repeated')):
            resumed = support.submit_requirements(self.state, submission,
                linked_sources={'https://example.test/project': 'Built Python services.'})
        self.assertEqual(resumed['failures'], [])
        self.assertEqual(resumed['awaiting_sources'], [])
        self.assertEqual(len(resumed['judgments_template']['jobs']), 1)
        self.assertEqual(condition_path.read_bytes(), accepted_condition)
        self.assertEqual(requirements_path.read_bytes(), accepted_requirements)
        row['condition']['status'] = 'manual_review'
        rejected = support.submit_requirements(self.state, submission)
        self.assertIn('accepted condition cannot change', rejected['failures'][0]['error'])
        row['condition']['status'] = 'passed'
        row['classified']['units'][1]['priority'] = 1
        rejected = support.submit_requirements(self.state, submission)
        self.assertIn('frozen requirements cannot change', rejected['failures'][0]['error'])
        self.assertEqual(condition_path.read_bytes(), accepted_condition)
        self.assertEqual(requirements_path.read_bytes(), accepted_requirements)

    def test_three_interactions_generate_templates_and_save_scores(self):
        prepared = support.prepare_run(self.source, self.state, self.vault, self.resumes, hybrid_search=False)
        submission = prepared['requirements_template']
        row = submission['jobs'][0]
        self.assertNotIn('input_fingerprint', json.dumps(submission))
        row['condition'].update(status='passed', reason='No gate applies', clauses=[])
        row['classified'] = {'units': [
            {'id': 1, 'category': 'Experience', 'priority': 2, 'reason': 'Role scope'},
            {'id': 2, 'category': 'Skills', 'priority': 3, 'reason': 'Required Python'}]}
        response = support.submit_requirements(Path(prepared['run_handle']), submission)
        judgments = response['judgments_template']
        reviewed = judgments['jobs'][0]
        reviewed['category'] = 'AI Agent'
        for index, requirement in enumerate(reviewed['requirements']):
            requirement.update(candidate_strength='transferable' if index == 0 else 'direct',
                candidate_reason='Verified services delivery', evidence=[{'path': '05 Evidence/Python.md', 'heading': 'Claim'}],
                resume_strengths={'ai.pdf': 'transferable' if index == 0 else 'direct', 'cv.pdf': 'missing'},
                resume_lines={'ai.pdf': [1], 'cv.pdf': []})
        result = support.submit_judgments(self.state, judgments, self.root/'logs')
        self.assertEqual(result['summary']['scored_job_count'], 1)
        self.assertEqual(result['summary']['status'], 'partial')
        self.assertEqual(result['jobs'][0]['status'], 'qualified')

    def test_failed_gate_requires_no_classification_and_completes(self):
        self.job['description_text'] = 'Australian citizenship required.'
        self.source.write_text(json.dumps(self.handoff))
        prepared = support.prepare_run(self.source, self.state, self.vault, self.resumes, hybrid_search=False)
        submission = prepared['requirements_template']
        row = submission['jobs'][0]
        row.pop('classified')
        row['condition'].update(status='failed', reason='Verified mismatch', clauses=[{
            'wording': 'Australian citizenship required.', 'kind': 'work_rights', 'status': 'failed',
            'reason': 'Verified mismatch', 'profile_fields': ['work_authorization.australian_citizen']}])
        result = support.submit_requirements(self.state, submission)
        self.assertEqual(result['summary']['condition_failed_count'], 1)
        self.assertEqual(result['outcomes'][0]['status'], 'condition_failed')
        self.assertEqual(result['progress']['unresolved_job_count'], 0)
        self.assertEqual(result['packets'], [])
        self.assertEqual(result['summary']['scored_job_count'], 0)

    def test_public_batch_repairs_invalid_job_without_replacing_completed_job(self):
        self.handoff['jobs'].append(dict(self.job, job_url='https://example.test/two'))
        self.source.write_text(json.dumps(self.handoff))
        prepared = support.prepare_run(self.source, self.state, self.vault, self.resumes, hybrid_search=False)
        submission = prepared['requirements_template']
        for row in submission['jobs']:
            row['condition'].update(status='passed', reason='No gate applies')
            row['classified'] = {'units': [
                {'id': 1, 'category': 'Experience', 'priority': 2, 'reason': 'Role scope'},
                {'id': 2, 'category': 'Skills', 'priority': 3, 'reason': 'Python required'}]}
        judgments = support.submit_requirements(self.state, submission)['judgments_template']
        for row in judgments['jobs']:
            row['category'] = 'AI Agent'
            for requirement in row['requirements']:
                requirement.update(candidate_strength='missing', candidate_reason='Confirmed fixture gap')
        valid = dict(judgments['jobs'][0])
        judgments['jobs'][0] = dict(valid, requirements=[])
        result = support.submit_judgments(self.state, judgments, self.root/'logs')
        self.assertEqual(result['summary']['failed_job_count'], 1)
        self.assertEqual(result['summary']['scored_job_count'], 1)
        result = support.submit_judgments(self.state, {'jobs': [valid]}, self.root/'logs')
        self.assertEqual(result['summary']['failed_job_count'], 0)
        self.assertEqual(result['summary']['scored_job_count'], 2)
        invalid = dict(valid, category='Hybrid')
        with self.assertRaisesRegex(ValueError, 'finalized'):
            support.submit_judgments(self.state, {'jobs': [invalid]}, self.root/'logs')

    def test_explicit_cli_ledger_records_each_score_once_without_native_ledger(self):
        import scoring_ledger
        manifest = self.prepare()
        self.review_job(manifest, manifest['jobs'][0]['job_id'])
        support.submit_judgments(self.state, {'jobs': []}, self.root/'logs')
        self.assertFalse((self.root/'ledger').exists())
        scoring_ledger.run_begin(self.root/'ledger', 'cli-fixture')
        with patch.dict(os.environ, {'PIPELINE_RUN_ID': 'cli-fixture'}), patch.object(scoring_ledger, 'default_state_dir', return_value=self.root/'ledger'):
            support.submit_judgments(self.state, {'jobs': []}, self.root/'logs')
            support.submit_judgments(self.state, {'jobs': []}, self.root/'logs')
        rows = scoring_ledger.read_json_lines(scoring_ledger.run_state_path(self.root/'ledger', 'cli-fixture'))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'qualified')
        self.assertEqual(rows[0]['candidate_evidence_fit'], 78)
        self.assertNotIn('https://', json.dumps(rows))

    def test_fixture_assessment_keeps_primary_state_and_logs_untouched(self):
        def snapshot():
            return {str(path): path.read_bytes() for directory in [support.ROOT/'.state', support.ROOT/'logs']
                    if directory.exists() for path in directory.rglob('*') if path.is_file()}
        before = snapshot()
        self.job['description_text'] = 'Australian citizenship required.'
        self.source.write_text(json.dumps(self.handoff))
        prepared = support.prepare_run(self.source, self.state, self.vault, self.resumes, hybrid_search=False)
        row = prepared['requirements_template']['jobs'][0]
        row['condition'].update(status='failed', reason='Verified mismatch', clauses=[{
            'wording': 'Australian citizenship required.', 'kind': 'work_rights', 'status': 'failed',
            'reason': 'Verified mismatch', 'profile_fields': ['work_authorization.australian_citizen']}])
        support.submit_requirements(self.state, {'jobs': [row]})
        self.assertEqual(snapshot(), before)
        self.assertTrue((self.root/'.state/readiness.json').exists())
        self.assertTrue(list((self.root/'logs').glob('*/scoring.jsonl')))

    def test_malformed_batch_rows_do_not_drop_valid_later_original(self):
        self.handoff['jobs'].append(dict(self.job, job_url='https://example.test/two'))
        self.source.write_text(json.dumps(self.handoff))
        manifest = self.prepare()
        second = manifest['jobs'][1]['job_id']
        self.review_job(manifest, second)
        reviewed = json.loads((self.state/f'{second}-reviewed.json').read_text())
        supplied = {'job_handle': second, **{key: reviewed[key] for key in ['category', 'requirements']}}
        for bad in [None, {'job_handle': []}, {'job_handle': 'unknown'}]:
            result = support.submit_judgments(self.state, {'jobs': [bad, supplied]}, self.root/'logs')
            self.assertEqual(result['summary']['status'], 'failed')
            self.assertEqual(result['summary']['scored_job_count'], 1)
            self.assertEqual(result['jobs'][0]['status'], 'pending')
            self.assertTrue(result['failures'])

    def test_requirement_response_reports_all_original_progress_and_coverage(self):
        self.handoff['jobs'].append(dict(self.job, job_url='https://example.test/two'))
        self.source.write_text(json.dumps(self.handoff))
        prepared = support.prepare_run(self.source, self.state, self.vault, self.resumes, hybrid_search=False)
        row = prepared['requirements_template']['jobs'][1]
        row['condition'].update(status='passed', reason='No gates')
        row['classified'] = {'units': [
            {'id': 1, 'category': 'Experience', 'priority': 2, 'reason': 'Role scope'},
            {'id': 2, 'category': 'Skills', 'priority': 3, 'reason': 'Python'}]}
        result = support.submit_requirements(self.state, {'jobs': [None, row]})
        self.assertEqual(len(result['packets']), 1)
        self.assertEqual(result['coverage'], self.handoff['coverage'])
        self.assertEqual(result['progress'], {'original_job_count': 2, 'unresolved_job_count': 2})
        self.assertEqual(len(result['outcomes']), 2)
        self.assertTrue(result['failures'])

    @property
    def pdf_binary(self):
        return self._pdf_binary

    def test_empty_complete_handoff_finishes_without_source_calls(self):
        self.handoff.update(jobs=[], coverage={'status': 'completed', 'failed': 0})
        self.source.write_text(json.dumps(self.handoff))
        self.prepare()
        self.assertEqual(support.finalize_assessment(self.state)['status'], 'completed')

    def test_existing_jobs_file_loads_adjacent_discovery_coverage(self):
        self.source.write_text(json.dumps([]))
        (self.source.parent/'coverage.json').write_text(json.dumps({'status': 'completed', 'run_id': 'retrieved',
            'checkpoint_path': '/private/checkpoint.json', 'window_start': 'cutoff', 'window_end': 'run start'}))
        manifest = self.prepare()
        self.assertEqual(manifest['handoff']['run_id'], 'retrieved')
        self.assertEqual(manifest['handoff']['window_start'], 'cutoff')
        self.assertEqual(support.finalize_assessment(self.state)['status'], 'completed')

    def test_changed_resume_invalidates_saved_assessment(self):
        self.prepare()
        (self.resumes/'ai.pdf').write_bytes((self.resumes/'ai.pdf').read_bytes()+b'\n% changed\n')
        with self.assertRaisesRegex(ValueError, 'changed'):
            support.finalize_assessment(self.state)

    def test_empty_handoffs_preserve_coverage_without_scoring_dependencies(self):
        for coverage, expected in [({'status': 'completed'}, 'completed'), ({'status': 'partial'}, 'partial'), ({'status': 'unknown'}, 'partial')]:
            with self.subTest(coverage=coverage):
                self.source.write_text(json.dumps({'jobs': [], 'coverage': coverage}))
                state = self.root/expected/coverage['status']
                with patch('readiness.check', side_effect=AssertionError('irrelevant scoring readiness')):
                    result = support.prepare_run(self.source, state, self.root/'missing-vault', self.root/'missing-resumes')
                self.assertEqual(result['summary']['status'], expected)
                self.assertEqual(result['summary']['scored_job_count'], 0)
                self.assertEqual(result['coverage'], coverage)

    def test_cli_output_is_compact_and_inspection_accounts_for_each_job(self):
        self.handoff['jobs'].append(dict(self.job, job_url='https://example.test/two'))
        self.source.write_text(json.dumps(self.handoff))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = support.main(['prepare', '--input', str(self.source), '--output', str(self.state),
                '--vault', str(self.vault), '--resumes-dir', str(self.resumes), '--hybrid-search', 'false'])
        self.assertEqual(code, 0)
        compact = json.loads(output.getvalue())
        self.assertNotIn('description_text', output.getvalue())
        self.assertEqual(compact['original_job_count'], 2)
        self.assertEqual(Path(compact['response_path']).stat().st_mode & 0o777, 0o600)
        first = support.inspect_jobs(self.state)
        second = support.inspect_jobs(self.state, first['next_offset'])
        self.assertEqual(len(first['jobs']), 1)
        self.assertEqual(first['jobs'][0]['job']['description_text'], self.job['description_text'])
        self.assertNotEqual(first['jobs'][0]['job_handle'], second['jobs'][0]['job_handle'])
        self.assertIsNone(second['next_offset'])
        with self.assertRaises(ValueError): support.inspect_jobs(self.state, limit=4)
        with self.assertRaisesRegex(ValueError, 'at most three'):
            support.submit_requirements(self.state, {'jobs': [first['jobs'][0]['requirements_template']]*4})

    def test_small_batches_leave_other_jobs_pending_and_finish_all_jobs(self):
        self.handoff['jobs'].append(dict(self.job, job_url='https://example.test/two'))
        self.handoff['coverage'] = {'status': 'completed'}
        self.source.write_text(json.dumps(self.handoff))
        support.prepare_run(self.source, self.state, self.vault, self.resumes, hybrid_search=False)
        for offset in (0, 1):
            page = support.inspect_jobs(self.state, offset)
            decision = page['jobs'][0]['requirements_template']
            decision['condition'].update(status='passed', reason='No gate')
            for unit in decision['classified']['units']:
                unit.update(category='Skills', reason='Reviewed capability')
            support.submit_requirements(self.state, {'jobs': [decision]})
            page = support.inspect_jobs(self.state, offset)
            judgment = page['jobs'][0]['judgments_template']
            judgment['category'] = 'AI Agent'
            for requirement in judgment['requirements']:
                requirement.update(candidate_strength='missing', candidate_reason='Confirmed fixture gap')
            result = support.submit_judgments(self.state, {'jobs': [judgment]}, self.root/'logs')
            self.assertEqual(result['summary']['status'], 'in_progress' if offset == 0 else 'completed')
            self.assertEqual(result['summary']['pending_job_count'], 1-offset)
            self.assertEqual(result['summary']['failed_job_count'], 0)
        self.assertEqual(result['summary']['scored_job_count'], 2)
        self.assertEqual(len(json.loads((self.state/'results.json').read_text())['jobs']), 2)

    def test_inspect_reuses_accepted_decisions_and_invalid_citations_keep_draft(self):
        support.prepare_run(self.source, self.state, self.vault, self.resumes, hybrid_search=False)
        decision = support.inspect_jobs(self.state)['jobs'][0]['requirements_template']
        decision['condition'].update(status='passed', reason='No gate')
        for unit in decision['classified']['units']:
            unit.update(category='Skills', reason='Reviewed capability')
        support.submit_requirements(self.state, {'jobs': [decision]})
        page = support.inspect_jobs(self.state)['jobs'][0]
        self.assertEqual(page['requirements_template'], decision)
        judgment = page['judgments_template']
        self.assertTrue(judgment['allowed_evidence'])
        judgment['category'] = 'AI Agent'
        for requirement in judgment['requirements']:
            requirement.update(candidate_strength='direct', candidate_reason='Invalid draft',
                               evidence=[{'evidence_id': 'not_retrieved'}])
        result = support.submit_judgments(self.state, {'jobs': [judgment]}, self.root/'logs')
        identifier = page['job_handle']
        self.assertTrue((self.state/f'{identifier}-draft.json').exists())
        self.assertFalse((self.state/f'{identifier}-reviewed.json').exists())
        self.assertTrue(result['failures'][0]['recoverable'])
        self.assertEqual(result['failures'][0]['error_code'], 'invalid_submission')
        for requirement in judgment['requirements']:
            requirement.update(candidate_strength='missing', candidate_reason='No verified support', evidence=[])
        repaired = support.submit_judgments(self.state, {'jobs': [judgment]}, self.root/'logs')
        self.assertEqual(repaired['summary']['failed_job_count'], 0)

    def test_failed_hybrid_query_is_blocked_until_explicit_paid_retry(self):
        with patch('readiness.build_chroma_index'), patch('readiness.run_check_index'):
            manifest = self.prepare()
            identifier = manifest['jobs'][0]['job_id']
            support.save_condition(self.state, identifier, {'reviewer': 'codex', 'status': 'passed', 'reason': 'No gate',
                'clauses': [], 'jd_fingerprint': manifest['prepared']['jobs'][0]['jd_fingerprint'],
                'profile_fingerprint': manifest['prepared']['profile_fingerprint']})
            support.freeze_job(self.state, identifier, {'units': [
                {'id': 1, 'category': 'Experience', 'priority': 2, 'reason': 'Role'},
                {'id': 2, 'category': 'Skills', 'priority': 3, 'reason': 'Python'}]})
            manifest['hybrid_search'] = True
            (self.state/'manifest.json').write_text(json.dumps(manifest))
            with patch.object(support.vault, 'run_batch_search', side_effect=support.vault.SemanticSearchUnavailable('unknown usage')) as query:
                with self.assertRaisesRegex(ValueError, 'unknown usage'): support.build_packet(self.state, identifier)
                with self.assertRaisesRegex(ValueError, 'approval'): support.build_packet(self.state, identifier)
                self.assertEqual(query.call_count, 1)
            def successful(*args):
                requests = json.loads(args[1].read_text())['requests']
                print(json.dumps({'results': [{'requirement': row['requirement'], 'matches': []} for row in requests]}))
            with patch.object(support.vault, 'run_batch_search', side_effect=successful) as query:
                support.build_packet(self.state, identifier, authorize_paid_retry=True)
                support.build_packet(self.state, identifier)
                self.assertEqual(query.call_count, 1)
            self.assertFalse((self.state/f'{identifier}-retrieval-pending.json').exists())

SavedHandoff._pdf_binary = os.environ.get('PDFTOTEXT_BIN')

class WorkflowReport(unittest.TestCase):
    setUp = SavedHandoff.setUp
    prepare = SavedHandoff.prepare
    review_job = SavedHandoff.review_job

    def qualify(self, count=1):
        self.handoff['jobs'] = [{**self.job, 'job_url': f'https://example.test/{i}',
            'company': f'Company {i}', 'location': 'Melbourne', 'source': 'Seek',
            'posted_at': '2026-10-06', 'salary': '$100,000', 'contact_email': 'jobs@example.test'} for i in range(count)]
        self.source.write_text(json.dumps(self.handoff))
        prepared = support.prepare_run(self.source, self.state, self.vault, self.resumes, hybrid_search=False)
        for row in prepared['requirements_template']['jobs']:
            row['condition'].update(status='passed', reason='No gate', clauses=[])
            row['classified']['units'] = [
                {'id': 1, 'category': 'ignore', 'priority': 1, 'reason': 'Role title'},
                {'id': 2, 'category': 'Skills', 'priority': 3, 'reason': 'Python services required'}]
            response = support.submit_requirements(self.state, {'jobs': [row]})
            judgment = response['judgments_template']['jobs'][0]
            judgment['category'] = 'AI Agent'
            for requirement in judgment['requirements']:
                requirement.update(candidate_strength='direct', candidate_reason='Verified Python delivery',
                    evidence=[{'path': '05 Evidence/Python.md', 'heading': 'Claim'}],
                    resume_strengths={'ai.pdf': 'direct', 'cv.pdf': 'missing'},
                    resume_lines={'ai.pdf': [1], 'cv.pdf': []})
            response = support.submit_judgments(self.state, {'jobs': [judgment]})
        return json.loads((self.state/'report.json').read_text())

    def test_scoring_finishes_before_any_suggestions(self):
        report = self.qualify()
        self.assertTrue(report['selectable'])
        self.assertEqual(report['summary']['qualified_job_count'], 1)
        self.assertNotIn('suggestions', report['candidates'][0])
        page = support.inspect_jobs(self.state)['jobs'][0]
        self.assertNotIn('suggestions_template', page)
        self.assertFalse(list((self.root/'logs').rglob('suggestion.jsonl')))
        rendered = (self.state/'report.md').read_text()
        for expected in ('Melbourne', 'Seek', '2026-10-06', '$100,000', 'jobs@example.test', 'Brief match', 'Complete match'):
            self.assertIn(expected, rendered)
        self.assertNotIn('Resume plan', rendered)
        with self.assertRaisesRegex(ValueError, 'approved preparation'):
            support.submit_judgments(self.state, {'jobs': [{'job_handle': report['candidates'][0]['job_id'], 'suggestions': {}}]})

    def test_shared_inputs_and_frozen_report(self):
        report = self.qualify(2)
        page = support.inspect_jobs(self.state)
        self.assertNotIn('profile', page)
        self.assertIn('profile', support.inspect_jobs(self.state, shared=True))
        self.assertEqual([r['job_id'] for r in report['candidates']], sorted(r['job_id'] for r in report['candidates']))
        before = (self.state/'report.json').read_bytes()
        support.submit_judgments(self.state, {'jobs': []})
        self.assertEqual(before, (self.state/'report.json').read_bytes())

    def test_only_selected_jobs_can_receive_suggestions(self):
        report = self.qualify(2)
        before = {p.name: p.read_bytes() for p in self.resumes.iterdir()}
        selection = preparation.approve_selection(self.state, report['report_id'], [2], obsidian=True)
        handle = Path(selection['preparation_handle'])
        self.assertEqual(selection['destinations']['notion'], 'skipped_disabled')
        page = preparation.inspect_preparation(handle)
        self.assertEqual([r['number'] for r in page['jobs']], [2])
        template = page['jobs'][0]['suggestions_template']
        template['suggestions']['strengths'] = [{'text': 'Built Python services.',
            'citations': [{'path': '05 Evidence/Python.md', 'heading': 'Claim'}]}]
        with self.assertRaisesRegex(ValueError, 'approved'):
            preparation.submit_suggestions(handle, {'jobs': [{**template, 'number': 1}]})
        result = preparation.submit_suggestions(handle, {'jobs': [template]})
        self.assertEqual(result['status'], 'ready_for_destinations')
        self.assertEqual(result['suggestions_ready_count'], 1)
        self.assertIsNotNone(preparation.inspect_preparation(handle)['jobs'][0]['suggestions'])
        self.assertEqual({p.name: p.read_bytes() for p in self.resumes.iterdir()}, before)
        self.assertNotIn('suggestions', json.loads((self.state/'report.json').read_text())['candidates'][1])
        self.assertFalse((self.vault/'07 Applications').exists())

    def test_selection_rejects_stale_unknown_and_tampered_scores(self):
        report = self.qualify()
        for identity,numbers in [('stale',[1]),(report['report_id'],[2]),(report['report_id'],[1,1])]:
            with self.assertRaises(ValueError):
                preparation.select_candidates(self.state, identity, numbers)
        with self.assertRaisesRegex(ValueError, 'flags'):
            preparation.select_candidates(self.state, report['report_id'], [1], obsidian='false')
        row = report['candidates'][0]
        path = self.state/(row['job_id']+'-scored.json')
        saved=json.loads(path.read_text()); saved['result']['match']['ATS_score']=99
        path.write_text(json.dumps(saved))
        with self.assertRaisesRegex(ValueError, 'integrity'):
            preparation.select_candidates(self.state, report['report_id'], [1])

    def test_threshold_change_invalidates_selection(self):
        report=self.qualify()
        with patch('scoring.qualification_threshold', return_value=90):
            with self.assertRaisesRegex(ValueError, 'threshold'):
                preparation.select_candidates(self.state, report['report_id'], [1])

    def test_empty_and_failed_runs_have_visible_reports(self):
        self.handoff['jobs']=[]; self.source.write_text(json.dumps(self.handoff))
        support.prepare_run(self.source,self.state,self.vault,self.resumes,hybrid_search=False)
        report=json.loads((self.state/'report.json').read_text())
        self.assertEqual(report['candidates'],[])
        with self.assertRaises(ValueError): preparation.select_candidates(self.state,report['report_id'],[1])
        self.state=self.root/'failed'; self.handoff['jobs']=[self.job];self.source.write_text(json.dumps(self.handoff))
        manifest=self.prepare();identifier=manifest['jobs'][0]['job_id'];self.review_job(manifest,identifier)
        (self.state/(identifier+'-reviewed.json')).write_text('[]')
        support.finalize_assessment(self.state)
        report=json.loads((self.state/'report.json').read_text())
        self.assertFalse(report['selectable'])
        self.assertIn('NONSELECTABLE',(self.state/'report.md').read_text())
        with self.assertRaisesRegex(ValueError,'incomplete'):
            preparation.select_candidates(self.state,report['report_id'],[1])

    def test_preparation_rejects_changed_selection_and_saved_evidence(self):
        report=self.qualify(2)
        selection=preparation.approve_selection(self.state,report['report_id'],[1])
        handle=Path(selection['preparation_handle'])
        path=handle/'selection.json';saved=json.loads(path.read_text())
        saved['numbers']=[2];path.write_text(json.dumps(saved))
        with self.assertRaisesRegex(ValueError,'selection changed'):
            preparation.inspect_preparation(handle)
        path.write_text(json.dumps(selection))
        identifier=selection['selected'][0]['job_id']
        packet_path=self.state/(identifier+'-packet.json')
        packet=json.loads(packet_path.read_text())
        packet['verified_notes']['05 Evidence/Python.md']='Invented experience.'
        packet_path.write_text(json.dumps(packet))
        with self.assertRaisesRegex(ValueError,'evidence changed'):
            preparation.inspect_preparation(handle)

    def test_suggestions_require_frozen_priorities_and_supported_changes(self):
        report=self.qualify()
        selection=preparation.approve_selection(self.state,report['report_id'],[1])
        handle=Path(selection['preparation_handle'])
        template=preparation.inspect_preparation(handle)['jobs'][0]['suggestions_template']
        template['suggestions']['strengths']=[{'text':'Python delivery',
            'citations':[{'path':'05 Evidence/Python.md','heading':'Claim'}]}]
        template['suggestions']['resume_plan']['changes']=[{'text':'Invented leadership',
            'requirement_id':template['suggestions']['jd_priorities'][0]['id'],
            'citations':[{'path':'05 Evidence/Invented.md','heading':'Claim'}], 'review_before_adding':True}]
        with self.assertRaisesRegex(ValueError,'unsupported evidence'):
            preparation.submit_suggestions(handle,{'jobs':[template]})
        self.assertIsNone(preparation.inspect_preparation(handle)['jobs'][0]['suggestions'])
        template['suggestions']['resume_plan']['changes']=[]
        template['suggestions']['jd_priorities']=[]
        with self.assertRaisesRegex(ValueError,'priorities'):
            preparation.submit_suggestions(handle,{'jobs':[template]})

    def test_selected_suggestions_cli_round_trip(self):
        import subprocess
        report=self.qualify()
        script=Path(__file__).resolve().parents[1]/'.agents/skills/job-suggestions/scripts/approved_preparation.py'
        env={**os.environ,'WRITE_OBSIDIAN':'false','WRITE_NOTION':'false'}
        selected=json.loads(subprocess.check_output([sys.executable,str(script),'select',
            '--run',str(self.state),'--report-id',report['report_id'],'--numbers','1'],env=env,text=True))
        self.assertNotIn('selected',selected)
        handle=Path(selected['preparation_handle'])
        page=json.loads(subprocess.check_output([sys.executable,str(script),'inspect',
            '--preparation',str(handle)],env=env,text=True))
        template=page['jobs'][0]['suggestions_template']
        template['suggestions']['strengths']=[{'text':'Built Python services.',
            'citations':[{'path':'05 Evidence/Python.md','heading':'Claim'}]}]
        source=self.root/'suggestions.json';source.write_text(json.dumps({'jobs':[template]}))
        result=json.loads(subprocess.check_output([sys.executable,str(script),'suggestions',
            '--preparation',str(handle),'--input',str(source)],env=env,text=True))
        self.assertEqual(result['status'],'ready_for_destinations')
        self.assertFalse(result['application_records_written'])
        self.assertEqual((handle/'selection.json').stat().st_mode & 0o777,0o600)
        self.assertFalse((self.vault/'07 Applications').exists())

    def test_cached_suggestions_are_revalidated_before_reuse(self):
        report=self.qualify()
        selection=preparation.approve_selection(self.state,report['report_id'],[1])
        handle=Path(selection['preparation_handle'])
        template=preparation.inspect_preparation(handle)['jobs'][0]['suggestions_template']
        template['suggestions']['strengths']=[{'text':'Python delivery',
            'citations':[{'path':'05 Evidence/Python.md','heading':'Claim'}]}]
        preparation.submit_suggestions(handle,{'jobs':[template]})
        path=handle/(selection['selected'][0]['job_id']+'-suggestions.json')
        saved=json.loads(path.read_text());saved['resume_plan']['recommended_resume']='invented.pdf'
        path.write_text(json.dumps(saved))
        with self.assertRaisesRegex(ValueError,'resume plan'):
            preparation.inspect_preparation(handle)

    def test_unsorted_selection_has_a_reusable_preparation_handle(self):
        report=self.qualify(2)
        selection=preparation.approve_selection(self.state,report['report_id'],[2,1])
        page=preparation.inspect_preparation(Path(selection['preparation_handle']),limit=2)
        self.assertEqual([row['number'] for row in page['jobs']],[1,2])

    def test_suggestion_resume_lines_come_from_immutable_pdfs(self):
        report=self.qualify()
        selection=preparation.approve_selection(self.state,report['report_id'],[1])
        identifier=selection['selected'][0]['job_id']
        path=self.state/(identifier+'-packet.json');packet=json.loads(path.read_text())
        packet['resume_lines']['ai.pdf'][0]['text']='Invented qualifications.'
        path.write_text(json.dumps(packet))
        page=preparation.inspect_preparation(Path(selection['preparation_handle']))
        self.assertEqual(page['jobs'][0]['packet']['resume_lines']['ai.pdf'][0]['text'],'Built Python services.')

    def test_destination_procedure_references_an_existing_helper(self):
        import re
        root=Path(__file__).resolve().parents[1]
        doc=(root/'docs/approved-destination-writes.md').read_text()
        paths=re.findall(r'`(\.agents/skills/[^` ]+\.py)(?: select)?`',doc)
        self.assertTrue(paths)
        for path in paths:self.assertTrue((root/path).is_file(),path)

    def test_known_gate_failure_never_initializes_hybrid_services(self):
        self.job['description_text']='Australian citizenship required.'
        self.source.write_text(json.dumps(self.handoff))
        with patch('readiness.build_chroma_index',side_effect=AssertionError('index')), \
             patch('readiness.run_check_index',side_effect=AssertionError('index')), \
             patch.object(support.vault,'run_batch_search',side_effect=AssertionError('query')):
            prepared=support.prepare_run(self.source,self.state,self.vault,self.resumes,hybrid_search=True)
            row=prepared['requirements_template']['jobs'][0]
            row['condition'].update(status='failed',reason='Known citizenship mismatch',clauses=[{
                'kind':'work_rights','wording':'Australian citizenship required.','status':'failed',
                'reason':'Verified not a citizen','profile_fields':['work_authorization.australian_citizen']}])
            result=support.submit_requirements(self.state,{'jobs':[row]})
            self.assertEqual(result['summary']['condition_failed_count'],1)

    def test_uncertain_query_cannot_be_repeated_using_another_output_path(self):
        with patch('readiness.build_chroma_index'),patch('readiness.run_check_index'), \
             patch.object(support.vault,'run_batch_search',side_effect=support.vault.SemanticSearchUnavailable('unknown usage')) as query:
            for state in (self.state,self.root/'another-output'):
                prepared=support.prepare_run(self.source,state,self.vault,self.resumes,hybrid_search=True)
                row=prepared['requirements_template']['jobs'][0]
                row['condition'].update(status='passed',reason='No gate',clauses=[])
                row['classified']['units']=[{'id':1,'category':'ignore','priority':1,'reason':'Title'},
                    {'id':2,'category':'Skills','priority':3,'reason':'Python'}]
                result=support.submit_requirements(state,{'jobs':[row]})
                self.assertTrue(result['failures'])
            self.assertEqual(query.call_count,1)
            self.assertIn('approval',result['failures'][0]['error'])

    def test_suggestions_account_for_known_gaps_and_unclear_conditions(self):
        self.job['description_text']='Permanent work rights required. Build Python services. Use Python. Use Kubernetes.'
        self.source.write_text(json.dumps(self.handoff))
        prepared=support.prepare_run(self.source,self.state,self.vault,self.resumes,hybrid_search=False)
        row=prepared['requirements_template']['jobs'][0]
        row['condition'].update(status='manual_review',reason='Permanent rights wording unclear',clauses=[{
            'kind':'work_rights','wording':'Permanent work rights required.','status':'manual_review',
            'reason':'Current rights verified; permanence unclear','profile_fields':['work_authorization.full_current_work_rights_regions']}])
        row['classified']['units']=[{'id':i,'category':'ignore' if i<3 else 'Skills','priority':1 if i==5 else 3,
            'reason':'Title/condition' if i<3 else 'Explicit skill'} for i in range(1,6)]
        response=support.submit_requirements(self.state,{'jobs':[row]})
        judgment=response['judgments_template']['jobs'][0];judgment['category']='AI Agent'
        for req in judgment['requirements']:
            missing=req['id']=='r5'
            req.update(candidate_strength='missing' if missing else 'direct',candidate_reason='No Kubernetes evidence' if missing else 'Verified Python',
                evidence=[] if missing else [{'path':'05 Evidence/Python.md','heading':'Claim'}],
                resume_strengths={'ai.pdf':'missing' if missing else 'transferable' if req['id']=='r3' else 'direct','cv.pdf':'missing'},
                resume_lines={'ai.pdf':[] if missing else [1],'cv.pdf':[]})
        support.submit_judgments(self.state,{'jobs':[judgment]})
        report=json.loads((self.state/'report.json').read_text());selection=preparation.approve_selection(self.state,report['report_id'],[1])
        handle=Path(selection['preparation_handle'])
        original=preparation.inspect_preparation(handle)['jobs'][0]['suggestions_template']
        original['suggestions']['strengths']=[{'text':'Verified Python','citations':[{'path':'05 Evidence/Python.md','heading':'Claim'}]}]
        import copy
        empty=copy.deepcopy(original);empty['suggestions']['gaps']=[]
        with self.assertRaisesRegex(ValueError,'gap|condition'):preparation.submit_suggestions(handle,{'jobs':[empty]})
        self.assertIn('r5',{g.get('requirement_id') for g in original['suggestions']['gaps']})
        self.assertIn('Permanent work rights required.',{g.get('condition_wording') for g in original['suggestions']['gaps']})
        empty=copy.deepcopy(original);empty['suggestions']['resume_plan']['coverage_gaps']=[]
        with self.assertRaisesRegex(ValueError,'coverage'):preparation.submit_suggestions(handle,{'jobs':[empty]})
        result=preparation.submit_suggestions(handle,{'jobs':[original]})
        self.assertEqual(result['status'],'ready_for_destinations')

    def test_confirmed_hybrid_results_are_reused_across_output_paths(self):
        def successful(vault,requests,*args):
            rows=json.loads(requests.read_text())['requests']
            print(json.dumps({'results':[{'requirement':row['requirement'],'matches':[]} for row in rows]}))
        with patch('readiness.build_chroma_index'),patch('readiness.run_check_index'), \
             patch.object(support.vault,'run_batch_search',side_effect=successful) as query:
            for state in (self.state,self.root/'another-output'):
                prepared=support.prepare_run(self.source,state,self.vault,self.resumes,hybrid_search=True)
                row=prepared['requirements_template']['jobs'][0]
                row['condition'].update(status='passed',reason='No gate',clauses=[])
                row['classified']['units']=[{'id':1,'category':'ignore','priority':1,'reason':'Title'},
                    {'id':2,'category':'Skills','priority':3,'reason':'Python'}]
                response=support.submit_requirements(state,{'jobs':[row]})
                self.assertFalse(response['failures'])
            self.assertEqual(query.call_count,1)

    def test_finalization_keeps_unchanged_outcome_files(self):
        report=self.qualify(2)
        paths=[self.state/(row['job_id']+'-scored.json') for row in report['candidates']]
        timestamps=[path.stat().st_mtime_ns for path in paths]
        support.submit_judgments(self.state,{'jobs':[]})
        self.assertEqual([path.stat().st_mtime_ns for path in paths],timestamps)


if __name__ == '__main__':
    unittest.main()
