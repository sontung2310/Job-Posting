# Spec Delta

## Purpose

Provide trusted, traceable retrieval of verified career-vault facts that the
job search workflow can use as evidence when evaluating a job description.

## ADDED Requirements

### Requirement: Eligible vault evidence

The system SHALL treat a vault fact as eligible only when its Markdown
frontmatter declares `status: verified`, contains at least one non-empty
`source`, and contains a non-empty `last_verified` value. The system SHALL
exclude drafts, notes needing review, archived notes, templates, indexes, and
system notes from scoring evidence.

#### Scenario: Verified source-linked project is eligible
- **WHEN** a project note has verified status, a source, and a verification date
- **THEN** the system makes its relevant evidence available for retrieval

#### Scenario: Unverified evidence is excluded
- **WHEN** an otherwise matching note has `status: needs-review`
- **THEN** the system returns no scoring evidence from that note

### Requirement: Discovery readiness validation

Before job-source discovery starts, the system SHALL verify that the vault has
at least one eligible profile note, target-role preferences note, and atomic
evidence note. The system SHALL stop before any paid job-source call when this
validation fails and SHALL report which prerequisite is missing.

#### Scenario: Vault is ready for discovery
- **WHEN** all three required eligible note types are present
- **THEN** the vault validation succeeds and discovery may continue

#### Scenario: Missing verified target-role preferences
- **WHEN** the vault lacks an eligible target-role preferences note
- **THEN** validation fails before any job source is queried

### Requirement: Hybrid requirement-oriented evidence retrieval

Given a JD requirement in its original context, the system SHALL retrieve only
eligible evidence candidates. When `hybrid_search` is true, retrieval SHALL use
literal keyword and Chroma Cloud vector signals; when false, it SHALL use literal
keyword retrieval only. Each candidate SHALL identify its vault path, note type,
relevant heading or section, supporting text, skills metadata when present,
source, verification date, component retrieval scores, and the retrieval method
or methods that produced it.

#### Scenario: Direct skill match
- **WHEN** a query names a skill that appears in eligible evidence metadata or
  supporting text
- **THEN** the returned candidates include the matching evidence and its trace

#### Scenario: No supported evidence exists
- **WHEN** no eligible evidence matches a query
- **THEN** the system returns an empty candidate set without inferring a match

### Requirement: Chroma Cloud vector boundary

The system SHALL send eligible section text and JD requirement text to OpenAI's
`text-embedding-3-small` embeddings API. It SHALL use Chroma Cloud to compare the
resulting vectors. The configured collection SHALL contain section vectors and
citation metadata, but not section or JD text. With `hybrid_search: false`, the
system SHALL use keyword retrieval only and SHALL NOT call OpenAI or Chroma. The
system SHALL NOT use a project-maintained synonym map.

#### Scenario: Semantic retrieval broadens a search
- **WHEN** a JD requirement uses wording different from an eligible vault claim
- **THEN** Chroma Cloud may return that claim as a candidate with
  its semantic score and original text preserved

#### Scenario: A semantic candidate is not proof
- **WHEN** semantic retrieval returns a candidate for a JD requirement
- **THEN** the scoring workflow still requires the cited claim and source to
  establish a direct or transferable match

### Requirement: Vault privacy boundary

The retrieval process SHALL read the local vault and send eligible section text
to OpenAI only to compute embeddings. It SHALL send JD requirement text to
OpenAI only to compute query embeddings. It SHALL upload only eligible section
vectors, citation metadata, and a fingerprint of those eligible indexing inputs
to the configured Chroma Cloud collection. It SHALL NOT fingerprint ineligible
notes for cloud metadata. Hybrid preflight MAY send fixed, non-sensitive probe
text to OpenAI to verify embedding access before paid discovery. It
SHALL NOT store source text in Chroma, write job descriptions or application
records to the vault, or include retrieved claim text in the job-run log.

#### Scenario: Evidence is prepared for a score
- **WHEN** evidence is retrieved for a retained job
- **THEN** it is available to the scoring workflow without being appended to the
  run log or written back into the vault
