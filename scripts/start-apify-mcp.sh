#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -z "${APIFY_TOKEN:-}" ]]; then
  source "$project_dir/scripts/load-apify-token.sh"
  load_apify_token "$project_dir/.env"
fi

exec /opt/homebrew/bin/npx -y mcp-remote \
  "https://mcp.apify.com/?tools=valig/linkedin-jobs-scraper,websift/seek-job-scraper" \
  --header "Authorization: Bearer $APIFY_TOKEN"
