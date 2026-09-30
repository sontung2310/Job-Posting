#!/usr/bin/env python3
"""Fetch, normalize, and validate structured job sources.

This is deliberately separate from the Codex discovery prompt. It gives the
pipeline a deterministic source layer inspired by career-ops' provider modules:
one adapter per source, a shared Job shape, strict freshness checks, and
keyword/location filtering before jobs reach scoring.

The default production workflow remains the 24-hour workflow in
config/search_targets.yaml. Use --days 7 only for source verification.
"""

from __future__ import annotations

import argparse
import asyncio
import html
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

try:
    import yaml
except ImportError:  # pragma: no cover - exercised by the CLI environment
    yaml = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEARCH_CONFIG = PROJECT_ROOT / "config" / "search_targets.yaml"
DEFAULT_SOURCE_CONFIG = PROJECT_ROOT / "config" / "source_boards.yaml"
USER_AGENT = "Job-Search-source-verifier/1.0 (+public-job-source-client)"
TRACKING_KEYS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "source"}
STOPWORDS = {"a", "an", "and", "for", "in", "of", "the", "to", "with"}


@dataclass(frozen=True)
class Job:
    source: str
    source_job_id: str | None
    job_url: str
    company: str
    position: str
    location: str
    posted_at: str | None
    salary: str | None
    contact_email: str | None
    company_website: str | None
    description_text: str


class SourceError(RuntimeError):
    pass


def error_text(error: BaseException) -> str:
    message = compact_text(error)
    return f"{type(error).__name__}: {message}" if message else type(error).__name__


def compact_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", html.unescape(str(value))).strip()


def canonical_url(value: Any) -> str:
    raw = compact_text(value)
    if not raw:
        return ""
    parts = urlsplit(raw)
    query = [(key, val) for key, val in parse_qsl(parts.query, keep_blank_values=True) if key.lower() not in TRACKING_KEYS]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/") or "/", urlencode(query), ""))


def parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        # ATS feeds use both epoch seconds and epoch milliseconds.
        seconds = float(value) / (1000 if float(value) > 10_000_000_000 else 1)
        return datetime.fromtimestamp(seconds, UTC)
    raw = compact_text(value)
    if not raw:
        return None
    relative = re.fullmatch(r"(?:posted\s+)?(today|yesterday|\d+)\s+(hour|hours|day|days)\s+ago", raw, re.I)
    if relative:
        amount = 0 if relative.group(1).lower() == "today" else int(relative.group(1))
        unit = relative.group(2).lower()
        delta = timedelta(hours=amount) if unit.startswith("hour") else timedelta(days=amount)
        return datetime.now(UTC) - delta
    if raw.lower() in {"posted today", "today"}:
        return datetime.now(UTC)
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d %B %Y", "%A %d %B %Y"):
            try:
                parsed = datetime.strptime(raw, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    return parsed.replace(tzinfo=parsed.tzinfo or UTC).astimezone(UTC)


def iso_datetime(value: Any) -> str | None:
    parsed = parse_datetime(value)
    return parsed.isoformat(timespec="seconds") if parsed else None


def strip_html(value: Any) -> str:
    class TextParser(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.parts: list[str] = []

        def handle_data(self, data: str) -> None:
            self.parts.append(data)

    parser = TextParser()
    parser.feed(html.unescape(str(value or "")))
    return compact_text(" ".join(parser.parts))


def fetch_bytes(url: str, *, method: str = "GET", body: bytes | None = None, headers: dict[str, str] | None = None) -> bytes:
    request_headers = {"User-Agent": USER_AGENT, "Accept": "application/json, text/html;q=0.9, */*;q=0.8"}
    if headers:
        request_headers.update(headers)
    request = Request(url, data=body, headers=request_headers, method=method)
    try:
        with urlopen(request, timeout=35) as response:
            return response.read()
    except (HTTPError, URLError, TimeoutError) as error:
        detail = getattr(error, "reason", error)
        raise SourceError(f"{method} {url} failed: {detail}") from error


def fetch_json(url: str, *, method: str = "GET", payload: dict[str, Any] | None = None) -> Any:
    body = json.dumps(payload).encode() if payload is not None else None
    raw = fetch_bytes(url, method=method, body=body, headers={"Content-Type": "application/json"} if body else None)
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except json.JSONDecodeError as error:
        raise SourceError(f"{url} returned invalid JSON") from error


def nested(value: Any, *keys: str, default: Any = None) -> Any:
    current = value
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return default if current is None else current


def location_text(value: Any) -> str:
    if isinstance(value, str):
        return compact_text(value)
    if isinstance(value, list):
        return " · ".join(dict.fromkeys(location_text(item) for item in value if location_text(item)))
    if isinstance(value, dict):
        fields = ("fullLocation", "display_name", "name", "city", "region", "state", "addressLocality", "addressRegion", "postalCode", "country")
        direct = compact_text(", ".join(str(value[key]) for key in fields if value.get(key)))
        if direct:
            return direct
        if value.get("address"):
            return location_text(value["address"])
    return ""


def make_job(source: str, company: str, *, url: Any, job_id: Any, title: Any, location: Any, posted: Any, description: Any = "", salary: Any = None) -> Job | None:
    job_url = canonical_url(url)
    position = compact_text(title)
    if not job_url or not position:
        return None
    return Job(
        source=source,
        source_job_id=compact_text(job_id) or None,
        job_url=job_url,
        company=compact_text(company),
        position=position,
        location=location_text(location),
        posted_at=iso_datetime(posted),
        salary=compact_text(salary) or None,
        contact_email=None,
        company_website=None,
        description_text=strip_html(description),
    )


class Adapter:
    source_id = ""

    def fetch(self, config: dict[str, Any]) -> list[Job]:
        raise NotImplementedError


class GreenhouseAdapter(Adapter):
    source_id = "greenhouse"

    def fetch(self, config: dict[str, Any]) -> list[Job]:
        jobs: list[Job] = []
        for board in config.get("boards", []):
            url = compact_text(board.get("api"))
            if not url:
                continue
            separator = "&" if "?" in url else "?"
            payload = fetch_json(f"{url}{separator}content=true")
            for raw in payload.get("jobs", []) if isinstance(payload, dict) else []:
                job = make_job(self.source_id, board.get("name", ""), url=raw.get("absolute_url"), job_id=raw.get("id"), title=raw.get("title"), location=nested(raw, "location", "name"), posted=raw.get("first_published"), description=raw.get("content"))
                if job:
                    jobs.append(job)
        return jobs


class AshbyAdapter(Adapter):
    source_id = "ashby"

    def fetch(self, config: dict[str, Any]) -> list[Job]:
        jobs: list[Job] = []
        for board in config.get("boards", []):
            payload = fetch_json(compact_text(board.get("api")))
            for raw in payload.get("jobs", []) if isinstance(payload, dict) else []:
                job = make_job(self.source_id, board.get("name", ""), url=raw.get("jobUrl"), job_id=raw.get("id"), title=raw.get("title"), location=[raw.get("location"), *(raw.get("secondaryLocations") or [])], posted=raw.get("publishedAt"), description=raw.get("descriptionPlain"))
                if job:
                    jobs.append(job)
        return jobs


class LeverAdapter(Adapter):
    source_id = "lever"

    def fetch(self, config: dict[str, Any]) -> list[Job]:
        jobs: list[Job] = []
        for board in config.get("boards", []):
            payload = fetch_json(compact_text(board.get("api")))
            for raw in payload if isinstance(payload, list) else []:
                job = make_job(self.source_id, board.get("name", ""), url=raw.get("hostedUrl") or raw.get("applyUrl"), job_id=raw.get("id"), title=raw.get("text"), location=nested(raw, "categories", "location"), posted=raw.get("createdAt"), description=raw.get("descriptionPlain"), salary=nested(raw, "salaryRange", "currency"))
                if job:
                    jobs.append(job)
        return jobs


class WorkdayAdapter(Adapter):
    source_id = "workday"

    def fetch(self, config: dict[str, Any]) -> list[Job]:
        jobs: list[Job] = []
        for board in config.get("boards", []):
            endpoint = compact_text(board.get("api"))
            if not endpoint:
                continue
            if not endpoint.rstrip("/").endswith("/jobs"):
                endpoint = endpoint.rstrip("/") + "/jobs"
            for offset in range(0, int(board.get("max_pages", 10)) * 20, 20):
                payload = fetch_json(endpoint, method="POST", payload={"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": ""})
                rows = payload.get("jobPostings", []) if isinstance(payload, dict) else []
                if not rows:
                    break
                for raw in rows:
                    path = raw.get("externalPath") or raw.get("url")
                    job_url = urljoin(board.get("careers_url", endpoint) + "/", path or "")
                    job = make_job(self.source_id, board.get("name", ""), url=job_url, job_id=raw.get("jobPostingId") or path, title=raw.get("title"), location=raw.get("locationsText") or raw.get("location"), posted=raw.get("postedOn") or raw.get("datePosted"), description=raw.get("jobDescription") or raw.get("bulletFields"))
                    if job:
                        jobs.append(job)
                if len(rows) < 20:
                    break
        return jobs


class SmartRecruitersAdapter(Adapter):
    source_id = "smartrecruiters"

    def fetch(self, config: dict[str, Any]) -> list[Job]:
        jobs: list[Job] = []
        for board in config.get("boards", []):
            company_id = compact_text(board.get("company_id"))
            if not company_id:
                continue
            for offset in range(0, int(board.get("max_pages", 5)) * 100, 100):
                url = f"https://api.smartrecruiters.com/v1/companies/{company_id}/postings?limit=100&offset={offset}"
                payload = fetch_json(url)
                rows = payload.get("content", []) if isinstance(payload, dict) else []
                for raw in rows:
                    location = raw.get("location") or {}
                    job = make_job(self.source_id, board.get("name", company_id), url=raw.get("ref") or raw.get("postingUrl"), job_id=raw.get("id"), title=raw.get("name"), location=location, posted=raw.get("releasedDate"), description=raw.get("jobAd", {}).get("sections", {}).get("jobDescription", {}).get("text") if isinstance(raw.get("jobAd"), dict) else "")
                    if job:
                        jobs.append(job)
                if len(rows) < 100:
                    break
        return jobs


def _html_attribute(attributes: str, name: str) -> str:
    match = re.search(rf"\b{re.escape(name)}\s*=\s*(['\"])(.*?)\1", attributes, re.I | re.S)
    return compact_text(match.group(2)) if match else ""


def parse_aps_listing_cards(page: str) -> list[dict[str, str]]:
    """Parse the rendered APS Lightning vacancy cards, not the Salesforce shell."""
    cards: list[dict[str, str]] = []
    pattern = re.compile(r"<c-aps_vacancy-feed-card\b([^>]*)>(.*?)</c-aps_vacancy-feed-card>", re.I | re.S)
    for attributes, card in pattern.findall(page):
        link = re.search(r'<a\s+href="([^"]*job-details[^"]*)"[^>]*>\s*<h3[^>]*>(.*?)</h3>', card, re.I | re.S)
        if not link:
            continue
        posted = re.search(r"Posted:.*?<time\s+datetime=\"([^\"]+)\"", card, re.I | re.S)
        company = re.search(r'<p[^>]*class="[^"]*content__text--highlight[^"]*"[^>]*>(.*?)</p>', card, re.I | re.S)
        location = re.search(r">\s*Location\s*</p>\s*<p[^>]*>(.*?)</p>", card, re.I | re.S)
        salary = re.search(r'<p[^>]*class="[^"]*content__label--quiet[^"]*"[^>]*>(\$.*?)(?:</p>)', card, re.I | re.S)
        cards.append(
            {
                "source_job_id": _html_attribute(attributes, "data-id"),
                "url": compact_text(link.group(1)),
                "title": strip_html(link.group(2)),
                "company": strip_html(company.group(1)) if company else "Australian Public Service",
                "location": strip_html(location.group(1)) if location else "Australia",
                "posted": compact_text(posted.group(1)) if posted else "",
                "salary": strip_html(salary.group(1)) if salary else "",
            }
        )
    return cards


def parse_aps_detail(page: str) -> dict[str, str]:
    posted = re.search(r'<div[^>]*class="[^"]*job_detail__top[^"]*"[^>]*>.*?<time\s+datetime="([^"]+)"', page, re.I | re.S)
    company = re.search(r'<p[^>]*class="[^"]*content__text--highlight[^"]*"[^>]*>(.*?)</p>', page, re.I | re.S)
    title = re.search(r'<div[^>]*class="[^"]*job_detail__header[^"]*"[^>]*>.*?<h3[^>]*>(.*?)</h3>', page, re.I | re.S)
    location = re.search(r'<p[^>]*class="[^"]*content__location[^"]*"[^>]*>(.*?)</p>', page, re.I | re.S)
    article = re.search(r'<article[^>]*class="[^"]*job_detail__content[^\"]*"[^>]*>(.*?)</article>', page, re.I | re.S)
    salary = re.search(r"Salary\s*.*?(\$[0-9,]+\s*to\s*\$[0-9,]+)", strip_html(page), re.I | re.S)
    return {
        "posted": compact_text(posted.group(1)) if posted else "",
        "company": strip_html(company.group(1)) if company else "",
        "title": strip_html(title.group(1)) if title else "",
        "location": strip_html(location.group(1)) if location else "",
        "description": strip_html(article.group(1)) if article else strip_html(page),
        "salary": compact_text(salary.group(1)) if salary else "",
    }


def parse_sa_listing_rows(page: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    row_pattern = re.compile(r'<tr\s+class="(?:evenrow|oddrow)"[^>]*>(.*?)</tr>', re.I | re.S)

    def cell(row: str, tabindex: str) -> str:
        match = re.search(rf'<td[^>]*tabindex=[\'\"]{tabindex}[\'\"][^>]*>(.*?)</td>', row, re.I | re.S)
        return strip_html(match.group(1)) if match else ""

    for row in row_pattern.findall(page):
        link = re.search(r'<a\s+href="([^"]+)"[^>]*>(.*?)</a>', row, re.I | re.S)
        if not link:
            continue
        rows.append(
            {
                "url": compact_text(link.group(1)),
                "title": strip_html(link.group(2)),
                "source_job_id": cell(row, "10"),
                "posted": cell(row, "27"),
                "company": cell(row, "34"),
            }
        )
    return rows


def parse_sa_detail(page: str, *, fallback_title: str = "", fallback_company: str = "", fallback_posted: str = "") -> dict[str, str]:
    text = strip_html(page)
    title_match = re.search(r'<(?:div|h1)[^>]*class="[^"]*aJobTitle[^"]*"[^>]*>(.*?)</(?:div|h1)>', page, re.I | re.S)
    location_match = re.search(r"\bLocation:\s*(.*?)\s+Job status:", text, re.I)
    return {
        "title": strip_html(title_match.group(1)) if title_match else fallback_title,
        "posted": fallback_posted,
        "location": compact_text(location_match.group(1)) if location_match else "South Australia",
        "company": fallback_company or "South Australian Government",
        "description": text,
    }


def parse_wa_listing_cards(page: str) -> list[dict[str, str]]:
    """Parse the public WA Government Jobs result cards."""
    cards: list[dict[str, str]] = []
    article_pattern = re.compile(r'<article[^>]*class="[^"]*job-search-results-card-col[^"]*"[^>]*>(.*?)</article>', re.I | re.S)

    def list_item(card: str, class_name: str) -> str:
        match = re.search(rf'<li[^>]*class="[^"]*{re.escape(class_name)}[^"]*"[^>]*>(.*?)</li>', card, re.I | re.S)
        return strip_html(match.group(1)) if match else ""

    for card in article_pattern.findall(page):
        link = re.search(r'<h3[^>]*class="[^"]*job-search-results-card-title[^"]*"[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', card, re.I | re.S)
        if not link:
            continue
        cards.append(
            {
                "url": compact_text(link.group(1)),
                "title": strip_html(link.group(2)),
                "company": list_item(card, "job-component-department"),
                "location": list_item(card, "job-component-dropdown-field-9"),
                "salary": list_item(card, "job-component-dropdown-field-5"),
            }
        )
    return cards


def parse_wa_detail(page: str) -> dict[str, str]:
    """Read the stable JobPosting JSON-LD embedded in a WA detail page."""
    for block in re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', page, re.I | re.S):
        try:
            payload = json.loads(html.unescape(block).strip())
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict) or payload.get("@type") != "JobPosting":
            continue
        location = payload.get("jobLocation")
        return {
            "source_job_id": compact_text(nested(payload, "identifier", "value")),
            "title": compact_text(payload.get("title")),
            "posted": compact_text(payload.get("datePosted")),
            "company": compact_text(nested(payload, "hiringOrganization", "name")),
            "location": location_text(location),
            "description": compact_text(payload.get("description")),
            "salary": "",
        }
    return {}


def _append_query(url: str, **params: Any) -> str:
    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    query.extend((key, str(value)) for key, value in params.items() if value is not None)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _browser_settings(config: dict[str, Any]) -> tuple[bool, int, int]:
    settings = config.get("_browser", {}) if isinstance(config.get("_browser"), dict) else {}
    return (
        bool(settings.get("headless", True)),
        max(1, int(settings.get("max_concurrency", 4))),
        max(10, int(settings.get("timeout_seconds", 45))) * 1000,
    )


def _unique_title_searches(searches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Avoid repeating the same browser search for city variants a portal cannot filter."""
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for search in searches:
        title = compact_text(search.get("title"))
        if not title or title.casefold() in seen:
            continue
        seen.add(title.casefold())
        result.append(search)
    return result


def _require_playwright() -> Any:
    try:
        from playwright.async_api import async_playwright
    except ImportError as error:  # pragma: no cover - depends on environment setup
        raise SourceError("Playwright is required for browser-backed sources; install requirements-sources.txt") from error
    return async_playwright


async def _wait_for_aps_results(page: Any, timeout_ms: int) -> str:
    """Wait for either APS result cards or its explicit empty-result state."""
    marker_timeout = min(timeout_ms, 15_000)
    try:
        await page.wait_for_function(
            """() => {
                const html = document.documentElement?.outerHTML || '';
                const text = document.body?.innerText || '';
                return html.includes('c-aps_vacancy-feed-card') ||
                    /0\\s+Jobs\\s+Found|There were no results for this search criteria/i.test(text);
            }""",
            timeout=marker_timeout,
        )
    except Exception as error:
        listing_html = await page.content()
        if "c-aps_vacancy-feed-card" not in listing_html:
            raise SourceError("APS Jobs did not render a result or explicit empty state") from error
    return await page.content()


async def _aps_fetch_async(config: dict[str, Any]) -> list[Job]:
    async_playwright = _require_playwright()
    headless, _, timeout_ms = _browser_settings(config)
    searches = _unique_title_searches(config.get("searches", []))
    days = int(config.get("_days", 7))
    jobs: list[Job] = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=headless)
        context = await browser.new_context(locale="en-AU", viewport={"width": 1440, "height": 1200})

        async def fetch_search(search: dict[str, Any]) -> list[Job]:
            page = await context.new_page()
            try:
                search_url = _append_query(config["search_url"], **{config.get("query_param", "searchString"): search.get("title", "")})
                response = await page.goto(search_url, wait_until="domcontentloaded", timeout=timeout_ms)
                if response and response.status >= 400:
                    raise SourceError(f"APS Jobs returned HTTP {response.status}")
                listing_html = await _wait_for_aps_results(page, timeout_ms)
                cards = parse_aps_listing_cards(listing_html)
                if not cards:
                    return []

                async def fetch_detail(card: dict[str, str]) -> Job | None:
                    posted = parse_datetime(card.get("posted"))
                    now = datetime.now(UTC)
                    if not posted or not (now - timedelta(days=days) <= posted <= now + timedelta(minutes=5)):
                        return None
                    detail_page = await context.new_page()
                    try:
                        detail_url = urljoin(config["search_url"], card["url"])
                        detail_response = await detail_page.goto(detail_url, wait_until="domcontentloaded", timeout=timeout_ms)
                        if detail_response and detail_response.status >= 400:
                            raise SourceError(f"APS detail page returned HTTP {detail_response.status}")
                        await detail_page.wait_for_function("document.documentElement.outerHTML.includes('job_detail__header')", timeout=timeout_ms)
                        detail = parse_aps_detail(await detail_page.content())
                        return make_job(
                            "aps_jobs",
                            detail.get("company") or card.get("company", ""),
                            url=detail_url,
                            job_id=card.get("source_job_id"),
                            title=detail.get("title") or card.get("title"),
                            location=detail.get("location") or card.get("location", ""),
                            posted=detail.get("posted") or card.get("posted"),
                            description=detail.get("description", ""),
                            salary=detail.get("salary") or card.get("salary"),
                        )
                    finally:
                        await detail_page.close()

                detail_results = await asyncio.gather(*(fetch_detail(card) for card in cards), return_exceptions=True)
                output: list[Job] = []
                for result in detail_results:
                    if isinstance(result, Job):
                        output.append(result)
                return output
            finally:
                await page.close()

        results: list[list[Job] | Exception] = []
        try:
            # Keep requests for one portal sequential; parallelism is across
            # independent portals, while this avoids triggering APS throttling.
            for search in searches:
                try:
                    results.append(await asyncio.wait_for(fetch_search(search), timeout=timeout_ms / 1000))
                except Exception as error:
                    results.append(error)
        finally:
            await context.close()
            await browser.close()
        errors = [result for result in results if isinstance(result, Exception)]
        if errors:
            raise SourceError("APS Jobs Playwright errors: " + "; ".join(error_text(error) for error in errors[:3]))
        for result in results:
            jobs.extend(result)
    return jobs


async def _sa_fetch_async(portal: dict[str, Any], searches: list[dict[str, Any]], browser_config: dict[str, Any], days: int) -> list[Job]:
    async_playwright = _require_playwright()
    headless, max_concurrency, timeout_ms = _browser_settings({"_browser": browser_config})
    portal_timeout_ms = min(timeout_ms, 30_000)
    date_label = "Last Day" if days <= 1 else "Last Week" if days <= 7 else "Last 2 Weeks" if days <= 14 else "Last Month"
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=headless)
        context = await browser.new_context(locale="en-AU", viewport={"width": 1440, "height": 1200})
        semaphore = asyncio.Semaphore(max_concurrency)

        async def fetch_search(search: dict[str, Any]) -> list[Job]:
            async with semaphore:
                page = await context.new_page()
                try:
                    await page.goto(portal["search_url"], wait_until="domcontentloaded", timeout=portal_timeout_ms)
                    await page.locator("#Data3108").fill(search.get("title", ""), timeout=portal_timeout_ms)
                    # SA hides the native select behind a custom widget.  Use
                    # the real option value and dispatch the browser event so
                    # the form receives the same state as a user selection.
                    await page.locator("#PostingDate3107").evaluate(
                        """(element, label) => {
                            const option = Array.from(element.options).find(
                                (candidate) => candidate.textContent.trim() === label
                            );
                            if (!option) throw new Error(`SA date option not found: ${label}`);
                            element.value = option.value;
                            element.dispatchEvent(new Event('change', { bubbles: true }));
                        }""",
                        date_label,
                    )
                    await page.locator('input[name="action"]').evaluate('(element) => { element.value = "Search"; }')
                    await page.locator('form[name="mainForm"]').evaluate("(form) => form.submit()")
                    try:
                        await page.wait_for_url(re.compile(r"/jb/page/"), timeout=portal_timeout_ms)
                    except Exception:
                        await page.wait_for_timeout(2000)
                    result_html = await page.content()
                    rows = parse_sa_listing_rows(result_html)
                    requested_terms = {
                        token
                        for token in re.findall(r"[a-z0-9]+", compact_text(search.get("title")).lower())
                        if token not in STOPWORDS
                    }
                    rows = [
                        row
                        for row in rows
                        if requested_terms.issubset(set(re.findall(r"[a-z0-9]+", row["title"].lower())))
                    ]

                    async def fetch_detail(row: dict[str, str]) -> Job | None:
                        posted = parse_datetime(row.get("posted"))
                        now = datetime.now(UTC)
                        if not posted or not (now - timedelta(days=days) <= posted <= now + timedelta(minutes=5)):
                            return None
                        detail_page = await context.new_page()
                        try:
                            detail_url = urljoin(portal["search_url"], row["url"])
                            await detail_page.goto(detail_url, wait_until="domcontentloaded", timeout=portal_timeout_ms)
                            detail = parse_sa_detail(
                                await detail_page.content(),
                                fallback_title=row.get("title", ""),
                                fallback_company=row.get("company", ""),
                                fallback_posted=row.get("posted", ""),
                            )
                            return make_job(
                                "state_portals",
                                detail.get("company") or row.get("company", ""),
                                url=detail_url,
                                job_id=row.get("source_job_id"),
                                title=detail.get("title") or row.get("title"),
                                location=detail.get("location", "South Australia"),
                                posted=detail.get("posted") or row.get("posted"),
                                description=detail.get("description", ""),
                            )
                        finally:
                            await detail_page.close()

                    detail_results = await asyncio.gather(*(fetch_detail(row) for row in rows), return_exceptions=True)
                    return [result for result in detail_results if isinstance(result, Job)]
                finally:
                    await page.close()

        results = await asyncio.gather(
            *(asyncio.wait_for(fetch_search(search), timeout=portal_timeout_ms / 1000) for search in searches),
            return_exceptions=True,
        )
        errors = [result for result in results if isinstance(result, Exception)]
        await context.close()
        await browser.close()
        if errors:
            raise SourceError("South Australia Playwright errors: " + "; ".join(error_text(error) for error in errors[:3]))
        return [job for result in results for job in result]


async def _wa_fetch_async(portal: dict[str, Any], searches: list[dict[str, Any]], browser_config: dict[str, Any], days: int) -> list[Job]:
    async_playwright = _require_playwright()
    headless, max_concurrency, timeout_ms = _browser_settings({"_browser": browser_config})
    title_searches = _unique_title_searches(searches)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=headless)
        context = await browser.new_context(locale="en-AU", viewport={"width": 1440, "height": 1200})
        detail_semaphore = asyncio.Semaphore(max_concurrency)

        def requested_terms(search: dict[str, Any]) -> tuple[set[str], str]:
            terms = {token for token in re.findall(r"[a-z0-9]+", compact_text(search.get("title")).lower()) if token not in STOPWORDS}
            return terms, compact_text(search.get("location")).lower()

        async def fetch_search(search: dict[str, Any]) -> list[Job]:
            page = await context.new_page()
            try:
                search_url = _append_query(portal["search_url"], query=search.get("title", ""), page=1)
                response = await page.goto(search_url, wait_until="domcontentloaded", timeout=timeout_ms)
                if response and response.status >= 400:
                    raise SourceError(f"Western Australia returned HTTP {response.status}")
                cards = parse_wa_listing_cards(await page.content())
                terms, requested_location = requested_terms(search)
                candidates = [
                    card
                    for card in cards
                    if terms.issubset(set(re.findall(r"[a-z0-9]+", card["title"].lower())))
                    and (not requested_location or requested_location in card["location"].lower())
                ]

                async def fetch_detail(card: dict[str, str]) -> Job | None:
                    async with detail_semaphore:
                        detail_page = await context.new_page()
                        try:
                            detail_url = canonical_url(urljoin(portal["search_url"], card["url"]))
                            detail_response = await detail_page.goto(detail_url, wait_until="domcontentloaded", timeout=timeout_ms)
                            if detail_response and detail_response.status >= 400:
                                raise SourceError(f"WA detail page returned HTTP {detail_response.status}")
                            detail = parse_wa_detail(await detail_page.content())
                            if not detail:
                                raise SourceError("WA detail page did not expose JobPosting JSON-LD")
                            return make_job(
                                "state_portals",
                                card.get("company") or detail.get("company", ""),
                                url=detail_url,
                                job_id=detail.get("source_job_id") or detail_url.rsplit("/", 1)[-1],
                                title=detail.get("title") or card.get("title"),
                                location=detail.get("location") or card.get("location", "Western Australia"),
                                posted=detail.get("posted"),
                                description=detail.get("description", ""),
                                salary=card.get("salary"),
                            )
                        finally:
                            await detail_page.close()

                detail_results = await asyncio.gather(*(fetch_detail(card) for card in candidates), return_exceptions=True)
                errors = [result for result in detail_results if isinstance(result, Exception)]
                if errors:
                    raise SourceError("WA detail errors: " + "; ".join(error_text(error) for error in errors[:3]))
                return [result for result in detail_results if isinstance(result, Job)]
            finally:
                await page.close()

        results: list[list[Job] | Exception] = []
        for search in title_searches:
            try:
                results.append(await fetch_search(search))
            except Exception as error:
                results.append(error)
        await context.close()
        await browser.close()
        errors = [result for result in results if isinstance(result, Exception)]
        if errors:
            raise SourceError("Western Australia Playwright errors: " + "; ".join(error_text(error) for error in errors[:3]))
        return [job for result in results for job in result]


class ApsJobsAdapter(Adapter):
    source_id = "aps_jobs"

    def fetch(self, config: dict[str, Any]) -> list[Job]:
        try:
            return asyncio.run(_aps_fetch_async(config))
        except SourceError:
            raise
        except Exception as error:
            raise SourceError(f"APS Jobs Playwright failed: {error}") from error


class StatePortalAdapter(Adapter):
    source_id = "state_portals"

    def fetch(self, config: dict[str, Any]) -> list[Job]:
        jobs: list[Job] = []
        browser_portals: list[dict[str, Any]] = []
        for portal in config.get("portals", []):
            if portal.get("id") != "victoria":
                browser_portals.append(portal)
                continue
            for search in config.get("searches", []):
                url = compact_text(portal.get("search_url")) + "?" + urlencode({portal.get("query_param", "keywords"): search["title"]})
                page = fetch_bytes(url).decode("utf-8", "replace")
                for href, title, company, location, description in parse_victoria_cards(page):
                    detail_url = urljoin(portal["search_url"], href)
                    detail = fetch_bytes(detail_url).decode("utf-8", "replace")
                    posted = parse_victoria_posted(detail)
                    job = make_job(self.source_id, company, url=detail_url, job_id=detail_url.rsplit("/", 1)[-1], title=title, location=location, posted=posted, description=description)
                    if job:
                        jobs.append(job)
        if browser_portals:
            try:
                jobs.extend(asyncio.run(self._fetch_browser_portals(browser_portals, config)))
            except SourceError:
                raise
            except Exception as error:
                raise SourceError(f"state portal Playwright failed: {error}") from error
        return jobs

    async def _fetch_browser_portals(self, portals: list[dict[str, Any]], config: dict[str, Any]) -> list[Job]:
        browser_settings = config.get("_browser", {}) if isinstance(config.get("_browser"), dict) else {}
        headless, max_concurrency, timeout_ms = _browser_settings({"_browser": browser_settings})
        searches = _unique_title_searches(config.get("searches", []))
        days = int(config.get("_days", 7))
        semaphore = asyncio.Semaphore(max_concurrency)

        async def fetch_portal(portal: dict[str, Any]) -> list[Job]:
            async with semaphore:
                portal_id = portal.get("id", "unknown")
                if portal_id == "south_australia":
                    return await _sa_fetch_async(portal, searches, browser_settings, days)
                if portal_id == "western_australia":
                    return await _wa_fetch_async(portal, searches, browser_settings, days)

                async_playwright = _require_playwright()
                async with async_playwright() as playwright:
                    browser = await playwright.chromium.launch(headless=headless)
                    context = await browser.new_context(locale="en-AU", viewport={"width": 1440, "height": 1200})
                    page = await context.new_page()
                    try:
                        response = await page.goto(portal["search_url"], wait_until="domcontentloaded", timeout=timeout_ms)
                        title = (await page.title()).lower()
                        text = " ".join((await page.locator("body").first.inner_text(timeout=timeout_ms)).split()).lower()
                        if response and response.status >= 400:
                            raise SourceError(f"{portal_id} returned HTTP {response.status}")
                        if "cloudflare" in title or "security verification" in text or "request blocked" in text:
                            raise SourceError(f"{portal_id} is protected by an anti-bot/security page")
                        raise SourceError(f"{portal_id} loaded but has no verified result parser")
                    finally:
                        await context.close()
                        await browser.close()

        results = await asyncio.gather(*(fetch_portal(portal) for portal in portals), return_exceptions=True)
        errors = [result for result in results if isinstance(result, Exception)]
        if errors:
            raise SourceError("state portal Playwright errors: " + "; ".join(error_text(error) for error in errors[:5]))
        return [job for result in results for job in result]


def parse_victoria_cards(page: str) -> Iterable[tuple[str, str, str, str, str]]:
    card_re = re.compile(r'<div class="views-row">\s*<rpl-content class="job-searchResult">(.*?)</rpl-content>\s*</div>', re.S)
    for card in card_re.findall(page):
        match = re.search(r'href="([^"]+)"[^>]*><h3>(.*?)</h3>', card, re.S)
        if not match:
            continue
        title = strip_html(match.group(2))
        company_match = re.search(r'header__title.*?</a>\s*</div>\s*<p[^>]*>(.*?)</p>', card, re.S)
        company = strip_html(company_match.group(1)) if company_match else "Victoria Government"
        location_match = re.search(r'<strong>Location:</strong>.*?<p>(.*?)</p>', card, re.S)
        location = strip_html(location_match.group(1)) if location_match else "VIC"
        description_match = re.search(r'field--name-description.*?</div>\s*</div>', card, re.S)
        description = strip_html(description_match.group(0)) if description_match else ""
        yield match.group(1), title, company, location, description


def parse_victoria_posted(page: str) -> str | None:
    match = re.search(r'<time datetime="([^"]+)"[^>]*>.*?</time>', page, re.S)
    return iso_datetime(match.group(1)) if match else None


ADAPTERS: dict[str, Adapter] = {
    "greenhouse": GreenhouseAdapter(),
    "ashby": AshbyAdapter(),
    "lever": LeverAdapter(),
    "workday": WorkdayAdapter(),
    "smartrecruiters": SmartRecruitersAdapter(),
    "aps_jobs": ApsJobsAdapter(),
    "state_portals": StatePortalAdapter(),
}


def load_yaml(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise SystemExit("PyYAML is required. Install requirements-sources.txt in the project environment.")
    with path.open(encoding="utf-8") as handle:
        value = yaml.safe_load(handle) or {}
    if not isinstance(value, dict):
        raise ValueError(f"expected a YAML mapping in {path}")
    return value


def search_terms(searches: list[dict[str, Any]]) -> list[tuple[str, str, set[str]]]:
    result = []
    for search in searches:
        title = compact_text(search.get("title"))
        location = compact_text(search.get("location"))
        tokens = {token.lower() for token in re.findall(r"[a-z0-9]+", title.lower()) if token not in STOPWORDS}
        if title and location and tokens:
            result.append((title, location, tokens))
    return result


def matches_search(job: Job, searches: list[tuple[str, str, set[str]]]) -> bool:
    title = job.position.lower()
    location = job.location.lower()
    for _, requested_location, tokens in searches:
        if tokens.issubset(set(re.findall(r"[a-z0-9]+", title))) and requested_location.lower() in location:
            return True
    return False


def within_window(job: Job, now: datetime, days: int) -> bool:
    posted = parse_datetime(job.posted_at)
    return bool(posted and now - timedelta(days=days) <= posted <= now + timedelta(minutes=5))


def dedupe(jobs: Iterable[Job]) -> list[Job]:
    seen: set[tuple[str, str, str, str]] = set()
    result: list[Job] = []
    for job in jobs:
        key = (job.job_url, job.company.casefold(), job.position.casefold(), job.location.casefold())
        if key in seen:
            continue
        seen.add(key)
        result.append(job)
    return result


def run(args: argparse.Namespace) -> int:
    search_config = load_yaml(args.search_config)
    source_config = load_yaml(args.source_config)
    searches = search_terms(search_config.get("searches", []))
    enabled = source_config.get("sources", {})
    selected = args.sources or list(enabled)
    now = datetime.now(UTC)
    all_jobs: list[Job] = []
    summary: dict[str, Any] = {"days": args.days, "sources": {}, "jobs": []}

    for source_id in selected:
        source = enabled.get(source_id)
        if not source:
            summary["sources"][source_id] = {"status": "missing_config"}
            continue
        if not source.get("enabled", False):
            summary["sources"][source_id] = {"status": "disabled"}
            continue
        adapter = ADAPTERS.get(source_id)
        if not adapter:
            summary["sources"][source_id] = {"status": "unsupported"}
            continue
        try:
            adapter_config = dict(source)
            adapter_config["_browser"] = source_config.get("browser", {})
            adapter_config["_days"] = args.days
            if source_id == "state_portals":
                adapter_config["searches"] = search_config.get("searches", [])
                jobs = adapter.fetch(adapter_config)
            elif source_id == "aps_jobs":
                adapter_config["searches"] = search_config.get("searches", [])
                jobs = adapter.fetch(adapter_config)
            else:
                jobs = adapter.fetch(adapter_config)
            recent = [job for job in jobs if within_window(job, now, args.days)]
            matched = [job for job in recent if matches_search(job, searches)]
            summary["sources"][source_id] = {"status": "ok", "fetched": len(jobs), "recent": len(recent), "keyword_location_matches": len(matched)}
            all_jobs.extend(matched)
        except SourceError as error:
            summary["sources"][source_id] = {"status": "error", "error": str(error)}

    for job in dedupe(all_jobs):
        payload = asdict(job)
        payload["keyword_match"] = True
        payload["fresh_within_days"] = True
        summary["jobs"].append(payload)
    summary["total_jobs"] = len(summary["jobs"])
    json.dump(summary, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if all(item.get("status") in {"ok", "disabled"} for item in summary["sources"].values()) else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--search-config", type=Path, default=DEFAULT_SEARCH_CONFIG)
    parser.add_argument("--source-config", type=Path, default=DEFAULT_SOURCE_CONFIG)
    parser.add_argument("--sources", nargs="+", choices=sorted(ADAPTERS))
    parser.add_argument("--days", type=int, default=7, help="verification window; production discovery remains 24 hours")
    return parser


if __name__ == "__main__":
    raise SystemExit(run(build_parser().parse_args()))
