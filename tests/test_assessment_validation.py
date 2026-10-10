import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import assessment_validation as prepare


class Conditions(unittest.TestCase):
    def test_conditions_require_review_and_keep_identical_jobs(self):
        jobs = [{'job_url': f'https://example.test/{i}', 'company': 'Co',
                 'position': 'Engineer', 'description_text': 'Australian citizenship required.'}
                for i in (1, 2)]
        profile = {'schema_version': 1, 'work_authorization': {'australian_citizen': False}, 'education': ['Master'],
                   'sources': {key: {'source': ['verified'], 'last_verified': '2026-10-01'}
                               for key in ('work_authorization', 'education')}}
        pending = prepare.prepare_jobs(jobs, profile)
        self.assertEqual(len(pending['jobs']), 2)
        self.assertNotEqual(pending['jobs'][0]['job_id'], pending['jobs'][1]['job_id'])
        reviews = {row['job_id']: {'status': 'failed', 'reason': 'Required citizenship mismatch',
                  'reviewer': 'codex', 'jd_fingerprint': row['jd_fingerprint'],
                  'profile_fingerprint': pending['profile_fingerprint'],
                  'clauses': [{'wording': 'Australian citizenship required.', 'kind': 'work_rights',
                               'status': 'failed', 'reason': 'Verified profile mismatch',
                               'profile_fields': ['work_authorization.australian_citizen']}]}
                   for row in pending['jobs']}
        self.assertEqual([prepare.validate_condition(job, profile, reviews[prepare.job_id(job)])
                          for job in jobs], ['failed', 'failed'])
        reviews[pending['jobs'][0]['job_id']]['clauses'][0]['kind'] = 'licence'
        with self.assertRaises(ValueError):
            prepare.validate_condition(jobs[0], profile, reviews[pending['jobs'][0]['job_id']])
        with self.assertRaisesRegex(ValueError, 'duplicate canonical job URL'):
            prepare.prepare_jobs([jobs[0], jobs[0]], profile)


if __name__ == '__main__':
    unittest.main()
