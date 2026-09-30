#!/usr/bin/env python3
"""Validate and search the local career evidence vault."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import socket
import socketserver
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence


FRONTMATTER_DELIMITER = "---"
EXCLUDED_DIRECTORIES = {"00 System", "07 Applications", "99 Archive", "Templates"}
EXCLUDED_TYPES = {"index", "system"}
EXCLUDED_SECTION_HEADINGS = {"related notes"}
REQUIRED_NOTE_TYPES = {
    "profile": "verified profile note",
    "preferences": "verified target-role preferences note",
    "evidence": "verified evidence note",
}
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
FRONTMATTER_PATTERN = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):(?:\s*(.*))?$")
DEFAULT_SEMANTIC_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_EMBEDDING_INDEX_PATH = "models/vault-embeddings"
DEFAULT_EVIDENCE_SOCKET = ".state/vault-evidence.sock"
DEFAULT_EVIDENCE_REQUEST_DIR = ".state/vault-evidence-requests"
EMBEDDING_INDEX_SCHEMA_VERSION = 1
DEFAULT_KEYWORD_WEIGHT = 0.4
DEFAULT_SEMANTIC_WEIGHT = 0.6
DEFAULT_SEMANTIC_MIN_SCORE = 0.20
DEFAULT_COMPACT_TEXT_LIMIT = 600
STOP_WORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in",
    "is", "it", "of", "on", "or", "that", "the", "to", "with", "you", "your",
})


@dataclass(frozen=True)
class Section:
    heading: str
    text: str


@dataclass(frozen=True)
class VaultNote:
    path: Path
    note_type: str
    status: str
    sources: tuple[str, ...]
    last_verified: str
    skills: tuple[str, ...]
    sections: tuple[Section, ...]


@dataclass(frozen=True)
class EvidenceCandidate:
    """One eligible vault section that can be returned as retrieval evidence."""

    note: VaultNote
    section: Section
    section_index: int


class SemanticSearchUnavailable(RuntimeError):
    """Raised when a requested local embedding model cannot be loaded."""


def load_semantic_model(
    model_name: str,
    model_cache: Path,
    allow_model_download: bool,
) -> Any:
    try:
        from embedding_runtime import load_embedding_model
    except ImportError as error:
        raise SemanticSearchUnavailable(
            "Local semantic search requires the local transformer runtime. "
            "Install requirements-semantic.txt, then retry."
        ) from error

    try:
        return load_embedding_model(
            model_name,
            model_cache,
            allow_model_download,
        )
    except Exception as error:  # The library emits several model/cache exception types.
        download_hint = " Re-run with --allow-model-download to download the model only."
        raise SemanticSearchUnavailable(
            f"Could not load local semantic model '{model_name}'.{download_hint}"
        ) from error


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_vault_path() -> Path:
    return project_root() / "career-vault"


def default_model_cache_path() -> Path:
    return project_root() / "models" / "sentence-transformers"


def default_embedding_index_path() -> Path:
    return project_root() / DEFAULT_EMBEDDING_INDEX_PATH


def default_evidence_socket_path() -> Path:
    return project_root() / DEFAULT_EVIDENCE_SOCKET


def default_evidence_request_dir() -> Path:
    return project_root() / DEFAULT_EVIDENCE_REQUEST_DIR


def normalize_text(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


def clean_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def parse_frontmatter(text: str) -> tuple[dict[str, str | list[str]], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_DELIMITER:
        raise ValueError("missing opening frontmatter delimiter")

    try:
        closing_index = next(
            index
            for index, line in enumerate(lines[1:], start=1)
            if line.strip() == FRONTMATTER_DELIMITER
        )
    except StopIteration as error:
        raise ValueError("missing closing frontmatter delimiter") from error

    metadata: dict[str, str | list[str]] = {}
    active_list: list[str] | None = None
    for raw_line in lines[1:closing_index]:
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("- "):
            if active_list is None:
                raise ValueError("list item without a frontmatter key")
            active_list.append(clean_value(line[2:]))
            continue

        match = FRONTMATTER_PATTERN.match(line)
        if match is None:
            raise ValueError(f"unsupported frontmatter line: {raw_line}")

        key, raw_value = match.groups()
        value = (raw_value or "").strip()
        if value == "":
            active_list = []
            metadata[key] = active_list
        elif value == "[]":
            active_list = []
            metadata[key] = active_list
        else:
            active_list = None
            metadata[key] = clean_value(value)

    return metadata, "\n".join(lines[closing_index + 1:])


def parse_sections(body: str) -> tuple[Section, ...]:
    sections: list[Section] = []
    heading = "Document"
    content: list[str] = []

    for line in body.splitlines():
        match = HEADING_PATTERN.match(line)
        if match:
            text = "\n".join(content).strip()
            if text:
                sections.append(Section(heading=heading, text=text))
            heading = match.group(2)
            content = []
        else:
            content.append(line)

    text = "\n".join(content).strip()
    if text:
        sections.append(Section(heading=heading, text=text))
    return tuple(sections)


def list_value(metadata: dict[str, str | list[str]], key: str) -> tuple[str, ...]:
    value = metadata.get(key, [])
    if isinstance(value, list):
        return tuple(item for item in value if item.strip())
    return (value,) if value.strip() else ()


def is_excluded_path(path: Path) -> bool:
    return (
        path.name == "AGENTS.md"
        or any(part in EXCLUDED_DIRECTORIES for part in path.parts)
        or path.stem.endswith("Index")
    )


def parse_note(path: Path, vault_path: Path) -> VaultNote:
    metadata, body = parse_frontmatter(path.read_text(encoding="utf-8"))
    return VaultNote(
        path=path.relative_to(vault_path),
        note_type=str(metadata.get("type", "")).strip(),
        status=str(metadata.get("status", "")).strip(),
        sources=list_value(metadata, "source"),
        last_verified=str(metadata.get("last_verified", "")).strip(),
        skills=list_value(metadata, "skills"),
        sections=parse_sections(body),
    )


def scan_vault(vault_path: Path) -> tuple[list[VaultNote], list[str]]:
    notes: list[VaultNote] = []
    errors: list[str] = []
    for path in sorted(vault_path.rglob("*.md")):
        relative_path = path.relative_to(vault_path)
        if is_excluded_path(relative_path):
            continue
        try:
            notes.append(parse_note(path, vault_path))
        except ValueError as error:
            errors.append(f"{relative_path.as_posix()}: {error}")
    return notes, errors


def is_eligible(note: VaultNote) -> bool:
    return (
        note.status == "verified"
        and note.note_type not in EXCLUDED_TYPES
        and bool(note.sources)
        and note.last_verified not in {"", "null", "None"}
    )


def eligible_notes(notes: Iterable[VaultNote]) -> list[VaultNote]:
    return [note for note in notes if is_eligible(note)]


def validation_errors(notes: Iterable[VaultNote], parse_errors: Iterable[str]) -> list[str]:
    eligible = eligible_notes(notes)
    errors = [
        f"invalid vault note: {parse_error}"
        for parse_error in parse_errors
    ]
    available_types = {note.note_type for note in eligible}
    for note_type, description in REQUIRED_NOTE_TYPES.items():
        if note_type not in available_types:
            errors.append(f"missing {description}")
    return errors


def contains_term(text: str, term: str) -> bool:
    normalized_text = f" {normalize_text(text)} "
    normalized_term = normalize_text(term)
    return bool(normalized_term) and f" {normalized_term} " in normalized_text


def lexical_tokens(value: str) -> set[str]:
    """Return meaningful lexical tokens without translating or expanding them."""

    return {
        token
        for token in normalize_text(value).split()
        if token not in STOP_WORDS
    }


def primary_section_index(note: VaultNote) -> int:
    for index, section in enumerate(note.sections):
        if normalize_text(section.heading) in {"claim", "evidence"}:
            return index
    return 0


def candidate_document(candidate: EvidenceCandidate) -> str:
    """Build the local-only text sent to the embedding model for one section."""

    return "\n".join(
        part
        for part in (
            f"Title: {candidate.note.path.stem}",
            f"Skills: {', '.join(candidate.note.skills)}" if candidate.note.skills else "",
            f"Section: {candidate.section.heading}",
            candidate.section.text,
        )
        if part
    )


def build_candidates(notes: Iterable[VaultNote]) -> list[EvidenceCandidate]:
    return [
        EvidenceCandidate(note=note, section=section, section_index=index)
        for note in eligible_notes(notes)
        for index, section in enumerate(note.sections)
        if normalize_text(section.heading) not in EXCLUDED_SECTION_HEADINGS
    ]


def vault_fingerprint(vault_path: Path) -> str:
    """Return a content fingerprint for the retrieval-eligible Markdown corpus."""

    digest = hashlib.sha256()
    for path in sorted(vault_path.rglob("*.md")):
        relative_path = path.relative_to(vault_path)
        if is_excluded_path(relative_path):
            continue
        digest.update(relative_path.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def candidate_keys(candidates: Sequence[EvidenceCandidate]) -> list[dict[str, object]]:
    return [
        {
            "path": candidate.note.path.as_posix(),
            "section_index": candidate.section_index,
            "heading": candidate.section.heading,
        }
        for candidate in candidates
    ]


def keyword_score(
    candidate: EvidenceCandidate,
    requirement: str,
    terms: Iterable[str],
) -> tuple[float, list[str]]:
    """Score literal JD terms without using a synonym list or fuzzy expansion.

    The full requirement is a semantic query and can score lexically only as an
    exact phrase. Token overlap is reserved for explicit `--term` values supplied
    from the JD, preventing generic requirement language such as "source
    material" from polluting keyword results. A multi-word literal term needs at
    least two matching meaningful tokens; a single-token term can match literally.
    Keyword retrieval never establishes evidence fulfilment.
    """

    title = candidate.note.path.stem
    matched_terms: list[str] = []
    score = 0.0

    configured_terms = [(requirement.strip(), False)] + [
        (term.strip(), True) for term in terms if term.strip()
    ]
    for term, allow_token_overlap in dict.fromkeys(configured_terms):
        term_score = 0.0
        normalized_term = normalize_text(term)
        if not normalized_term:
            continue

        if candidate.section_index == primary_section_index(candidate.note):
            if any(normalize_text(skill) == normalized_term for skill in candidate.note.skills):
                term_score = max(term_score, 1.0)
            if contains_term(title, term):
                term_score = max(term_score, 0.9)
        if contains_term(candidate.section.heading, term):
            term_score = max(term_score, 0.75)
        if contains_term(candidate.section.text, term):
            term_score = max(term_score, 0.65)

        # Treat a hyphenated identifier as an exact literal phrase. Splitting it
        # would turn e.g. "application-only-claim" into generic partial hits.
        query_tokens = (
            lexical_tokens(term)
            if allow_token_overlap and "-" not in term
            else set()
        )
        section_tokens = lexical_tokens(
            " ".join((title, " ".join(candidate.note.skills), candidate.section.heading, candidate.section.text))
        )
        if query_tokens:
            overlapping_tokens = query_tokens & section_tokens
            if len(query_tokens) == 1 and overlapping_tokens:
                term_score = max(term_score, 0.45)
            elif len(overlapping_tokens) >= 2:
                term_score = max(term_score, 0.45 * len(overlapping_tokens) / len(query_tokens))

        if term_score > 0:
            matched_terms.append(term)
            score = max(score, term_score)

    return score, matched_terms


def local_semantic_scores(
    requirement: str,
    candidates: Sequence[EvidenceCandidate],
    model_name: str,
    model_cache: Path,
    allow_model_download: bool,
) -> list[float]:
    """Calculate cosine similarity locally; vault text is never sent to an API."""

    model = load_semantic_model(model_name, model_cache, allow_model_download)

    try:
        corpus_embeddings = model.encode_document(
            [candidate_document(candidate) for candidate in candidates],
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        query_embedding = model.encode_query(
            requirement,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        return [float(value) for value in corpus_embeddings @ query_embedding]
    except Exception as error:
        raise SemanticSearchUnavailable(
            f"Local semantic search failed while encoding the eligible vault: {error}"
        ) from error


def validate_weights(keyword_weight: float, semantic_weight: float) -> None:
    if keyword_weight < 0 or semantic_weight < 0:
        raise ValueError("retrieval weights must be non-negative")
    if not math.isclose(keyword_weight + semantic_weight, 1.0, abs_tol=0.000001):
        raise ValueError("--keyword-weight and --semantic-weight must add up to 1")


def search_notes(
    notes: Iterable[VaultNote],
    requirement: str,
    terms: Iterable[str],
    limit: int,
    semantic_scorer: Callable[[str, Sequence[EvidenceCandidate]], Sequence[float]] | None = None,
    semantic_min_score: float = DEFAULT_SEMANTIC_MIN_SCORE,
    keyword_weight: float = DEFAULT_KEYWORD_WEIGHT,
    semantic_weight: float = DEFAULT_SEMANTIC_WEIGHT,
) -> list[dict[str, object]]:
    """Return a hybrid lexical + semantic shortlist of eligible vault sections.

    Retrieval scores decide ordering only. Callers must still inspect the returned
    claim and source before classifying evidence as direct or transferable.
    """

    if semantic_min_score < -1 or semantic_min_score > 1:
        raise ValueError("--semantic-min-score must be between -1 and 1")
    validate_weights(keyword_weight, semantic_weight)

    normalized_requirement = requirement.strip()
    if not normalized_requirement:
        raise ValueError("a non-empty requirement is required")
    literal_terms = tuple(term.strip() for term in terms if term.strip())

    candidates = build_candidates(notes)
    if not candidates:
        return []

    if semantic_scorer is None:
        raise SemanticSearchUnavailable(
            "Hybrid search requires a local semantic scorer; use --semantic-mode off "
            "only for lexical diagnostics."
        )

    semantic_scores = list(semantic_scorer(normalized_requirement, candidates))
    if len(semantic_scores) != len(candidates):
        raise ValueError("semantic scorer returned a score count different from the candidate count")

    matches: list[dict[str, object]] = []

    for candidate, semantic_score in zip(candidates, semantic_scores):
        lexical_score, matched_terms = keyword_score(candidate, normalized_requirement, literal_terms)
        semantic_score = float(semantic_score)
        if lexical_score == 0 and semantic_score < semantic_min_score:
            continue

        methods = []
        if lexical_score > 0:
            methods.append("keyword")
        if semantic_score >= semantic_min_score:
            methods.append("semantic")
        matches.append(
            {
                "path": candidate.note.path.as_posix(),
                "type": candidate.note.note_type,
                "heading": candidate.section.heading,
                "text": candidate.section.text,
                "skills": list(candidate.note.skills),
                "source": list(candidate.note.sources),
                "last_verified": candidate.note.last_verified,
                "matched_terms": matched_terms,
                "keyword_score": round(lexical_score, 4),
                "semantic_score": round(semantic_score, 4),
                "retrieval_methods": methods,
                "hybrid_score": round(
                    keyword_weight * lexical_score + semantic_weight * max(semantic_score, 0.0),
                    4,
                ),
            }
        )

    matches.sort(
        key=lambda item: (-float(item["hybrid_score"]), str(item["path"]), str(item["heading"]))
    )
    return matches[:limit]


def compact_matches(
    matches: Sequence[dict[str, object]],
    text_limit: int = DEFAULT_COMPACT_TEXT_LIMIT,
) -> list[dict[str, object]]:
    """Keep retrieval output small while retaining inspectable source excerpts."""

    compacted: list[dict[str, object]] = []
    for match in matches:
        text = str(match.get("text", ""))
        excerpt = text[:text_limit]
        if len(text) > text_limit:
            excerpt = f"{excerpt}…"
        compacted.append(
            {
                "path": match["path"],
                "type": match["type"],
                "heading": match["heading"],
                "text_excerpt": excerpt,
                "source": match["source"],
                "last_verified": match["last_verified"],
                "matched_terms": match["matched_terms"],
                "keyword_score": match["keyword_score"],
                "semantic_score": match["semantic_score"],
                "retrieval_methods": match["retrieval_methods"],
                "hybrid_score": match["hybrid_score"],
            }
        )
    return compacted


def result_payload(
    requirement: str,
    terms: Sequence[str],
    matches: Sequence[dict[str, object]],
    semantic_mode: str,
    semantic_model: str,
    model_cache: Path,
    semantic_min_score: float,
    keyword_weight: float,
    semantic_weight: float,
) -> dict[str, object]:
    return {
        "requirement": requirement,
        "terms": list(terms),
        "retrieval": {
            "keyword": "exact requirement phrases and supplied literal JD terms",
            "semantic": {
                "mode": semantic_mode,
                "model": semantic_model if semantic_mode == "required" else None,
                "model_cache": model_cache.as_posix() if semantic_mode == "required" else None,
                "minimum_score": semantic_min_score if semantic_mode == "required" else None,
            },
            "weights": {
                "keyword": keyword_weight,
                "semantic": semantic_weight,
            },
        },
        "matches": list(matches),
    }


class EmbeddingIndexService:
    """Serve many searches from one model load and one persisted corpus index."""

    def __init__(
        self,
        vault_path: Path,
        model_name: str,
        model_cache: Path,
        index_path: Path,
        allow_model_download: bool,
    ) -> None:
        try:
            import numpy as np
        except ImportError as error:
            raise SemanticSearchUnavailable(
                "The embedding index requires numpy. Install requirements-semantic.txt, then retry."
            ) from error

        self.np = np
        self.vault_path = vault_path
        self.model_name = model_name
        self.model_cache = model_cache
        self.index_path = index_path
        self.index_path.mkdir(parents=True, exist_ok=True)
        self.notes, self.parse_errors = scan_vault(vault_path)
        self.candidates = build_candidates(self.notes)
        self.fingerprint = vault_fingerprint(vault_path)
        self.model = load_semantic_model(model_name, model_cache, allow_model_download)
        self.embeddings = self._load_or_build_index()
        self.query_cache_path = self.index_path / "query-cache.json"
        self.query_cache = self._load_query_cache()

    @property
    def index_file(self) -> Path:
        return self.index_path / "embeddings.npy"

    @property
    def metadata_file(self) -> Path:
        return self.index_path / "metadata.json"

    def _index_metadata(self) -> dict[str, object]:
        return {
            "schema_version": EMBEDDING_INDEX_SCHEMA_VERSION,
            "model": self.model_name,
            "vault_fingerprint": self.fingerprint,
            "candidate_keys": candidate_keys(self.candidates),
        }

    def _load_or_build_index(self):
        expected = self._index_metadata()
        try:
            metadata = json.loads(self.metadata_file.read_text(encoding="utf-8"))
            embeddings = self.np.load(self.index_file, allow_pickle=False)
            if metadata == expected and embeddings.shape[0] == len(self.candidates):
                return embeddings
        except (OSError, ValueError, json.JSONDecodeError):
            pass

        documents = [candidate_document(candidate) for candidate in self.candidates]
        embeddings = self.model.encode_document(
            documents,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        ).astype("float32")
        self.np.save(self.index_file, embeddings)
        self.metadata_file.write_text(json.dumps(expected, ensure_ascii=False, indent=2), encoding="utf-8")
        return embeddings

    def _load_query_cache(self) -> dict[str, object]:
        try:
            cache = json.loads(self.query_cache_path.read_text(encoding="utf-8"))
            if (
                cache.get("schema_version") == EMBEDDING_INDEX_SCHEMA_VERSION
                and cache.get("model") == self.model_name
                and cache.get("vault_fingerprint") == self.fingerprint
                and isinstance(cache.get("entries"), dict)
            ):
                return cache
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        return {
            "schema_version": EMBEDDING_INDEX_SCHEMA_VERSION,
            "model": self.model_name,
            "vault_fingerprint": self.fingerprint,
            "entries": {},
        }

    def _save_query_cache(self) -> None:
        temporary_path = self.query_cache_path.with_suffix(".tmp")
        temporary_path.write_text(
            json.dumps(self.query_cache, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(temporary_path, self.query_cache_path)

    def _refresh_if_needed(self) -> None:
        """Refresh a long-lived service after the vault changes on disk."""

        current_fingerprint = vault_fingerprint(self.vault_path)
        if current_fingerprint == self.fingerprint:
            return

        self.notes, self.parse_errors = scan_vault(self.vault_path)
        self.candidates = build_candidates(self.notes)
        self.fingerprint = current_fingerprint
        self.embeddings = self._load_or_build_index()
        self.query_cache = self._load_query_cache()

    def _cache_key(
        self,
        requirement: str,
        terms: Sequence[str],
        limit: int,
        compact: bool,
        semantic_min_score: float,
        keyword_weight: float,
        semantic_weight: float,
    ) -> str:
        canonical_terms = sorted(dict.fromkeys(term.strip() for term in terms if term.strip()))
        payload = {
            "model": self.model_name,
            "vault_fingerprint": self.fingerprint,
            "requirement": requirement.strip(),
            "terms": canonical_terms,
            "limit": limit,
            "compact": compact,
            "semantic_min_score": semantic_min_score,
            "keyword_weight": keyword_weight,
            "semantic_weight": semantic_weight,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

    @staticmethod
    def _prepare_request(request: dict[str, object]) -> dict[str, object]:
        requirement = str(request.get("requirement", "")).strip()
        raw_terms = request.get("terms", [])
        if isinstance(raw_terms, str):
            raw_terms = [raw_terms]
        terms = sorted(dict.fromkeys(
            str(term).strip() for term in raw_terms if str(term).strip()
        ))
        limit = int(request.get("limit", 3))
        compact = bool(request.get("compact", True))
        semantic_min_score = float(request.get("semantic_min_score", DEFAULT_SEMANTIC_MIN_SCORE))
        keyword_weight = float(request.get("keyword_weight", DEFAULT_KEYWORD_WEIGHT))
        semantic_weight = float(request.get("semantic_weight", DEFAULT_SEMANTIC_WEIGHT))
        if not requirement:
            raise ValueError("a non-empty requirement is required")
        if limit < 1:
            raise ValueError("--limit must be at least 1")
        return {
            "requirement": requirement,
            "terms": terms,
            "limit": limit,
            "compact": compact,
            "semantic_min_score": semantic_min_score,
            "keyword_weight": keyword_weight,
            "semantic_weight": semantic_weight,
        }

    def _search_prepared_request(
        self,
        prepared: dict[str, object],
        query_embedding: Any,
    ) -> dict[str, object]:
        requirement = str(prepared["requirement"])
        terms = list(prepared["terms"])  # type: ignore[arg-type]
        limit = int(prepared["limit"])
        compact = bool(prepared["compact"])
        semantic_min_score = float(prepared["semantic_min_score"])
        keyword_weight = float(prepared["keyword_weight"])
        semantic_weight = float(prepared["semantic_weight"])
        semantic_scores = self.embeddings @ query_embedding
        matches = search_notes(
            self.notes,
            requirement,
            terms,
            limit,
            semantic_scorer=lambda _query, candidates: semantic_scores[: len(candidates)],
            semantic_min_score=semantic_min_score,
            keyword_weight=keyword_weight,
            semantic_weight=semantic_weight,
        )
        if compact:
            matches = compact_matches(matches)
        return result_payload(
            requirement,
            terms,
            matches,
            "required",
            self.model_name,
            self.model_cache,
            semantic_min_score,
            keyword_weight,
            semantic_weight,
        )

    def search_requests(self, requests: Sequence[dict[str, object]]) -> list[dict[str, object]]:
        """Search many requirements with one model call and one cache write.

        Results are deduplicated by the complete request cache key. Query
        embeddings are deduplicated separately by requirement text, so the
        same requirement with different display limits or literal terms still
        requires only one encoder pass.
        """

        self._refresh_if_needed()
        prepared_requests = [self._prepare_request(request) for request in requests]
        entries = self.query_cache["entries"]
        if not isinstance(entries, dict):
            entries = {}
            self.query_cache["entries"] = entries

        results: list[dict[str, object] | None] = [None] * len(prepared_requests)
        pending: dict[str, list[tuple[int, dict[str, object]]]] = {}
        for index, prepared in enumerate(prepared_requests):
            key = self._cache_key(
                str(prepared["requirement"]),
                list(prepared["terms"]),  # type: ignore[arg-type]
                int(prepared["limit"]),
                bool(prepared["compact"]),
                float(prepared["semantic_min_score"]),
                float(prepared["keyword_weight"]),
                float(prepared["semantic_weight"]),
            )
            cached = entries.get(key)
            if isinstance(cached, dict):
                results[index] = cached
                continue
            pending.setdefault(key, []).append((index, prepared))

        if pending:
            unique_requirements: dict[str, list[tuple[str, dict[str, object]]]] = {}
            for key, grouped_requests in pending.items():
                for _, prepared in grouped_requests:
                    unique_requirements.setdefault(str(prepared["requirement"]), []).append((key, prepared))

            query_texts = list(unique_requirements)
            query_embeddings = self.model.encode_queries(
                query_texts,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            for query_text, query_embedding in zip(query_texts, query_embeddings):
                for key, prepared in unique_requirements[query_text]:
                    result = self._search_prepared_request(prepared, query_embedding)
                    entries[key] = result
                    for index, _ in pending[key]:
                        results[index] = result
            self._save_query_cache()

        return [result for result in results if result is not None]

    def search_request(self, request: dict[str, object]) -> dict[str, object]:
        return self.search_requests([request])[0]


class EvidenceRequestHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        raw_request = self.rfile.readline()
        try:
            request = json.loads(raw_request.decode("utf-8"))
            command = request.get("command")
            if command == "search":
                result = self.server.evidence_service.search_request(request)  # type: ignore[attr-defined]
            elif command == "search_batch":
                raw_requests = request.get("requests", [])
                if not isinstance(raw_requests, list):
                    raise ValueError("search_batch requests must be a list")
                result = {
                    "results": self.server.evidence_service.search_requests(raw_requests)  # type: ignore[attr-defined]
                }
            else:
                raise ValueError("unsupported evidence service command")
            response = {"ok": True, "result": result}
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            response = {"ok": False, "error": str(error)}
        self.wfile.write(json.dumps(response, ensure_ascii=False).encode("utf-8") + b"\n")


class EvidenceUnixServer(socketserver.UnixStreamServer):
    allow_reuse_address = True


def request_evidence_service(socket_path: Path, request: dict[str, object]) -> dict[str, object]:
    if not socket_path.exists():
        raise SemanticSearchUnavailable(f"Evidence service socket does not exist: {socket_path}")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(180)
        client.connect(str(socket_path))
        client.sendall(json.dumps(request, ensure_ascii=False).encode("utf-8") + b"\n")
        client.shutdown(socket.SHUT_WR)
        response = b"".join(iter(lambda: client.recv(65536), b""))
    payload = json.loads(response.decode("utf-8"))
    if not payload.get("ok"):
        raise SemanticSearchUnavailable(str(payload.get("error", "evidence service failed")))
    return payload["result"]


def request_evidence_file_service(request_dir: Path, request: dict[str, object]) -> dict[str, object]:
    ready_path = request_dir / "READY"
    if not ready_path.exists():
        raise SemanticSearchUnavailable(f"Evidence service is not ready: {request_dir}")

    request_id = uuid.uuid4().hex
    request_path = request_dir / f"{request_id}.request.json"
    response_path = request_dir / f"{request_id}.response.json"
    temporary_path = request_dir / f"{request_id}.request.tmp"
    temporary_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary_path, request_path)
    deadline = time.monotonic() + 180
    try:
        while time.monotonic() < deadline:
            if response_path.exists():
                payload = json.loads(response_path.read_text(encoding="utf-8"))
                response_path.unlink(missing_ok=True)
                if not payload.get("ok"):
                    raise SemanticSearchUnavailable(str(payload.get("error", "evidence service failed")))
                return payload["result"]
            time.sleep(0.02)
    finally:
        request_path.unlink(missing_ok=True)
        temporary_path.unlink(missing_ok=True)
    raise SemanticSearchUnavailable(f"Evidence service timed out: {request_dir}")


class EvidenceFileService:
    """Filesystem transport for environments where local sockets are unavailable."""

    def __init__(self, request_dir: Path, evidence_service: EmbeddingIndexService) -> None:
        self.request_dir = request_dir
        self.evidence_service = evidence_service
        self.request_dir.mkdir(parents=True, exist_ok=True)
        (self.request_dir / "READY").write_text("ready\n", encoding="utf-8")

    def serve_forever(self) -> None:
        try:
            while True:
                handled = False
                for request_path in sorted(self.request_dir.glob("*.request.json")):
                    working_path = request_path.with_name(request_path.name.replace(".request.json", ".working.json"))
                    try:
                        request_path.rename(working_path)
                    except FileNotFoundError:
                        continue
                    handled = True
                    try:
                        request = json.loads(working_path.read_text(encoding="utf-8"))
                        command = request.get("command")
                        if command == "search":
                            result = self.evidence_service.search_request(request)
                        elif command == "search_batch":
                            raw_requests = request.get("requests", [])
                            if not isinstance(raw_requests, list):
                                raise ValueError("search_batch requests must be a list")
                            result = {"results": self.evidence_service.search_requests(raw_requests)}
                        else:
                            raise ValueError("unsupported evidence service command")
                        response = {"ok": True, "result": result}
                    except (OSError, TypeError, ValueError, RuntimeError, json.JSONDecodeError) as error:
                        response = {"ok": False, "error": str(error)}
                    response_path = request_path.with_name(request_path.name.replace(".request.json", ".response.json"))
                    response_path.write_text(json.dumps(response, ensure_ascii=False), encoding="utf-8")
                    working_path.unlink(missing_ok=True)
                if not handled:
                    time.sleep(0.02)
        finally:
            (self.request_dir / "READY").unlink(missing_ok=True)
            for path in self.request_dir.glob("*.working.json"):
                path.unlink(missing_ok=True)


def run_serve(
    vault_path: Path,
    socket_path: Path,
    request_dir: Path | None,
    model_name: str,
    model_cache: Path,
    index_path: Path,
    allow_model_download: bool,
    pid_file: Path | None,
) -> int:
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    if socket_path.exists():
        socket_path.unlink()
    if pid_file is not None:
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(str(os.getpid()), encoding="utf-8")
    service = EmbeddingIndexService(
        vault_path,
        model_name,
        model_cache,
        index_path,
        allow_model_download,
    )
    if request_dir is not None:
        file_service = EvidenceFileService(request_dir, service)
        print(
            f"Evidence service ready: {len(service.candidates)} candidates, "
            f"index={index_path}, request_dir={request_dir}",
            flush=True,
        )
        try:
            file_service.serve_forever()
        except KeyboardInterrupt:
            return 0
        finally:
            if pid_file is not None:
                pid_file.unlink(missing_ok=True)
        return 0
    server = EvidenceUnixServer(str(socket_path), EvidenceRequestHandler)
    server.evidence_service = service  # type: ignore[attr-defined]
    try:
        os.chmod(socket_path, 0o600)
    except PermissionError:
        # Some managed sandboxes disallow chmod on Unix sockets; the runner
        # keeps the socket under the private project .state directory.
        pass
    print(
        f"Evidence service ready: {len(service.candidates)} candidates, "
        f"index={index_path}, socket={socket_path}",
        flush=True,
    )
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()
        if socket_path.exists():
            socket_path.unlink()
        if pid_file is not None:
            pid_file.unlink(missing_ok=True)
    return 0


def run_check(vault_path: Path) -> int:
    notes, parse_errors = scan_vault(vault_path)
    errors = validation_errors(notes, parse_errors)
    if errors:
        print("Vault preflight failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"Vault preflight passed: {len(eligible_notes(notes))} eligible notes.")
    return 0


def load_batch_requests(input_path: Path, default_limit: int, compact: bool) -> list[dict[str, object]]:
    raw_text = sys.stdin.read() if str(input_path) == "-" else input_path.read_text(encoding="utf-8")
    payload = json.loads(raw_text)
    if isinstance(payload, dict) and isinstance(payload.get("requests"), list):
        payload = payload["requests"]
    if not isinstance(payload, list):
        raise ValueError("batch input must be a JSON array or an object with a requests array")

    requests: list[dict[str, object]] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("each batch request must be a JSON object")
        request = dict(item)
        request.setdefault("limit", default_limit)
        request.setdefault("compact", compact)
        requests.append(request)
    if not requests:
        raise ValueError("batch input contains no requests")
    return requests


def run_batch_search(
    vault_path: Path,
    input_path: Path,
    default_limit: int,
    compact: bool,
    semantic_model: str,
    model_cache: Path,
    index_path: Path,
    allow_model_download: bool,
    semantic_min_score: float,
    keyword_weight: float,
    semantic_weight: float,
    socket_path: Path | None,
    request_dir: Path | None,
) -> int:
    requests = load_batch_requests(input_path, default_limit, compact)
    for request in requests:
        request.setdefault("semantic_min_score", semantic_min_score)
        request.setdefault("keyword_weight", keyword_weight)
        request.setdefault("semantic_weight", semantic_weight)

    if request_dir is not None:
        result = request_evidence_file_service(
            request_dir,
            {"command": "search_batch", "requests": requests},
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if socket_path is not None:
        result = request_evidence_service(
            socket_path,
            {"command": "search_batch", "requests": requests},
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    service = EmbeddingIndexService(
        vault_path,
        semantic_model,
        model_cache,
        index_path,
        allow_model_download,
    )
    print(
        json.dumps(
            {"results": service.search_requests(requests)},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def run_search(
    vault_path: Path,
    requirement: str,
    terms: list[str],
    limit: int,
    semantic_mode: str,
    semantic_model: str,
    model_cache: Path,
    allow_model_download: bool,
    semantic_min_score: float,
    keyword_weight: float,
    semantic_weight: float,
    compact: bool,
    socket_path: Path | None,
    request_dir: Path | None,
) -> int:
    if semantic_mode != "off" and request_dir is not None:
        result = request_evidence_file_service(
            request_dir,
            {
                "command": "search",
                "requirement": requirement,
                "terms": terms,
                "limit": limit,
                "compact": compact,
                "semantic_min_score": semantic_min_score,
                "keyword_weight": keyword_weight,
                "semantic_weight": semantic_weight,
            },
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if semantic_mode != "off" and socket_path is not None:
        result = request_evidence_service(
            socket_path,
            {
                "command": "search",
                "requirement": requirement,
                "terms": terms,
                "limit": limit,
                "compact": compact,
                "semantic_min_score": semantic_min_score,
                "keyword_weight": keyword_weight,
                "semantic_weight": semantic_weight,
            },
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    notes, _ = scan_vault(vault_path)
    semantic_scorer: Callable[[str, Sequence[EvidenceCandidate]], Sequence[float]] | None
    if semantic_mode == "off":
        semantic_scorer = lambda _requirement, candidates: [0.0] * len(candidates)
        semantic_min_score = 1.0
        semantic_weight = 0.0
        keyword_weight = 1.0
    else:
        semantic_scorer = lambda query, candidates: local_semantic_scores(
            query,
            candidates,
            model_name=semantic_model,
            model_cache=model_cache,
            allow_model_download=allow_model_download,
        )

    matches = search_notes(
        notes,
        requirement,
        terms,
        limit,
        semantic_scorer=semantic_scorer,
        semantic_min_score=semantic_min_score,
        keyword_weight=keyword_weight,
        semantic_weight=semantic_weight,
    )
    if compact:
        matches = compact_matches(matches)
    result = result_payload(
        requirement,
        terms,
        matches,
        semantic_mode,
        semantic_model,
        model_cache,
        semantic_min_score,
        keyword_weight,
        semantic_weight,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser("check", help="validate vault readiness")
    check_parser.add_argument("--vault", type=Path, default=default_vault_path())

    serve_parser = subparsers.add_parser(
        "serve",
        help="load the local model once and serve cached vault searches",
    )
    serve_parser.add_argument("--vault", type=Path, default=default_vault_path())
    serve_parser.add_argument("--socket", type=Path, default=default_evidence_socket_path())
    serve_parser.add_argument("--request-dir", type=Path, default=None)
    serve_parser.add_argument("--semantic-model", default=DEFAULT_SEMANTIC_MODEL)
    serve_parser.add_argument("--model-cache", type=Path, default=default_model_cache_path())
    serve_parser.add_argument("--index-path", type=Path, default=default_embedding_index_path())
    serve_parser.add_argument("--allow-model-download", action="store_true")
    serve_parser.add_argument(
        "--pid-file",
        type=Path,
        default=None,
        help="write the long-lived service PID here",
    )

    search_parser = subparsers.add_parser("search", help="search eligible vault evidence")
    search_parser.add_argument("--vault", type=Path, default=default_vault_path())
    search_parser.add_argument(
        "--requirement",
        required=True,
        help="full JD requirement in its original context; this is the semantic query",
    )
    search_parser.add_argument(
        "--term",
        action="append",
        default=[],
        help="literal JD tool, acronym, or phrase to boost in keyword retrieval",
    )
    search_parser.add_argument("--limit", type=int, default=8)
    search_parser.add_argument(
        "--compact",
        action="store_true",
        help="return top matches with short excerpts instead of full evidence text",
    )
    search_parser.add_argument(
        "--socket",
        type=Path,
        default=(Path(os.environ["VAULT_EVIDENCE_SOCKET"])
                 if os.environ.get("VAULT_EVIDENCE_SOCKET") else None),
        help="use a persistent local evidence service for model/index reuse",
    )
    search_parser.add_argument(
        "--request-dir",
        type=Path,
        default=(Path(os.environ["VAULT_EVIDENCE_REQUEST_DIR"])
                 if os.environ.get("VAULT_EVIDENCE_REQUEST_DIR") else None),
        help="use a filesystem-backed evidence service for model/index reuse",
    )
    search_parser.add_argument(
        "--semantic-mode",
        choices=("required", "off"),
        default="required",
        help="use local embeddings (default); 'off' is only for lexical diagnostics",
    )
    search_parser.add_argument(
        "--semantic-model",
        default=DEFAULT_SEMANTIC_MODEL,
        help="local BERT-compatible embedding model name or path",
    )
    search_parser.add_argument(
        "--allow-model-download",
        action="store_true",
        help="allow first-run download of the model; vault text remains local",
    )
    search_parser.add_argument(
        "--model-cache",
        type=Path,
        default=default_model_cache_path(),
        help="workspace-local directory containing the embedding model",
    )
    search_parser.add_argument(
        "--semantic-min-score",
        type=float,
        default=DEFAULT_SEMANTIC_MIN_SCORE,
        help="minimum cosine similarity for a semantic-only candidate (-1 to 1)",
    )
    search_parser.add_argument(
        "--keyword-weight",
        type=float,
        default=DEFAULT_KEYWORD_WEIGHT,
        help="hybrid score weight for literal matches",
    )
    search_parser.add_argument(
        "--semantic-weight",
        type=float,
        default=DEFAULT_SEMANTIC_WEIGHT,
        help="hybrid score weight for local semantic similarity",
    )

    batch_parser = subparsers.add_parser(
        "batch-search",
        help="search many requirements through one persistent service request",
    )
    batch_parser.add_argument(
        "--input",
        type=Path,
        default=Path("-"),
        help="JSON array or object containing requests; '-' reads stdin",
    )
    batch_parser.add_argument("--limit", type=int, default=3)
    batch_parser.add_argument("--compact", action="store_true")
    batch_parser.add_argument(
        "--socket",
        type=Path,
        default=(Path(os.environ["VAULT_EVIDENCE_SOCKET"])
                 if os.environ.get("VAULT_EVIDENCE_SOCKET") else None),
    )
    batch_parser.add_argument(
        "--request-dir",
        type=Path,
        default=(Path(os.environ["VAULT_EVIDENCE_REQUEST_DIR"])
                 if os.environ.get("VAULT_EVIDENCE_REQUEST_DIR") else None),
    )
    batch_parser.add_argument("--vault", type=Path, default=default_vault_path())
    batch_parser.add_argument("--semantic-model", default=DEFAULT_SEMANTIC_MODEL)
    batch_parser.add_argument("--model-cache", type=Path, default=default_model_cache_path())
    batch_parser.add_argument("--index-path", type=Path, default=default_embedding_index_path())
    batch_parser.add_argument("--allow-model-download", action="store_true")
    batch_parser.add_argument("--semantic-min-score", type=float, default=DEFAULT_SEMANTIC_MIN_SCORE)
    batch_parser.add_argument("--keyword-weight", type=float, default=DEFAULT_KEYWORD_WEIGHT)
    batch_parser.add_argument("--semantic-weight", type=float, default=DEFAULT_SEMANTIC_WEIGHT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    if args.command == "check":
        return run_check(args.vault)
    if args.command == "serve":
        return run_serve(
            args.vault,
            args.socket,
            args.request_dir,
            args.semantic_model,
            args.model_cache,
            args.index_path,
            args.allow_model_download,
            args.pid_file,
        )
    if args.command == "search":
        if args.limit < 1:
            raise ValueError("--limit must be at least 1")
        return run_search(
            args.vault,
            args.requirement,
            args.term,
            args.limit,
            args.semantic_mode,
            args.semantic_model,
            args.model_cache,
            args.allow_model_download,
            args.semantic_min_score,
            args.keyword_weight,
            args.semantic_weight,
            args.compact,
            args.socket,
            args.request_dir,
        )
    if args.command == "batch-search":
        if args.limit < 1:
            raise ValueError("--limit must be at least 1")
        return run_batch_search(
            args.vault,
            args.input,
            args.limit,
            args.compact,
            args.semantic_model,
            args.model_cache,
            args.index_path,
            args.allow_model_download,
            args.semantic_min_score,
            args.keyword_weight,
            args.semantic_weight,
            args.socket,
            args.request_dir,
        )
    raise ValueError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"vault_evidence: {error}", file=sys.stderr)
        raise SystemExit(1) from error
