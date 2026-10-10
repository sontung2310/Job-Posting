# Workflow boundary fixes

The workflow remains retrieval → ranked scoring report → human selection →
suggestions → enabled destination preparation. Destination ownership stays in
the destination docs; scoring and suggestions do not write application records.

## Changes

- Hybrid query uncertainty is shared across run directories. Confirmed query
  results are reused; changing output paths does not authorize a retry.
- Profile/PDF readiness runs locally. Hybrid index work waits until a job passes
  the conditions; failed gates need no cloud work.
- Nonblocking operation locks distinguish active overlapping work from abandoned
  paid work. Retry approval cannot override an active lock.
- Selection is saved in stable candidate-number order regardless of input order.
- The destination document points to the actual suggestion-stage helper.
- Suggestion inspection extracts resume context from fingerprint-checked source
  PDFs instead of trusting packet resume text.
- Suggestions must retain all known evidence gaps, recommended-resume coverage
  gaps and unresolved gate wording. Generated templates include these items.
- Finalization loads the current profile once and reuses integrity-checked
  successful outcomes without rewriting them. Full report snapshots still
  inspect every job to preserve complete accounting.

Index helper diagnostics are captured so scoring CLI responses remain JSON-only.

## Verification

125 Python fixture tests pass, including regressions for all eight findings.
Discovery bridge fixture checks, shell syntax and diff whitespace checks pass.
External index/query calls are mocked. No live discovery, embeddings, destination
writes or personal evidence were used for verification.
