#!/usr/bin/env python3
"""Validate the local vault and retrieve eligible evidence from Chroma Cloud."""

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
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_CHROMA_COLLECTION = "career-vault-evidence-openai"
DEFAULT_EVIDENCE_SOCKET = ".state/vault-evidence.sock"
CHROMA_INDEX_SCHEMA_VERSION = 3
EVIDENCE_SERVICE_VERSION = "openai-chroma-v2"
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
    """Raised when hybrid retrieval cannot embed text or reach its cloud services."""


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_vault_path() -> Path:
    return project_root() / "career-vault"


def default_embedding_model() -> str:
    return os.environ.get("OPENAI_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)


class OpenAIEmbeddingModel:
    """Create embeddings with OpenAI's embeddings API."""

    batch_size = 32

    def __init__(self, model_name: str) -> None:
        if model_name != DEFAULT_EMBEDDING_MODEL:
            raise SemanticSearchUnavailable("Only text-embedding-3-small is permitted for hybrid retrieval.")
        load_service_environment()
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise SemanticSearchUnavailable(
                "OpenAI credentials are missing. Set OPENAI_API_KEY in the environment or .env."
            )
        try:
            from openai import OpenAI
        except ImportError as error:
            raise SemanticSearchUnavailable(
                "OpenAI embeddings require openai. Install requirements-semantic.txt, then retry."
            ) from error
        self.model_name = model_name
        self.client = OpenAI(api_key=api_key, max_retries=0, timeout=60)
        self.usage: list[dict[str, object]] = []

    def _encode(self, texts: Sequence[str]) -> list[list[float]]:
        embeddings: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = list(texts[start : start + self.batch_size])
            started = time.monotonic()
            try:
                response = self.client.embeddings.create(
                    model=self.model_name,
                    input=batch,
                    encoding_format="float",
                )
            except Exception as error:
                raise SemanticSearchUnavailable(
                    f"OpenAI embeddings request failed ({type(error).__name__}); billable usage unknown."
                ) from error
            usage = getattr(response, "usage", None)
            prompt_tokens = getattr(usage, "prompt_tokens", None)
            total_tokens = getattr(usage, "total_tokens", None)
            if (type(prompt_tokens) is not int or type(total_tokens) is not int
                    or prompt_tokens < 0 or total_tokens < prompt_tokens):
                raise SemanticSearchUnavailable("OpenAI embedding usage is unavailable or invalid.")
            self.usage.append({"model": self.model_name, "prompt_tokens": prompt_tokens,
                               "total_tokens": total_tokens,
                               "elapsed_seconds": time.monotonic() - started,
                               "cost_estimate_usd": None})
            rows = sorted(response.data, key=lambda item: item.index)
            if [row.index for row in rows] != list(range(len(batch))):
                raise SemanticSearchUnavailable("OpenAI returned an incomplete embedding batch.")
            if any(not row.embedding or any(not math.isfinite(value) for value in row.embedding) for row in rows):
                raise SemanticSearchUnavailable("OpenAI returned invalid embedding vectors.")
            embeddings.extend(row.embedding for row in rows)
        return embeddings

    def encode_document(self, documents: Sequence[str]) -> list[list[float]]:
        return self._encode(documents)

    def encode_queries(self, queries: Sequence[str]) -> list[list[float]]:
        return self._encode(queries)


def load_embedding_model(model_name: str) -> OpenAIEmbeddingModel:
    try:
        return OpenAIEmbeddingModel(model_name)
    except SemanticSearchUnavailable:
        raise
    except Exception as error:
        raise SemanticSearchUnavailable(
            f"Could not initialize OpenAI embeddings ({type(error).__name__})."
        ) from error


def default_hybrid_search() -> bool:
    config_path = project_root() / "config" / "search_targets.yaml"
    try:
        import yaml
    except ImportError as error:
        raise ValueError("Reading hybrid_search requires PyYAML; install requirements.txt.") from error
    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as error:
        raise ValueError(f"Could not read search configuration: {error}") from error
    value = config.get("hybrid_search", True)
    if not isinstance(value, bool):
        raise ValueError("config/search_targets.yaml must set hybrid_search to true or false")
    return value


def parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise argparse.ArgumentTypeError("expected true or false")


def default_evidence_socket_path() -> Path:
    return project_root() / DEFAULT_EVIDENCE_SOCKET


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
    """Build the eligible section text sent to OpenAI for embedding."""

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


def vault_fingerprint(candidates: Iterable[EvidenceCandidate]) -> str:
    """Fingerprint only the candidate text and citation metadata sent to Chroma."""

    digest = hashlib.sha256()
    for candidate in candidates:
        digest.update(candidate_id(candidate).encode("ascii"))
        digest.update(b"\0")
        digest.update(candidate_document(candidate).encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def local_vault_fingerprint(vault_path: Path) -> str:
    """Detect local note edits without uploading a hash of ineligible notes."""

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


def candidate_id(candidate: EvidenceCandidate) -> str:
    key = {
        "path": candidate.note.path.as_posix(),
        "section_index": candidate.section_index,
        "heading": candidate.section.heading,
    }
    return hashlib.sha256(json.dumps(key, sort_keys=True).encode("utf-8")).hexdigest()


def load_service_environment() -> None:
    """Read only Chroma and OpenAI API keys from .env without executing it."""

    keys = {"CHROMA_API_KEY", "CHROMA_TENANT", "CHROMA_DATABASE", "OPENAI_API_KEY"}
    env_file = project_root() / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[7:].lstrip()
        name, separator, value = line.partition("=")
        if not separator or name.strip() not in keys or os.environ.get(name.strip()):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[name.strip()] = value


def create_chroma_client() -> Any:
    load_service_environment()
    if not os.environ.get("CHROMA_API_KEY"):
        raise SemanticSearchUnavailable(
            "Chroma Cloud credentials are missing. Set CHROMA_API_KEY in the environment or .env."
        )
    try:
        import chromadb
    except ImportError as error:
        raise SemanticSearchUnavailable(
            "Chroma search requires chromadb. Install requirements-semantic.txt, then retry."
        ) from error
    try:
        return chromadb.CloudClient(
            api_key=os.environ["CHROMA_API_KEY"],
            tenant=os.environ.get("CHROMA_TENANT") or None,
            database=os.environ.get("CHROMA_DATABASE") or None,
        )
    except Exception as error:
        raise SemanticSearchUnavailable(
            f"Could not connect to Chroma Cloud ({type(error).__name__})."
        ) from error


def get_chroma_collection(client: Any, create: bool = False) -> Any:
    try:
        if create:
            return client.get_or_create_collection(
                name=DEFAULT_CHROMA_COLLECTION,
                embedding_function=None,
            )
        return client.get_collection(
            name=DEFAULT_CHROMA_COLLECTION,
            embedding_function=None,
        )
    except Exception as error:
        operation = "create or open" if create else "open"
        raise SemanticSearchUnavailable(
            f"Could not {operation} Chroma collection '{DEFAULT_CHROMA_COLLECTION}' "
            f"({type(error).__name__})."
        ) from error


def chroma_index_metadata(model_name: str, fingerprint: str, count: int) -> dict[str, object]:
    return {
        "schema_version": CHROMA_INDEX_SCHEMA_VERSION,
        "embedding_model": model_name,
        "vault_fingerprint": fingerprint,
        "candidate_count": count,
        "vector_metric": "normalized_l2",
    }


def validate_chroma_index(
    collection: Any,
    model_name: str,
    fingerprint: str,
    candidate_count: int,
) -> None:
    metadata = collection.metadata or {}
    expected = chroma_index_metadata(model_name, fingerprint, candidate_count)
    if any(metadata.get(key) != value for key, value in expected.items()):
        raise SemanticSearchUnavailable(
            "Chroma Cloud does not contain a current index for this vault and model. "
            "Run ./.venv/bin/python scripts/index_vault_chroma.py first."
        )
    try:
        count = collection.count()
    except Exception as error:
        raise SemanticSearchUnavailable(
            f"Could not read the Chroma Cloud index ({type(error).__name__})."
        ) from error
    if count != candidate_count:
        raise SemanticSearchUnavailable(
            "The Chroma Cloud index count does not match the eligible vault sections. "
            "Run ./.venv/bin/python scripts/index_vault_chroma.py first."
        )


def build_chroma_index(
    vault_path: Path,
    model_name: str,
) -> int:
    if model_name != DEFAULT_EMBEDDING_MODEL:
        raise SemanticSearchUnavailable("Only text-embedding-3-small is permitted for hybrid retrieval.")
    notes, parse_errors = scan_vault(vault_path)
    errors = validation_errors(notes, parse_errors)
    if errors:
        raise ValueError("Vault index preflight failed: " + "; ".join(errors))

    candidates = build_candidates(notes)
    if not candidates:
        raise ValueError("No eligible vault sections are available to index.")
    fingerprint = vault_fingerprint(candidates)

    client = create_chroma_client()
    collection = get_chroma_collection(client, create=True)
    expected = chroma_index_metadata(model_name, fingerprint, len(candidates))
    if all((collection.metadata or {}).get(key) == value for key, value in expected.items()):
        try:
            if collection.count() == len(candidates):
                return len(candidates)
        except Exception as error:
            raise SemanticSearchUnavailable(
                f"Could not read the Chroma Cloud index ({type(error).__name__})."
            ) from error
    model = load_embedding_model(model_name)

    ids = [candidate_id(candidate) for candidate in candidates]
    metadatas = [
        {
            "path": candidate.note.path.as_posix(),
            "section_index": candidate.section_index,
            "heading": candidate.section.heading,
        }
        for candidate in candidates
    ]

    batch_size = 100
    for start in range(0, len(candidates), batch_size):
        end = start + batch_size
        try:
            embeddings = model.encode_document(
                [candidate_document(candidate) for candidate in candidates[start:end]]
            )
            collection.upsert(
                ids=ids[start:end],
                embeddings=embeddings,
                metadatas=metadatas[start:end],
            )
        except Exception as error:
            raise SemanticSearchUnavailable(
                f"Could not embed or write a vault batch to OpenAI/Chroma Cloud ({type(error).__name__})."
            ) from error

    current_ids = set(ids)
    try:
        stored_ids = collection.get(include=["metadatas"]).get("ids", [])
        stale_ids = [record_id for record_id in stored_ids if record_id not in current_ids]
        for start in range(0, len(stale_ids), batch_size):
            collection.delete(ids=stale_ids[start : start + batch_size])
        collection.modify(metadata=chroma_index_metadata(
            model_name,
            fingerprint,
            len(candidates),
        ))
    except Exception as error:
        raise SemanticSearchUnavailable(
            f"Could not finalize the Chroma Cloud index ({type(error).__name__})."
        ) from error

    return len(candidates)


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
            "Hybrid search requires a semantic scorer; use --hybrid-search false "
            "only for keyword retrieval."
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
                "vector_store": "Chroma Cloud" if semantic_mode == "required" else None,
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
    """Embed each requirement with OpenAI and retrieve indexed vectors from Chroma."""

    def __init__(
        self,
        vault_path: Path,
        model_name: str,
    ) -> None:
        self.vault_path = vault_path
        self.model_name = model_name
        self.notes, self.parse_errors = scan_vault(vault_path)
        self.candidates = build_candidates(self.notes)
        self.fingerprint = vault_fingerprint(self.candidates)
        self.local_fingerprint = local_vault_fingerprint(vault_path)
        self.client = create_chroma_client()
        self.collection = get_chroma_collection(self.client)
        self.model = load_embedding_model(model_name)
        self.query_cache: dict[str, object] = {"entries": {}}
        self._check_index()

    def _check_index(self) -> None:
        validate_chroma_index(
            self.collection,
            self.model_name,
            self.fingerprint,
            len(self.candidates),
        )

    def _refresh_if_needed(self) -> None:
        """Refresh local evidence and require an explicit reindex after vault edits."""

        current_local_fingerprint = local_vault_fingerprint(self.vault_path)
        if current_local_fingerprint == self.local_fingerprint:
            return

        notes, parse_errors = scan_vault(self.vault_path)
        candidates = build_candidates(notes)
        current_fingerprint = vault_fingerprint(candidates)
        if current_fingerprint != self.fingerprint:
            validate_chroma_index(
                self.collection,
                self.model_name,
                current_fingerprint,
                len(candidates),
            )
            self.fingerprint = current_fingerprint
        self.notes, self.parse_errors = notes, parse_errors
        self.candidates = candidates
        self.local_fingerprint = current_local_fingerprint
        self.query_cache = {"entries": {}}

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
        semantic_scores: Sequence[float],
    ) -> dict[str, object]:
        requirement = str(prepared["requirement"])
        terms = list(prepared["terms"])  # type: ignore[arg-type]
        limit = int(prepared["limit"])
        compact = bool(prepared["compact"])
        semantic_min_score = float(prepared["semantic_min_score"])
        keyword_weight = float(prepared["keyword_weight"])
        semantic_weight = float(prepared["semantic_weight"])
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
            semantic_min_score,
            keyword_weight,
            semantic_weight,
        )

    def search_requests(self, requests: Sequence[dict[str, object]]) -> list[dict[str, object]]:
        """Batch query encoding and Chroma requests; cache results in process memory only."""

        self._refresh_if_needed()
        prepared_requests = [self._prepare_request(request) for request in requests]
        entries = self.query_cache.setdefault("entries", {})
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
            query_embeddings = self.model.encode_queries(query_texts)
            semantic_by_requirement = self._semantic_scores(query_embeddings)
            for query_text, semantic_scores in zip(query_texts, semantic_by_requirement):
                for key, prepared in unique_requirements[query_text]:
                    result = self._search_prepared_request(prepared, semantic_scores)
                    entries[key] = result
                    for index, _ in pending[key]:
                        results[index] = result

        return [result for result in results if result is not None]

    def _semantic_scores(self, query_embeddings: Sequence[Sequence[float]]) -> list[list[float]]:
        # Keep cloud query payloads small; independent chunks share one warm client.
        if len(query_embeddings) > 5 and hasattr(self, "collection"):
            from concurrent.futures import ThreadPoolExecutor
            chunks = [query_embeddings[i:i+5] for i in range(0, len(query_embeddings), 5)]
            with ThreadPoolExecutor(max_workers=4) as executor:
                return [row for chunk in executor.map(self._semantic_scores, chunks) for row in chunk]
        if not self.candidates:
            return [[] for _ in query_embeddings]

        vectors = [[float(value) for value in embedding] for embedding in query_embeddings]
        if not hasattr(self, "collection"):
            # Supports deterministic in-memory service stand-ins without persisting vectors.
            indexed_vectors = getattr(self, "embeddings", [])
            return [
                [
                    math.fsum(float(value) * float(other) for value, other in zip(query, indexed))
                    for indexed in indexed_vectors
                ]
                for query in vectors
            ]
        try:
            result = self.collection.query(
                query_embeddings=vectors,
                n_results=len(self.candidates),
                include=["distances"],
            )
        except Exception as error:
            raise SemanticSearchUnavailable(
                f"Chroma Cloud vector search failed ({type(error).__name__})."
            ) from error

        indices = {candidate_id(candidate): index for index, candidate in enumerate(self.candidates)}
        scores_by_query: list[list[float]] = []
        for ids, distances in zip(result.get("ids", []), result.get("distances", [])):
            if len(ids) != len(indices) or any(record_id not in indices for record_id in ids):
                raise SemanticSearchUnavailable("Chroma Cloud returned an incomplete or stale candidate set.")
            scores = [0.0] * len(self.candidates)
            for record_id, distance in zip(ids, distances):
                index = indices.get(record_id)
                if index is not None and distance is not None:
                    # Chroma's default L2 metric is squared distance; normalized
                    # vectors make cosine similarity equal to 1 - distance / 2.
                    scores[index] = max(-1.0, min(1.0, 1.0 - float(distance) / 2.0))
            scores_by_query.append(scores)
        if len(scores_by_query) != len(vectors):
            raise SemanticSearchUnavailable("Chroma Cloud returned an incomplete vector-search response.")
        return scores_by_query

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
        except (OSError, TypeError, ValueError, RuntimeError, json.JSONDecodeError) as error:
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
    request_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(request_dir, 0o700)
    ready_path = request_dir / "READY"
    if not ready_path.exists():
        raise SemanticSearchUnavailable(f"Evidence service is not ready: {request_dir}")

    request_id = uuid.uuid4().hex
    request_path = request_dir / f"{request_id}.request.json"
    response_path = request_dir / f"{request_id}.response.json"
    temporary_path = request_dir / f"{request_id}.request.tmp"
    write_private_text(temporary_path, json.dumps(request, ensure_ascii=False))
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
        response_path.unlink(missing_ok=True)
        temporary_path.unlink(missing_ok=True)
    raise SemanticSearchUnavailable(f"Evidence service timed out: {request_dir}")


def write_private_text(path: Path, text: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            descriptor = -1
            output.write(text)
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def cleanup_stale_evidence_responses(request_dir: Path) -> None:
    cutoff = time.time() - 600
    for path in request_dir.glob("*.response.json"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except FileNotFoundError:
            pass


class EvidenceFileService:
    """Filesystem transport for environments where local sockets are unavailable."""

    def __init__(self, request_dir: Path, evidence_service: EmbeddingIndexService) -> None:
        self.request_dir = request_dir
        self.evidence_service = evidence_service
        self.request_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.request_dir, 0o700)
        write_private_text(
            self.request_dir / "READY",
            f"{EVIDENCE_SERVICE_VERSION}:{self.evidence_service.model_name}\n",
        )

    def serve_forever(self) -> None:
        try:
            next_cleanup = 0.0
            while True:
                if time.monotonic() >= next_cleanup:
                    cleanup_stale_evidence_responses(self.request_dir)
                    next_cleanup = time.monotonic() + 60
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
                    write_private_text(response_path, json.dumps(response, ensure_ascii=False))
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
    )
    if request_dir is not None:
        file_service = EvidenceFileService(request_dir, service)
        print(
            f"Evidence service ready: {len(service.candidates)} candidates, "
            f"vector_store=Chroma Cloud, request_dir={request_dir}",
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
        f"vector_store=Chroma Cloud, socket={socket_path}",
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


def run_check_index(vault_path: Path, model_name: str) -> int:
    if model_name != DEFAULT_EMBEDDING_MODEL:
        raise SemanticSearchUnavailable("Only text-embedding-3-small is permitted for hybrid retrieval.")
    notes, parse_errors = scan_vault(vault_path)
    errors = validation_errors(notes, parse_errors)
    if errors:
        raise ValueError("Vault index preflight failed: " + "; ".join(errors))
    candidates = build_candidates(notes)
    # Validate local embedding prerequisites without sending a billable probe.
    load_embedding_model(model_name)
    collection = get_chroma_collection(create_chroma_client())
    validate_chroma_index(
        collection,
        model_name,
        vault_fingerprint(candidates),
        len(candidates),
    )
    print(f"Chroma Cloud index is current: {len(candidates)} eligible sections.")
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


def keyword_only_result(
    notes: Sequence[VaultNote],
    request: dict[str, object],
    semantic_model: str,
) -> dict[str, object]:
    requirement = str(request["requirement"])
    terms = request.get("terms", [])
    if isinstance(terms, str):
        terms = [terms]
    limit = int(request.get("limit", 3))
    if limit < 1:
        raise ValueError("--limit must be at least 1")
    candidates = build_candidates(notes)
    matches = search_notes(
        notes,
        requirement,
        [str(term) for term in terms],
        limit,
        semantic_scorer=lambda _query, _candidates: [0.0] * len(candidates),
        semantic_min_score=1.0,
        keyword_weight=1.0,
        semantic_weight=0.0,
    )
    if bool(request.get("compact", True)):
        matches = compact_matches(matches)
    return result_payload(
        requirement,
        [str(term) for term in terms],
        matches,
        "off",
        semantic_model,
        1.0,
        1.0,
        0.0,
    )


def run_batch_search(
    vault_path: Path,
    input_path: Path,
    default_limit: int,
    compact: bool,
    hybrid_search: bool,
    semantic_model: str,
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

    if not hybrid_search:
        notes, _ = scan_vault(vault_path)
        print(json.dumps({
            "results": [keyword_only_result(notes, request, semantic_model) for request in requests]
        }, ensure_ascii=False, indent=2))
        return 0

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

    service = EmbeddingIndexService(vault_path, semantic_model)
    results = service.search_requests(requests)
    print(
        json.dumps(
            {"results": results, "embedding_usage": service.model.usage},
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
    hybrid_search: bool,
    semantic_model: str,
    semantic_min_score: float,
    keyword_weight: float,
    semantic_weight: float,
    compact: bool,
    socket_path: Path | None,
    request_dir: Path | None,
) -> int:
    if hybrid_search and request_dir is not None:
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
    if hybrid_search and socket_path is not None:
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

    if hybrid_search:
        service = EmbeddingIndexService(vault_path, semantic_model)
        result = service.search_request({
            "requirement": requirement,
            "terms": terms,
            "limit": limit,
            "compact": compact,
            "semantic_min_score": semantic_min_score,
            "keyword_weight": keyword_weight,
            "semantic_weight": semantic_weight,
        })
    else:
        notes, _ = scan_vault(vault_path)
        result = keyword_only_result(
            notes,
            {"requirement": requirement, "terms": terms, "limit": limit, "compact": compact},
            semantic_model,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser("check", help="validate vault readiness")
    check_parser.add_argument("--vault", type=Path, default=default_vault_path())

    index_check_parser = subparsers.add_parser(
        "check-index",
        help="verify that Chroma Cloud matches the current eligible vault",
    )
    index_check_parser.add_argument("--vault", type=Path, default=default_vault_path())
    index_check_parser.add_argument(
        "--embedding-model", "--semantic-model",
        dest="embedding_model",
        default=default_embedding_model(),
        help="OpenAI embedding model used by the Chroma index",
    )

    serve_parser = subparsers.add_parser(
        "serve",
        help="keep one OpenAI embedding client warm and serve Chroma Cloud searches",
    )
    serve_parser.add_argument("--vault", type=Path, default=default_vault_path())
    serve_parser.add_argument("--socket", type=Path, default=default_evidence_socket_path())
    serve_parser.add_argument("--request-dir", type=Path, default=None)
    serve_parser.add_argument(
        "--embedding-model", "--semantic-model",
        dest="embedding_model",
        default=default_embedding_model(),
        help="OpenAI embedding model used for search queries",
    )
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
        "--hybrid-search",
        type=parse_bool,
        default=None,
        metavar="true|false",
        help="override config/search_targets.yaml; false uses keyword retrieval only",
    )
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
        default=None,
        help="legacy alias: 'off' selects keyword-only retrieval",
    )
    search_parser.add_argument(
        "--embedding-model", "--semantic-model",
        dest="embedding_model",
        default=default_embedding_model(),
        help="OpenAI embedding model used for query and vault section text",
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
        help="hybrid score weight for Chroma Cloud similarity",
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
        "--hybrid-search",
        type=parse_bool,
        default=None,
        metavar="true|false",
        help="override config/search_targets.yaml; false uses keyword retrieval only",
    )
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
    batch_parser.add_argument(
        "--embedding-model", "--semantic-model",
        dest="embedding_model",
        default=default_embedding_model(),
        help="OpenAI embedding model used for query and vault section text",
    )
    batch_parser.add_argument("--semantic-min-score", type=float, default=DEFAULT_SEMANTIC_MIN_SCORE)
    batch_parser.add_argument("--keyword-weight", type=float, default=DEFAULT_KEYWORD_WEIGHT)
    batch_parser.add_argument("--semantic-weight", type=float, default=DEFAULT_SEMANTIC_WEIGHT)
    args = parser.parse_args(argv)
    if args.command in {"search", "batch-search"} and args.hybrid_search is None:
        args.hybrid_search = default_hybrid_search()
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    if args.command == "check":
        return run_check(args.vault)
    if args.command == "check-index":
        return run_check_index(args.vault, args.embedding_model)
    if args.command == "serve":
        return run_serve(
            args.vault,
            args.socket,
            args.request_dir,
            args.embedding_model,
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
            args.hybrid_search if args.semantic_mode is None else args.semantic_mode != "off",
            args.embedding_model,
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
            args.hybrid_search,
            args.embedding_model,
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
    except (OSError, ValueError, SemanticSearchUnavailable, json.JSONDecodeError) as error:
        print(f"vault_evidence: {error}", file=sys.stderr)
        raise SystemExit(1) from error
