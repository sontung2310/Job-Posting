import copy
import json
import io
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".agents/skills/job-scoring/scripts"))
from assessment_fixture import fixture
import scoring
import assessment_validation
import condition_profile
import assessment


class ScoreValidation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.vault, self.resumes = fixture(self.root)
        self.job = {'job_url': 'https://example.test/one', 'company': 'Co', 'position': 'Engineer',
                    'description_text': 'Build Python services.\nBenefits include flexibility.'}
        profile = condition_profile.build_condition_profile(self.vault, self.root/'profile.json')
        self.data = {'job': self.job, 'condition_status': 'passed',
            'condition_review': {'reviewer': 'codex', 'status': 'passed', 'reason': 'No required condition',
                'clauses': [], 'jd_fingerprint': assessment_validation.jd_fingerprint(self.job),
                'profile_fingerprint': assessment_validation.profile_fingerprint(profile)},
            'input_fingerprint': assessment.evidence_fingerprint(self.vault, self.resumes),
            'category': 'AI Agent', 'resumes': ['ai.pdf', 'cv.pdf'],
            'classified': {'units': [
                {'id': 1, 'category': 'Experience', 'priority': 2, 'reason': 'Role scope'},
                {'id': 2, 'category': 'Skills', 'priority': 3, 'reason': 'Required Python'},
                {'id': 3, 'category': 'ignore', 'priority': 1, 'reason': 'Benefits'}]},
            'requirements': [
                {'id': 'r1', 'requirement': 'Engineer', 'category': 'Experience', 'priority': 2,
                 'candidate_strength': 'transferable', 'candidate_reason': 'Related engineering',
                 'evidence': [{'path': '05 Evidence/Python.md', 'heading': 'Claim'}],
                 'resume_strengths': {'ai.pdf': 'transferable', 'cv.pdf': 'missing'},
                 'resume_lines': {'ai.pdf': [1], 'cv.pdf': []}},
                {'id': 'r2', 'requirement': 'Build Python services.', 'category': 'Skills', 'priority': 3,
                 'candidate_strength': 'direct', 'candidate_reason': 'Verified Python delivery',
                 'evidence': [{'path': '05 Evidence/Python.md', 'heading': 'Claim'}],
                 'resume_strengths': {'ai.pdf': 'direct', 'cv.pdf': 'missing'},
                 'resume_lines': {'ai.pdf': [1], 'cv.pdf': []}}],
            'retrieval': {'results': [{'requirement': text, 'matches': [{'path': '05 Evidence/Python.md',
                'heading': 'Claim', 'text': 'Built Python services.', 'source': ['user-confirmed: fixture']}]}
                for text in ['Engineer', 'Build Python services.']]}}

        self.state = self.root/'assessment'
        source = self.root/'jobs.json'
        source.write_text(__import__('json').dumps({'jobs': [self.job], 'coverage': {'status': 'completed'}}))
        assessment.prepare_assessment(source, self.state, self.vault, self.resumes, hybrid_search=False)
        identifier = assessment_validation.job_id(self.job)
        assessment.save_condition(self.state, identifier, self.data['condition_review'])
        assessment.freeze_job(self.state, identifier, self.data['classified'])
        packet = assessment.build_packet(self.state, identifier)
        self.data['retrieval'] = packet['retrieval']
        self.data['linked_sources'] = packet['linked_sources']

    def calculate(self, data=None):
        return scoring.calculate(self.data if data is None else data, vault=self.vault, resumes_dir=self.resumes, state=self.state)

    def test_catalog_ids_are_usable_without_legacy_paths(self):
        data = copy.deepcopy(self.data)
        entry = next(row for row in scoring.evidence_catalog(data['retrieval']) if row['path'] == '05 Evidence/Python.md' and row['heading'] == 'Claim')
        for row in data['requirements']:
            row['evidence'] = [{'evidence_id': entry['evidence_id']}]
        self.assertEqual(self.calculate(data)['match'], self.calculate()['match'])

    def test_all_invalid_citations_return_requirement_diagnostics(self):
        data = copy.deepcopy(self.data)
        for row in data['requirements']:
            row['evidence'] = [{'path': '05 Evidence/Python.md', 'heading': 'Not retrieved'}]
        with self.assertRaises(scoring.CitationValidationError) as caught:
            self.calculate(data)
        self.assertEqual([row['requirement_id'] for row in caught.exception.diagnostics], ['r1', 'r2'])
        self.assertTrue(all(row['allowed_evidence_ids'] for row in caught.exception.diagnostics))

    def test_evidence_id_does_not_allow_conflicting_heading(self):
        data = copy.deepcopy(self.data)
        entry = scoring.evidence_catalog(data['retrieval'])[0]
        data['requirements'][0]['evidence'] = [{'evidence_id': entry['evidence_id'], 'heading': 'Invented'}]
        with self.assertRaises(scoring.CitationValidationError):
            self.calculate(data)

    def test_working_judgment_fields_are_repairable_without_recording_score(self):
        for field, value in [('candidate_strength', 'invented'), ('resume_lines', {'ai.pdf': [999999], 'cv.pdf': []})]:
            with self.subTest(field=field):
                data = copy.deepcopy(self.data)
                data['job_handle'] = assessment_validation.job_id(self.job)
                data['requirements'][0][field] = value
                result = assessment.submit_judgments(self.state, {'jobs': [data]})
                self.assertEqual(result['summary']['scored_job_count'], 0)
                self.assertEqual(result['failures'][0]['error_code'], 'invalid_submission')
                self.assertTrue(result['failures'][0]['recoverable'])
                self.assertEqual(result['failures'][0]['diagnostics'][0]['field'], field)
                identifier = assessment_validation.job_id(self.job)
                self.assertFalse((self.state/f'{identifier}-scored.json').exists())

    def test_public_calculator_checks_current_lines_and_full_original_units(self):
        valid = self.calculate()
        self.assertEqual(valid['match']['ATS_score'], 78)
        self.assertEqual(valid['status'], 'qualified')
        self.assertEqual(valid['resume_coverage'], {'ai.pdf': 78, 'cv.pdf': 0})
        for mutation in ['line', 'empty_lines', 'omitted_unit', 'duplicate_unit', 'changed_wording', 'omitted_requirement', 'stale_condition', 'citation', 'fingerprint', 'retrieval']:
            invalid = copy.deepcopy(self.data)
            if mutation == 'line': invalid['requirements'][0]['resume_lines']['ai.pdf'] = [999]
            if mutation == 'empty_lines': invalid['requirements'][0]['resume_lines']['ai.pdf'] = []
            if mutation == 'omitted_unit': invalid['classified']['units'].pop()
            if mutation == 'duplicate_unit': invalid['classified']['units'][2] = invalid['classified']['units'][1]
            if mutation == 'changed_wording': invalid['requirements'][0]['requirement'] = 'Senior Engineer'
            if mutation == 'omitted_requirement': invalid['requirements'].pop()
            if mutation == 'stale_condition': invalid['condition_review']['jd_fingerprint'] = 'stale'
            if mutation == 'fingerprint': invalid['input_fingerprint'] = 'stale'
            if mutation == 'retrieval': invalid['retrieval']['results'].pop()
            if mutation == 'citation': invalid['requirements'][0]['evidence'][0]['heading'] = 'Invented'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): self.calculate(invalid)

    def test_actual_fit_74_75_76_obeys_exclusive_threshold(self):
        for direct, missing, fit, status in ((20, 7, 74, 'below_threshold'),
                                            (3, 1, 75, 'below_threshold'),
                                            (19, 6, 76, 'qualified')):
            with self.subTest(fit=fit):
                job = {**self.job, 'job_url': f'https://example.test/{fit}',
                       'description_text': '\n'.join('Build Python services.' for _ in range(direct+missing))}
                state = self.root/f'score-{fit}'; source = self.root/f'jobs-{fit}.json'
                source.write_text(json.dumps({'jobs': [job], 'coverage': {'status': 'completed'}}))
                manifest = assessment.prepare_assessment(source, state, self.vault, self.resumes, hybrid_search=False)
                identifier = manifest['jobs'][0]['job_id']
                review = {**self.data['condition_review'], 'jd_fingerprint': assessment_validation.jd_fingerprint(job)}
                assessment.save_condition(state, identifier, review)
                units = manifest['jobs'][0]['units']
                classified = {'units': [{'id': row['id'], 'category': 'ignore' if row['id'] == 1 else 'Skills',
                                         'priority': 1, 'reason': 'Title or Python duty'} for row in units]}
                assessment.freeze_job(state, identifier, classified)
                assessment.build_packet(state, identifier)
                data = json.loads((state/f'{identifier}-review-template.json').read_text())
                for index, requirement in enumerate(data['requirements']):
                    supported = index < direct
                    requirement.update(candidate_strength='direct' if supported else 'missing',
                        candidate_reason='Verified Python delivery' if supported else 'No claimed evidence',
                        evidence=[{'path': '05 Evidence/Python.md', 'heading': 'Claim'}] if supported else [],
                        resume_strengths={'ai.pdf': 'direct' if supported else 'missing', 'cv.pdf': 'missing'},
                        resume_lines={'ai.pdf': [1] if supported else [], 'cv.pdf': []})
                result = scoring.calculate(data, vault=self.vault, resumes_dir=self.resumes, state=state)
                self.assertEqual(result['match']['ATS_score'], fit)
                self.assertEqual(result['status'], status)
                self.assertEqual(result['resume_coverage'], {'ai.pdf': fit, 'cv.pdf': 0})

    def test_jointly_altered_review_cannot_drop_a_persisted_frozen_requirement(self):
        invalid = copy.deepcopy(self.data)
        invalid['classified']['units'][0]['category'] = 'ignore'
        invalid['requirements'] = invalid['requirements'][1:]
        invalid['retrieval']['results'] = invalid['retrieval']['results'][1:]
        with self.assertRaisesRegex(ValueError, 'frozen|persisted|packet'):
            self.calculate(invalid)
        with self.assertRaisesRegex(ValueError, 'frozen'):
            assessment.freeze_job(self.state, assessment_validation.job_id(self.job), invalid['classified'])

    def test_malformed_nested_judgments_fail_validation_without_scores(self):
        for field, value in [('resumes', [['ai.pdf']]), ('retrieval', []), ('requirements', [{'id': []}])]:
            invalid = copy.deepcopy(self.data)
            invalid[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.calculate(invalid)

    def test_certified_skill_with_preferred_degree_can_be_scored_as_missing(self):
        job = {**self.job, 'job_url': 'https://example.test/certified', 'position': 'Cloud Expert',
               'description_text': 'Mandatory: Salesforce Certified JavaScript Developer I Desirable: tertiary qualification in Engineering.'}
        source = self.root/'mixed-job.json'
        source.write_text(json.dumps({'jobs': [job], 'coverage': {'status': 'completed'}}))
        state = self.root/'mixed-assessment'
        manifest = assessment.prepare_assessment(source, state, self.vault, self.resumes, hybrid_search=False)
        identifier = manifest['jobs'][0]['job_id']
        prepared = assessment.submit_requirements(state, {'jobs': [{'job_handle': identifier,
            'condition': {'reviewer': 'codex', 'status': 'passed', 'reason': 'Degree is preferred, not required.', 'clauses': []},
            'classified': {'units': [{'id': 1, 'category': 'ignore', 'priority': 1, 'reason': 'Title'},
                                      {'id': 2, 'category': 'Skills', 'priority': 3, 'reason': 'Mandatory certification; degree is preferred.'}]}}]})
        self.assertEqual(prepared['failures'], [])
        data = json.loads((state/f'{identifier}-review-template.json').read_text())
        data.update(job_handle=identifier, category='Hybrid')
        for requirement in data['requirements']:
            requirement['candidate_strength'] = 'missing'
            requirement['candidate_reason'] = 'No verified Salesforce certification.'
        result = assessment.submit_judgments(state, {'jobs': [data]})
        self.assertEqual(result['summary']['failed_job_count'], 0)
        self.assertEqual(result['summary']['below_threshold_job_count'], 1)

    def test_responsibilities_with_preferred_degree_are_not_education_only(self):
        self.assertFalse(scoring.education_only('Key responsibilities Apply AI to develop assessment products. PhD qualifications will be highly regarded.'))
        self.assertFalse(scoring.education_only('Relevant tertiary qualifications, with experience using Jira and Confluence.'))
        self.assertTrue(scoring.education_only('PhD qualifications in Psychology required.'))

    def test_strong_and_partial_transfer_have_distinct_credit(self):
        for strength, expected in [('strong_transfer', 85), ('partial_transfer', 50)]:
            data = copy.deepcopy(self.data)
            for row in data['requirements']:
                row['candidate_strength'] = strength
                row['resume_strengths']['ai.pdf'] = strength
            result = self.calculate(data)
            self.assertEqual(result['match']['ATS_score'], expected)
            self.assertEqual(result['resume_coverage']['ai.pdf'], expected)
            self.assertEqual(result['score_range'], {'lower': expected, 'upper': expected})

    def test_full_weights_and_unknown_that_cannot_change_qualification(self):
        job = {**self.job, 'description_text': 'Build Python services. Own delivery. Operate software services.'}
        source = self.root/'weighted-jobs.json'
        source.write_text(json.dumps({'jobs': [job], 'coverage': {'status': 'completed'}}))
        state = self.root/'weighted'
        manifest = assessment.prepare_assessment(source, state, self.vault, self.resumes, hybrid_search=False)
        identifier = manifest['jobs'][0]['job_id']
        assessment.save_condition(state, identifier, {**self.data['condition_review'],
            'jd_fingerprint': assessment_validation.jd_fingerprint(job)})
        categories = ['ignore', 'Skills', 'Experience', 'Domain']
        assessment.freeze_job(state, identifier, {'units': [
            {'id': unit['id'], 'category': categories[index], 'priority': 1, 'reason': 'Fixture scope'}
            for index, unit in enumerate(manifest['jobs'][0]['units'])]})
        assessment.build_packet(state, identifier)
        data = json.loads((state/f'{identifier}-review-template.json').read_text())
        data['category'] = 'Hybrid'
        for strengths, fit, upper, coverage in [(['direct', 'strong_transfer', 'partial_transfer'], 85, 85, 100),
                                                (['direct', 'direct', 'unknown'], 80, 100, 80)]:
            for row, strength in zip(data['requirements'], strengths):
                row.update(candidate_strength=strength, candidate_reason='Verified scope or explicit clarification needed.',
                           evidence=[] if strength == 'unknown' else self.data['requirements'][0]['evidence'],
                           resume_strengths={'ai.pdf': 'missing' if strength == 'unknown' else strength, 'cv.pdf': 'missing'},
                           resume_lines={'ai.pdf': [] if strength == 'unknown' else [1], 'cv.pdf': []})
            result = scoring.calculate(data, state=state, vault=self.vault, resumes_dir=self.resumes)
            self.assertEqual(result['category_budgets'], {'Skills': 45, 'Experience': 35, 'Domain': 20})
            self.assertEqual(result['score_range'], {'lower': fit, 'upper': upper})
            self.assertEqual(result['evidence_coverage_percent'], coverage)
            self.assertEqual(result['status'], 'qualified')

    def test_unknown_crossing_threshold_is_nonselectable_and_can_be_resolved(self):
        data = copy.deepcopy(self.data)
        data['job_handle'] = assessment_validation.job_id(self.job)
        row = data['requirements'][0]
        row.update(candidate_strength='unknown', candidate_reason='Confirm delivery ownership.', evidence=[])
        result = assessment.submit_judgments(self.state, {'jobs': [data]})
        outcome = result['jobs'][0]['result']
        self.assertEqual(outcome['score_range'], {'lower': 56, 'upper': 100})
        self.assertEqual(outcome['evidence_coverage_percent'], 56.25)
        self.assertEqual(outcome['unknown_requirements'], ['r1'])
        self.assertEqual(result['progress']['unresolved_job_count'], 1)
        self.assertEqual(result['summary']['evidence_review_job_count'], 1)
        self.assertFalse(json.loads((self.state/'report.json').read_text())['selectable'])
        row.update(candidate_strength='direct', candidate_reason='Verified delivery ownership.',
                   evidence=self.data['requirements'][0]['evidence'])
        resolved = assessment.submit_judgments(self.state, {'jobs': [data]})
        self.assertEqual(resolved['jobs'][0]['status'], 'qualified')
        self.assertEqual(resolved['progress']['unresolved_job_count'], 0)
        self.assertTrue(json.loads((self.state/'report.json').read_text())['selectable'])

    def test_unknown_cannot_rescue_a_score_with_confirmed_large_gaps(self):
        data = copy.deepcopy(self.data)
        data['requirements'][0].update(candidate_strength='unknown', evidence=[])
        data['requirements'][1].update(candidate_strength='missing', evidence=[])
        result = self.calculate(data)
        self.assertEqual(result['status'], 'below_threshold')
        self.assertEqual(result['score_range'], {'lower': 0, 'upper': 44})

    def test_resume_coverage_requires_an_inspected_strength_not_unknown(self):
        data = copy.deepcopy(self.data)
        data['requirements'][0]['resume_strengths']['ai.pdf'] = 'unknown'
        with self.assertRaises(scoring.InvalidSubmissionError):
            self.calculate(data)

    def test_old_policy_cannot_be_silently_rescored(self):
        path = self.state/'manifest.json'
        manifest = json.loads(path.read_text())
        manifest.pop('scoring_policy')
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'scoring policy changed'):
            self.calculate()


if __name__ == '__main__': unittest.main()
