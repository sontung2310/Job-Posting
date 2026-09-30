#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

source "$project_dir/scripts/load-apify-token.sh"
load_apify_token "$project_dir/.env"

exec /opt/homebrew/bin/npx -y mcp-remote \
  "https://mcp.apify.com/?tools=curious_coder/linkedin-jobs-scraper,websift/seek-job-scraper" \
  --header "Authorization: Bearer $APIFY_TOKEN"
