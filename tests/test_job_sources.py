from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
import job_sources  # noqa: E402


class JobSourceTests(unittest.TestCase):
    def test_canonical_url_removes_tracking_parameters(self) -> None:
        self.assertEqual(
            job_sources.canonical_url("https://Example.com/jobs/1/?utm_source=feed&x=1#details"),
            "https://example.com/jobs/1?x=1",
        )

    def test_keyword_matching_requires_all_configured_title_terms_and_location(self) -> None:
        searches = job_sources.search_terms([{"title": "AI Engineer", "location": "Melbourne"}])
        good = job_sources.Job("test", "1", "https://example.com/1", "Example", "Senior AI Engineer", "Melbourne, VIC", "2026-09-29T00:00:00+00:00", None, None, None, "")
        bad_title = good.__class__(**{**good.__dict__, "position": "AI Product Manager"})
        bad_location = good.__class__(**{**good.__dict__, "location": "Sydney, NSW"})
        self.assertTrue(job_sources.matches_search(good, searches))
        self.assertFalse(job_sources.matches_search(bad_title, searches))
        self.assertFalse(job_sources.matches_search(bad_location, searches))

    def test_seven_day_window_rejects_old_and_missing_dates(self) -> None:
        now = datetime(2026, 9, 30, tzinfo=UTC)
        fresh = job_sources.Job("test", "1", "https://example.com/1", "Example", "AI Engineer", "Melbourne", "2026-09-25T00:00:00+00:00", None, None, None, "")
        old = job_sources.Job("test", "2", "https://example.com/2", "Example", "AI Engineer", "Melbourne", "2026-09-22T00:00:00+00:00", None, None, None, "")
        missing = job_sources.Job("test", "3", "https://example.com/3", "Example", "AI Engineer", "Melbourne", None, None, None, None, "")
        self.assertTrue(job_sources.within_window(fresh, now, 7))
        self.assertFalse(job_sources.within_window(old, now, 7))
        self.assertFalse(job_sources.within_window(missing, now, 7))

    def test_relative_ats_posting_date_is_supported(self) -> None:
        parsed = job_sources.parse_datetime("Posted 4 Days Ago")
        self.assertIsNotNone(parsed)
        self.assertLessEqual(datetime.now(UTC) - parsed, timedelta(days=4, seconds=5))

    def test_victoria_posted_date_is_taken_from_detail_page(self) -> None:
        page = '<div>Posted <time datetime="2026-09-29T14:32:07+10:00" class="datetime">29 September 2026</time></div>'
        self.assertEqual(job_sources.parse_victoria_posted(page), "2026-09-29T04:32:07+00:00")

    def test_victoria_card_parser_extracts_job_fields(self) -> None:
        page = '''<div class="views-row"><rpl-content class="job-searchResult">
          <div class="job-searchResult-header"><div class="job-searchResult-header__title">
          <a href="/job/ai-engineer-123"><h3>AI Engineer</h3></a></div>
          <p>Example Health</p></div>
          <div class="job-searchResult-detailsWrapper"><div><p><strong>Location:</strong></p><p>Melbourne</p></div></div>
          <div class="job-searchResult-description"><div class="field--name-description"><p>Build AI systems.</p></div></div>
        </rpl-content></div>'''
        cards = list(job_sources.parse_victoria_cards(page))
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0][1], "AI Engineer")
        self.assertEqual(cards[0][2], "Example Health")
        self.assertEqual(cards[0][3], "Melbourne")

    def test_aps_listing_parser_extracts_posted_date_and_fields(self) -> None:
        page = '''<c-aps_vacancy-feed-card data-id="APS-1">
          <p class="content__label content__text--quiet">Posted: <time datetime="2026-09-29">29/09/2026</time></p>
          <p class="content__label content__text--highlight">Example Agency</p>
          <a href="./job-details?Id=APS-1"><h3>AI Engineer</h3></a>
          <p class="content__label content__label--quiet">$100,000 to $120,000</p>
          <p class="content__label content__text--quiet">Location</p><p>Melbourne VIC</p>
        </c-aps_vacancy-feed-card>'''
        cards = job_sources.parse_aps_listing_cards(page)
        self.assertEqual(cards[0]["source_job_id"], "APS-1")
        self.assertEqual(cards[0]["title"], "AI Engineer")
        self.assertEqual(cards[0]["location"], "Melbourne VIC")
        self.assertEqual(cards[0]["posted"], "2026-09-29")

    def test_sa_listing_parser_extracts_posting_date_and_agency(self) -> None:
        page = '''<table id="brs_report_table_140"><tr class="evenrow">
          <td tabindex="7"><a href="/jb/page/abc">AI Engineer</a></td>
          <td tabindex="10">SA-1</td><td tabindex="27">29/09/2026</td>
          <td tabindex="34">Example Agency</td>
        </tr></table>'''
        rows = job_sources.parse_sa_listing_rows(page)
        self.assertEqual(rows[0]["title"], "AI Engineer")
        self.assertEqual(rows[0]["source_job_id"], "SA-1")
        self.assertEqual(rows[0]["posted"], "29/09/2026")
        self.assertEqual(rows[0]["company"], "Example Agency")

    def test_sa_detail_uses_listing_fallbacks_and_real_location(self) -> None:
        page = '''<div class="aJobTitle">AI Engineer</div>
          <div>Location: 5000 - ADELAIDE Job status: Ongoing</div>'''
        detail = job_sources.parse_sa_detail(page, fallback_title="AI Engineer", fallback_company="Example Agency", fallback_posted="29/09/2026")
        self.assertEqual(detail["title"], "AI Engineer")
        self.assertEqual(detail["company"], "Example Agency")
        self.assertEqual(detail["posted"], "29/09/2026")
        self.assertIn("ADELAIDE", detail["location"])

    def test_wa_listing_parser_extracts_public_card_fields(self) -> None:
        page = '''<article class="col-12 job-search-results-card-col">
          <h3 class="card-title job-search-results-card-title"><a href="https://search.jobs.wa.gov.au/jobs/ai-engineer">AI Engineer</a></h3>
          <li class="job-component-department"><span>Department of Innovation</span></li>
          <li class="job-component-dropdown-field-5"><span>From $120,000</span></li>
          <li class="job-component-dropdown-field-9"><span>Perth</span></li>
        </article>'''
        cards = job_sources.parse_wa_listing_cards(page)
        self.assertEqual(cards[0]["title"], "AI Engineer")
        self.assertEqual(cards[0]["company"], "Department of Innovation")
        self.assertEqual(cards[0]["location"], "Perth")

    def test_wa_detail_parser_reads_jobposting_json_ld(self) -> None:
        page = '''<script type="application/ld+json">{"@type":"JobPosting","title":"AI Engineer","datePosted":"2026-09-29T00:00:00Z","description":"<p>Build systems.</p>","hiringOrganization":{"name":"WA Agency"},"identifier":{"value":"WA-1"},"jobLocation":{"address":{"addressLocality":"Perth","addressRegion":"Western Australia"}}}</script>'''
        detail = job_sources.parse_wa_detail(page)
        self.assertEqual(detail["source_job_id"], "WA-1")
        self.assertEqual(detail["title"], "AI Engineer")
        self.assertEqual(detail["posted"], "2026-09-29T00:00:00Z")
        self.assertIn("Perth", detail["location"])


if __name__ == "__main__":
    unittest.main()
