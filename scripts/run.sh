#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
env_file="$project_dir/.env"
codex_bin="${CODEX_BIN:-/opt/homebrew/bin/codex}"
vault_check="$project_dir/scripts/vault_evidence.py"
semantic_healthcheck="$project_dir/scripts/semantic_healthcheck.py"
semantic_python="$project_dir/.venv/bin/python"
pipeline_log_script="$project_dir/scripts/pipeline_log.py"
semantic_model_cache="$project_dir/models/sentence-transformers"
embedding_index_dir="$project_dir/models/vault-embeddings"
evidence_socket="$project_dir/.state/vault-evidence.sock"
evidence_request_dir="$project_dir/.state/vault-evidence-requests"
evidence_pid_file="$project_dir/.state/vault-evidence-service.pid"
evidence_service_log="$project_dir/.state/vault-evidence-service.log"
ledger_script="$project_dir/scripts/scoring_ledger.py"
rates_file="$project_dir/config/scoring_cost_rates.json"
scoring_model="${CODEX_MODEL:-gpt-5.6-luna}"
scoring_reasoning_effort="${CODEX_REASONING_EFFORT:-xhigh}"
semantic_model="${SEMANTIC_MODEL:-sentence-transformers/all-MiniLM-L6-v2}"
evidence_service_start_timeout_seconds="${EVIDENCE_SERVICE_START_TIMEOUT_SECONDS:-300}"
persistent_evidence_service="${PERSISTENT_EVIDENCE_SERVICE:-1}"

if [[ ! -f "$env_file" ]]; then
  echo "Missing $env_file. Add APIFY_TOKEN before running job discovery." >&2
  exit 1
fi

source "$project_dir/scripts/load-apify-token.sh"
load_apify_token "$env_file"

parse_flag() {
  case "$1" in
    1|true|TRUE|True|yes|YES|Yes|on|ON|On) echo "true" ;;
    0|false|FALSE|False|no|NO|No|off|OFF|Off|"") echo "false" ;;
    *) echo "Invalid boolean flag: $1. Use true/false." >&2; exit 1 ;;
  esac
}

write_notion="$(parse_flag "${WRITE_NOTION:-false}")"
write_obsidian="$(parse_flag "${WRITE_OBSIDIAN:-false}")"

resume_files=()
while IFS= read -r resume_file; do
  resume_files+=("$resume_file")
done < <(find "$project_dir/resumes" -maxdepth 1 -type f -iname '*.pdf' -print | sort)
if (( ${#resume_files[@]} < 2 )); then
  echo "Preflight failed. Add at least two text-extractable PDFs to $project_dir/resumes/." >&2
  exit 1
fi

required_files=(
  "$project_dir/AGENTS.md"
  "$project_dir/config/search_targets.yaml"
  "$project_dir/config/obsidian_schema.md"
  "$project_dir/career-vault/AGENTS.md"
  "$project_dir/requirements-semantic.txt"
  "$vault_check"
  "$semantic_healthcheck"
  "$pipeline_log_script"
  "$ledger_script"
  "$rates_file"
  "$project_dir/config/notion_schema.md"
)

missing=0
for required_file in "${required_files[@]}"; do
  if [[ ! -s "$required_file" ]]; then
    echo "Missing or empty: $required_file" >&2
    missing=1
  fi
done

if [[ "$missing" -ne 0 ]]; then
  echo "Preflight failed. Add the missing files before running job discovery." >&2
  exit 1
fi

pdftotext_bin="${PDFTOTEXT_BIN:-$(command -v pdftotext || true)}"
if [[ -z "$pdftotext_bin" ]]; then
  pdftoppm_bin="$(command -v pdftoppm || true)"
  if [[ "$pdftoppm_bin" == */dependencies/bin/override/pdftoppm ]]; then
    for bundled_pdftotext in \
      "$(cd "$(dirname "$pdftoppm_bin")/../../native/poppler/poppler/bin" && pwd)/pdftotext" \
      "$(cd "$(dirname "$pdftoppm_bin")/../../native/poppler/bin" && pwd)/pdftotext"; do
      if [[ -x "$bundled_pdftotext" ]]; then
        pdftotext_bin="$bundled_pdftotext"
        break
      fi
    done
  fi
fi
if [[ -z "$pdftotext_bin" || ! -x "$pdftotext_bin" ]]; then
  echo "Preflight failed. pdftotext is required to verify résumé extractability." >&2
  exit 1
fi

resume_text_missing=0
for resume_file in "${resume_files[@]}"; do
  if ! "$pdftotext_bin" "$resume_file" - 2>/dev/null | awk 'NF { found=1 } END { exit found ? 0 : 1 }'; then
    echo "Résumé has no extractable text: $resume_file" >&2
    resume_text_missing=1
  fi
done

if [[ "$resume_text_missing" -ne 0 ]]; then
  echo "Preflight failed. Re-export or OCR both résumé PDFs before job discovery." >&2
  exit 1
fi

if [[ ! -x "$semantic_python" || ! -d "$semantic_model_cache" ]]; then
  echo "Hybrid retrieval is not ready. Create .venv, install requirements-semantic.txt, and run one search with --allow-model-download." >&2
  exit 1
fi

if [[ "${1:-}" == "--check" || "${RUN_SEMANTIC_HEALTHCHECK:-0}" == "1" ]]; then
  if ! "$semantic_python" "$semantic_healthcheck" --model-cache "$semantic_model_cache"; then
    echo "Hybrid retrieval is not ready. Repair the local embedding environment before job discovery." >&2
    exit 1
  fi
fi

if ! "$semantic_python" "$ledger_script" validate-rates --model "$scoring_model"; then
  echo "Scoring cost-rate configuration is not ready for $scoring_model." >&2
  exit 1
fi

if ! python3 "$vault_check" check; then
  echo "Preflight failed. Resolve the Career Evidence Vault review items before job discovery." >&2
  exit 1
fi

if [[ "${1:-}" == "--check" ]]; then
  echo "Preflight passed. APIFY_TOKEN was loaded from .env (value hidden)."
  exit 0
fi

if [[ ! -x "$codex_bin" ]]; then
  echo "Codex CLI not found or not executable: $codex_bin" >&2
  exit 1
fi

report_dir="$project_dir/reports"
mkdir -p "$report_dir"
run_id="$(date +%F)-manual-$(date +%H%M%S)-$$"
report_path="$report_dir/$run_id.md"
started_epoch_seconds="$(date +%s)"
"$semantic_python" "$ledger_script" begin --run-id "$run_id"
"$semantic_python" "$pipeline_log_script" init \
  --run-id "$run_id" \
  --started-epoch-seconds "$started_epoch_seconds" \
  --write-notion "$write_notion" \
  --write-obsidian "$write_obsidian"
export PIPELINE_RUN_ID="$run_id"
export WRITE_NOTION="$write_notion"
export WRITE_OBSIDIAN="$write_obsidian"

mkdir -p "$project_dir/.state"
evidence_service_pid=""
cleanup_evidence_service() {
  if [[ "$persistent_evidence_service" != "1" && -n "$evidence_service_pid" ]] && kill -0 "$evidence_service_pid" 2>/dev/null; then
    kill "$evidence_service_pid" 2>/dev/null || true
    wait "$evidence_service_pid" 2>/dev/null || true
    rm -f "$evidence_pid_file"
  fi
  if [[ "$persistent_evidence_service" != "1" ]]; then
    rm -f "$evidence_socket"
  fi
  if [[ "$persistent_evidence_service" != "1" && -d "$evidence_request_dir" ]]; then
    find "$evidence_request_dir" -maxdepth 1 -type f -delete
  fi
}
trap cleanup_evidence_service EXIT

service_ready=0
existing_service_pid=""
if [[ -f "$evidence_pid_file" ]]; then
  existing_service_pid="$(tr -d '[:space:]' < "$evidence_pid_file")"
fi
if [[ -n "$existing_service_pid" ]] && kill -0 "$existing_service_pid" 2>/dev/null && [[ -f "$evidence_request_dir/READY" ]]; then
  evidence_service_pid="$existing_service_pid"
  service_ready=1
  echo "Reusing warm local evidence service (pid $evidence_service_pid)."
else
  rm -f "$evidence_socket" "$evidence_pid_file" "$evidence_request_dir/READY"
  if [[ -d "$evidence_request_dir" ]]; then
    find "$evidence_request_dir" -maxdepth 1 -type f -delete
  fi
  nohup "$semantic_python" "$vault_check" serve \
    --vault "$project_dir/career-vault" \
    --socket "$evidence_socket" \
    --request-dir "$evidence_request_dir" \
    --semantic-model "$semantic_model" \
    --model-cache "$semantic_model_cache" \
    --index-path "$embedding_index_dir" \
    --pid-file "$evidence_pid_file" \
    >"$evidence_service_log" 2>&1 < /dev/null &
  evidence_service_pid=$!

  echo "Starting local evidence service (cold embedding startup may take a few minutes)..."
  service_start_deadline=$(( $(date +%s) + evidence_service_start_timeout_seconds ))
  while [[ "$(date +%s)" -lt "$service_start_deadline" ]]; do
    if [[ -f "$evidence_request_dir/READY" ]]; then
      service_ready=1
      break
    fi
    if ! kill -0 "$evidence_service_pid" 2>/dev/null; then
      echo "Evidence service failed to start. See $evidence_service_log" >&2
      exit 1
    fi
    sleep 0.5
  done
fi
if [[ "$service_ready" -ne 1 ]]; then
  echo "Evidence service did not become ready. See $evidence_service_log" >&2
  exit 1
fi
export VAULT_EVIDENCE_REQUEST_DIR="$evidence_request_dir"

prompt="Read AGENTS.md and run today's discovery workflow through the approval report. Use verified, source-linked career-vault evidence for Candidate Evidence Fit and assess both resumes separately for Resume Coverage. For every JD requirement, use ./.venv/bin/python scripts/vault_evidence.py search --limit 3 --compact with its complete original wording in --requirement and use --term only for exact tools, acronyms, or phrases in that JD. When several requirements are available together, prefer batch-search with a local JSON array of the same request objects; never repeat an identical requirement unnecessarily. The search command is connected to the persistent local evidence service, which keeps the model warm, reuses the local embedding index, batches query encoding, and caches complete results. Inspect the cited claim and source yourself: hybrid retrieval scores only rank candidates and cannot establish a direct match, transferable match, or hard-requirement fulfilment. Use ./.venv/bin/python scripts/pipeline_log.py discovery-summary and discovery-job to write privacy-safe logs/DD-MM-YYYY/discovery.jsonl. Discovery outcomes must be mutually exclusive: exactly one of fetch, reject, or retain per platform/job. Use stable job IDs or --job-url, which is hashed; never put a full JD in the log. For Stage 3, follow docs/03-suggestions.md and use the installed ResumeSkills: job-description-analyzer, resume-ats-optimizer, tech-resume-optimizer, resume-tailor, and resume-bullet-writer. Write one suggestion record per qualifying job with ./.venv/bin/python scripts/pipeline_log.py suggestion. Record token usage and cost only when actually exposed; otherwise leave them null and never fabricate estimates. Do not invoke cover-letter-generator or create or update Obsidian packages or Notion pages during discovery; wait for explicit approval. This batch's private scoring-ledger run ID is $run_id. After finalising Stage 2 for every JD that was scored, including an ineligible or below-threshold JD, run ./.venv/bin/python scripts/scoring_ledger.py record with that run ID, its canonical URL, company, position, rounded Candidate Evidence Fit, status (qualified, below_threshold, or ineligible), and a factual reason of no more than 240 characters. The command hashes the URL; do not put a raw URL, full JD, or evidence text in the reason. Do not record a draft for jobs that never reached Stage 2. Storage flags are WRITE_NOTION=$write_notion and WRITE_OBSIDIAN=$write_obsidian; both default false. After explicit approval, write only to destinations whose flag is true, then create one pipeline_log.py storage-job record per approved job and run storage-summary. A disabled destination must be logged as skipped, not failed. For Obsidian, success requires the application package to exist at the expected path. For Notion, success requires confirming the job appears in the Notion table."

if "$codex_bin" exec \
  --cd "$project_dir" \
  --sandbox workspace-write \
  --model "$scoring_model" \
  --config "model_reasoning_effort=\"$scoring_reasoning_effort\"" \
  --json \
  --output-last-message "$report_path" \
  "$prompt" | "$semantic_python" "$ledger_script" finalize \
    --run-id "$run_id" \
    --model "$scoring_model" \
    --started-epoch-seconds "$started_epoch_seconds" \
    --daily-log-root "$project_dir/logs"; then
  echo "Approval report saved to $report_path"
else
  exit 1
fi
