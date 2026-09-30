# Spec Delta

## Purpose

Provide trusted, traceable retrieval of local career-vault facts that the job
search workflow can safely use as evidence when evaluating a job description.

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
eligible evidence candidates with both literal keyword and local semantic-search
signals. Each candidate SHALL identify its vault path, note type, relevant
heading or section, supporting text, skills metadata when present, source,
verification date, component retrieval scores, and the retrieval method or
methods that produced it.

#### Scenario: Direct skill match
- **WHEN** a query names a skill that appears in eligible evidence metadata or
  supporting text
- **THEN** the returned candidates include the matching evidence and its trace

#### Scenario: No supported evidence exists
- **WHEN** no eligible evidence matches a query
- **THEN** the system returns an empty candidate set without inferring a match

### Requirement: Local semantic privacy boundary

The system SHALL calculate semantic similarity locally from the original JD
requirement and eligible vault sections. It SHALL NOT use a project-maintained
synonym map or upload vault content to an embedding or retrieval API. The model
may be downloaded explicitly to a Git-ignored local cache; downloading model
assets does not authorize uploading the vault.

#### Scenario: Semantic retrieval broadens a search
- **WHEN** a JD requirement uses wording different from an eligible vault claim
- **THEN** the local semantic retriever may return that claim as a candidate with
  its semantic score and original text preserved

#### Scenario: A semantic candidate is not proof
- **WHEN** semantic retrieval returns a candidate for a JD requirement
- **THEN** the scoring workflow still requires the cited claim and source to
  establish a direct or transferable match

### Requirement: Vault privacy boundary

The retrieval process SHALL read the local vault only. It SHALL NOT upload vault
content, write job descriptions or application records to the vault, or include
retrieved claim text in the job-run log.

#### Scenario: Evidence is prepared for a score
- **WHEN** evidence is retrieved for a retained job
- **THEN** it is available to the scoring workflow without being appended to the
  run log or written back into the vault
