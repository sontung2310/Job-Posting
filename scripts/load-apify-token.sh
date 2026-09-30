#!/usr/bin/env bash

# Define load_apify_token for callers that need APIFY_TOKEN before starting Codex
# or the Apify MCP process. The dotenv file is parsed as data and is never executed.
load_apify_token() {
  local env_file="${1:?dotenv path is required}"
  local env_line=""
  local env_key=""
  local env_value=""
  local apify_token=""
  local write_notion=""
  local write_obsidian=""
  local notion_database_id=""

  if [[ ! -f "$env_file" ]]; then
    echo "Missing $env_file. Add APIFY_TOKEN before running job discovery." >&2
    return 1
  fi

  while IFS= read -r env_line || [[ -n "$env_line" ]]; do
    env_line="${env_line%$'\r'}"
    env_line="${env_line#"${env_line%%[![:space:]]*}"}"
    [[ -z "$env_line" || "$env_line" == \#* ]] && continue

    if [[ "$env_line" == export[[:space:]]* ]]; then
      env_line="${env_line#export}"
      env_line="${env_line#"${env_line%%[![:space:]]*}"}"
    fi

    env_key="${env_line%%=*}"
    env_value="${env_line#*=}"
    env_key="${env_key%"${env_key##*[![:space:]]}"}"

    if [[ "$env_key" == "APIFY_TOKEN" && "$env_line" == *=* ]]; then
      env_value="${env_value#"${env_value%%[![:space:]]*}"}"
      env_value="${env_value%"${env_value##*[![:space:]]}"}"
      if [[ ${#env_value} -ge 2 ]]; then
        if [[ "$env_value" == \"*\" && "$env_value" == *\" ]]; then
          env_value="${env_value:1:${#env_value}-2}"
        elif [[ "$env_value" == \'*\' && "$env_value" == *\' ]]; then
          env_value="${env_value:1:${#env_value}-2}"
        fi
      fi
      apify_token="$env_value"
    fi

    if [[ "$env_key" == "WRITE_NOTION" && "$env_line" == *=* ]]; then
      env_value="${env_value#"${env_value%%[![:space:]]*}"}"
      env_value="${env_value%"${env_value##*[![:space:]]}"}"
      if [[ ${#env_value} -ge 2 ]]; then
        if [[ "$env_value" == \"* && "$env_value" == *\" ]]; then
          env_value="${env_value:1:${#env_value}-2}"
        elif [[ "$env_value" == \'* && "$env_value" == *\' ]]; then
          env_value="${env_value:1:${#env_value}-2}"
        fi
      fi
      write_notion="$env_value"
    fi

    if [[ "$env_key" == "WRITE_OBSIDIAN" && "$env_line" == *=* ]]; then
      env_value="${env_value#"${env_value%%[![:space:]]*}"}"
      env_value="${env_value%"${env_value##*[![:space:]]}"}"
      if [[ ${#env_value} -ge 2 ]]; then
        if [[ "$env_value" == \"* && "$env_value" == *\" ]]; then
          env_value="${env_value:1:${#env_value}-2}"
        elif [[ "$env_value" == \'* && "$env_value" == *\' ]]; then
          env_value="${env_value:1:${#env_value}-2}"
        fi
      fi
      write_obsidian="$env_value"
    fi

    if [[ "$env_key" == "NOTION_DATABASE_ID" && "$env_line" == *=* ]]; then
      env_value="${env_value#"${env_value%%[![:space:]]*}"}"
      env_value="${env_value%"${env_value##*[![:space:]]}"}"
      if [[ ${#env_value} -ge 2 ]]; then
        if [[ "$env_value" == \"* && "$env_value" == *\" ]]; then
          env_value="${env_value:1:${#env_value}-2}"
        elif [[ "$env_value" == \'* && "$env_value" == *\' ]]; then
          env_value="${env_value:1:${#env_value}-2}"
        fi
      fi
      notion_database_id="$env_value"
    fi
  done < "$env_file"

  if [[ -z "$apify_token" ]]; then
    echo "APIFY_TOKEN is missing or empty in $env_file." >&2
    return 1
  fi

  APIFY_TOKEN="$apify_token"
  export APIFY_TOKEN
  if [[ -n "$write_notion" ]]; then
    WRITE_NOTION="$write_notion"
    export WRITE_NOTION
  fi
  if [[ -n "$write_obsidian" ]]; then
    WRITE_OBSIDIAN="$write_obsidian"
    export WRITE_OBSIDIAN
  fi
  if [[ -n "$notion_database_id" ]]; then
    NOTION_DATABASE_ID="$notion_database_id"
    export NOTION_DATABASE_ID
  fi
}
