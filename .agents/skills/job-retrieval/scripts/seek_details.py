#!/usr/bin/env python3
"""Read one known Seek job URL; no search, authentication or paid actor calls."""
from html.parser import HTMLParser
import json
import re
import sys
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, Request

MAX_BYTES = 2_000_000


def validate_url(url):
    parts = urlsplit(url)
    if parts.scheme != 'https' or parts.hostname not in {'www.seek.com.au', 'seek.com.au'} or parts.port not in (None, 443) or parts.username or parts.password or not re.fullmatch(r'/job/\d+/?', parts.path):
        raise ValueError('Only a known HTTPS Seek job URL is allowed')
    return url


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        if urlsplit(newurl).path.rstrip('/') != urlsplit(req.full_url).path.rstrip('/'):
            raise ValueError('Seek redirected to a different job')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class JobPostingParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.active = False; self.parts = []; self.scripts = []
    def handle_starttag(self, tag, attrs):
        if tag == 'script' and dict(attrs).get('type') == 'application/ld+json':
            self.active = True; self.parts = []
    def handle_data(self, text):
        if self.active: self.parts.append(text)
    def handle_endtag(self, tag):
        if tag == 'script' and self.active:
            self.scripts.append(''.join(self.parts)); self.active = False


def extract(html, url):
    parser = JobPostingParser(); parser.feed(html)
    def postings(value):
        if isinstance(value, list):
            for item in value: yield from postings(item)
        elif isinstance(value, dict):
            types = value.get('@type', [])
            if types == 'JobPosting' or isinstance(types, list) and 'JobPosting' in types:
                yield value
            yield from postings(value.get('@graph', []))
    for script in parser.scripts:
        try: data = json.loads(script)
        except ValueError: continue
        for posting in postings(data):
            identity = posting.get('url') or posting.get('mainEntityOfPage')
            if isinstance(identity, dict): identity = identity.get('@id')
            if identity and urlsplit(str(identity)).path.rstrip('/') != urlsplit(url).path.rstrip('/'):
                continue
            text = posting.get('description')
            if isinstance(text, str) and text.strip():
                return {'description_html': text, 'description_source_url': url}
    raise ValueError('Seek page has no verifiable JobPosting description')


def fetch(url):
    validate_url(url)
    try:
        with build_opener(SafeRedirect()).open(Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=15) as response:
            validate_url(response.url)
            if urlsplit(response.url).path.rstrip('/') != urlsplit(url).path.rstrip('/'):
                raise ValueError('Seek response belongs to a different job')
            body = response.read(MAX_BYTES+1)
            if len(body) > MAX_BYTES: raise ValueError('Seek page exceeded size limit')
            return {'structuredContent': {'url': url, **extract(body.decode('utf-8'), url)}}
    except Exception as error:
        return {'structuredContent': {'url': url, 'error': 'Description unavailable: '+type(error).__name__}}

if __name__ == '__main__':
    print(json.dumps(fetch(json.load(sys.stdin)['url'])))
