#!/usr/bin/env bash
set -euo pipefail
umask 077
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="$project_dir/.venv/bin/python"
codex_bin="${CODEX_BIN:-/opt/homebrew/bin/codex}"
check=false
scoring_only=false
retrieval_only=false
lookback_hours=""
input=""
while (( $# )); do
  case "$1" in
    --check) check=true; shift ;;
    --retrieval-only) retrieval_only=true; shift ;;
    --lookback-hours) lookback_hours="${2:?--lookback-hours needs a positive integer}"; shift 2 ;;
    --scoring-only) scoring_only=true; shift ;;
    --input) input="${2:?--input needs saved jobs JSON}"; shift 2 ;;
    *) echo "Usage: run.sh [--check] [--retrieval-only | --scoring-only --input SAVED_JOBS] [--lookback-hours HOURS]" >&2; exit 1 ;;
  esac
done
[[ -x "$python_bin" ]] || { echo 'Create .venv and install requirements.txt.' >&2; exit 1; }
pdftotext_bin="${PDFTOTEXT_BIN:-$(command -v pdftotext || true)}"
if [[ -z "$pdftotext_bin" ]]; then
  pdftoppm_bin="$(command -v pdftoppm || true)"
  if [[ "$pdftoppm_bin" == */dependencies/bin/override/pdftoppm ]]; then
    for candidate in "$(dirname "$pdftoppm_bin")/../../native/poppler/poppler/bin/pdftotext" "$(dirname "$pdftoppm_bin")/../../native/poppler/bin/pdftotext"; do
      if [[ -x "$candidate" ]]; then pdftotext_bin="$candidate"; break; fi
    done
  fi
fi
export PDFTOTEXT_BIN="$pdftotext_bin"
cd "$project_dir"
[[ "$scoring_only" == false || "$retrieval_only" == false ]] || { echo 'Choose only one phase.' >&2; exit 1; }
if [[ -n "$lookback_hours" ]]; then
  [[ "$lookback_hours" =~ ^[1-9][0-9]*$ ]] || { echo 'lookback hours must be a positive integer.' >&2; exit 1; }
  [[ "$scoring_only" == false ]] || { echo 'Lookback applies only to discovery.' >&2; exit 1; }
fi
mode=scoring
[[ "$scoring_only" == true ]] || mode=discovery
if [[ "$scoring_only" == false || "$check" == true ]]; then
  "$python_bin" scripts/readiness.py --mode "$mode" --local-only
fi
if [[ "$scoring_only" == false ]]; then
  needs_apify="$("$python_bin" -c 'import yaml; c=yaml.safe_load(open("config/search_targets.yaml")); print(str(any(c.get("sources",{}).get(s,{}).get("enabled",False) for s in ("linkedin","seek"))).lower())')"
  if [[ "$needs_apify" == true && -z "${APIFY_TOKEN:-}" ]]; then
    source "$project_dir/scripts/load-apify-token.sh"
    load_apify_token "$project_dir/.env"
  fi
fi
if [[ "$check" == true ]]; then
  echo "Readiness passed (mode=$mode)."
  exit 0
fi
[[ -x "$codex_bin" ]] || { echo "Codex CLI unavailable: $codex_bin" >&2; exit 1; }
if [[ "$scoring_only" == true ]]; then
  [[ -f "$input" ]] || { echo 'Scoring-only needs --input saved jobs JSON.' >&2; exit 1; }
fi
parse_flag() {
  case "$1" in
    true|TRUE|True|1|yes|YES|on|ON) echo true ;;
    false|FALSE|False|0|no|NO|off|OFF|"") echo false ;;
    *) echo 'Destination flag must be true or false.' >&2; return 1 ;;
  esac
}
export WRITE_OBSIDIAN="$(parse_flag "${WRITE_OBSIDIAN:-false}")"
export WRITE_NOTION="$(parse_flag "${WRITE_NOTION:-false}")"
run_id="$(TZ=Australia/Melbourne date +%F)-manual-$(date +%H%M%S)-$$"
started="$(date +%s)"
model="${CODEX_MODEL:-gpt-5.6-luna}"
mkdir -p reports
chmod 700 reports
"$python_bin" scripts/scoring_ledger.py validate-rates --model "$model"
"$python_bin" scripts/scoring_ledger.py begin --run-id "$run_id"
"$python_bin" scripts/pipeline_log.py init --run-id "$run_id" --started-epoch-seconds "$started" --write-notion "$WRITE_NOTION" --write-obsidian "$WRITE_OBSIDIAN"
export PIPELINE_RUN_ID="$run_id"
if [[ "$scoring_only" == true ]]; then
  sequence="Invoke .agents/skills/job-scoring/SKILL.md on saved jobs input: $input. Continue through the ranked scoring report and await current-report selection."
elif [[ "$retrieval_only" == true ]]; then
  sequence="Invoke .agents/skills/job-retrieval/SKILL.md and return its saved jobs and coverage handoff."
else
  sequence="Invoke .agents/skills/job-search/SKILL.md for progressive bounded retrieval and scoring. Continue through the ranked scoring report and await current-report selection."
fi
prompt="$sequence Run ID and explicit CLI scoring-ledger ID: $run_id. Discovery lookback override hours: ${lookback_hours:-none}; pass an explicit override to progressive session --lookback-hours, or stage1_options.lookbackHours for retrieval-only. Shared readiness cache: .state/readiness.json. Preserve coverage and approval boundaries. CLI finalization separately estimates full-turn usage."

"$codex_bin" exec --cd "$project_dir" --sandbox workspace-write \
  --config 'sandbox_workspace_write.network_access=true' --model "$model" \
  --config "model_reasoning_effort=\"${CODEX_REASONING_EFFORT:-xhigh}\"" \
  --json --output-last-message "$project_dir/reports/$run_id.md" "$prompt" </dev/null \
  | "$python_bin" scripts/scoring_ledger.py finalize --run-id "$run_id" --model "$model" \
    --started-epoch-seconds "$started" --daily-log-root "$project_dir/logs"
echo "Approval report saved to $project_dir/reports/$run_id.md"
