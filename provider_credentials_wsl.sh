#!/usr/bin/env bash

# Shared credential validation for WSL launchers. This file must be sourced.

load_provider_credentials() {
  local credentials_file="$1"
  if [[ ! -f "$credentials_file" ]]; then
    echo "Credentials file is missing: $credentials_file" >&2
    return 1
  fi
  set -a
  # shellcheck disable=SC1090
  source "$credentials_file"
  set +a
}

require_model_credentials() {
  local model_preset="$1"
  case "$model_preset" in
    deepseek-*)
      if [[ -z "${DEEPSEEK_API_KEY:-}" ]]; then
        echo "DEEPSEEK_API_KEY is required for $model_preset" >&2
        return 1
      fi
      DEEPSEEK_API_BASE="${DEEPSEEK_API_BASE:-https://api.deepseek.com}"
      export DEEPSEEK_API_BASE
      ;;
    gemini-*)
      if [[ -z "${GEMINI_API_KEY:-}" ]]; then
        echo "GEMINI_API_KEY is required for $model_preset" >&2
        return 1
      fi
      ;;
    claude-*-anu)
      # ANU strproxy expects a Bearer token. Keep accepting the legacy local
      # ANTHROPIC_API_KEY entry so the populated secret file need not be
      # rewritten or printed during migration.
      if [[ -z "${ANTHROPIC_AUTH_TOKEN:-}" && -n "${ANTHROPIC_API_KEY:-}" ]]; then
        ANTHROPIC_AUTH_TOKEN="$ANTHROPIC_API_KEY"
        export ANTHROPIC_AUTH_TOKEN
      fi
      if [[ -z "${ANTHROPIC_AUTH_TOKEN:-}" ]]; then
        echo "ANTHROPIC_AUTH_TOKEN is required for $model_preset" >&2
        return 1
      fi
      ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL:-https://strproxy.comp.anu.edu.au}"
      export ANTHROPIC_BASE_URL
      ;;
    claude-*-direct)
      if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
        echo "ANTHROPIC_API_KEY is required for $model_preset" >&2
        return 1
      fi
      ;;
    claude-*)
      if [[ -z "${AWS_BEARER_TOKEN_BEDROCK:-}" \
         && -z "${ANTHROPIC_AWS_API_KEY:-}" \
         && -z "${AWS_PROFILE:-}" \
         && ( -z "${AWS_ACCESS_KEY_ID:-}" || -z "${AWS_SECRET_ACCESS_KEY:-}" ) ]]; then
        echo "AWS Bedrock credentials are required for $model_preset" >&2
        return 1
      fi
      if [[ -z "${AWS_REGION:-${AWS_DEFAULT_REGION:-}}" ]]; then
        echo "AWS_REGION or AWS_DEFAULT_REGION is required for $model_preset" >&2
        return 1
      fi
      ;;
    gpt-*|codex-*)
      if [[ -z "${AZURE_OPENAI_ENDPOINT:-}" || -z "${AZURE_OPENAI_API_KEY:-}" ]]; then
        echo "AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY are required for $model_preset" >&2
        return 1
      fi
      ;;
    kimi-*)
      if [[ -z "${KIMI_BEDROCK_BASE_URL:-}" || -z "${KIMI_BEDROCK_API_KEY:-}" ]]; then
        echo "KIMI_BEDROCK_BASE_URL and KIMI_BEDROCK_API_KEY are required for $model_preset" >&2
        return 1
      fi
      ;;
    *)
      echo "No credential rule is defined for model preset: $model_preset" >&2
      return 1
      ;;
  esac
}

model_preset_from_args() {
  local default_preset="$1"
  shift
  local previous=""
  local argument
  for argument in "$@"; do
    if [[ "$previous" == "--model-preset" ]]; then
      printf '%s\n' "$argument"
      return 0
    fi
    case "$argument" in
      --model-preset=*)
        printf '%s\n' "${argument#--model-preset=}"
        return 0
        ;;
    esac
    previous="$argument"
  done
  printf '%s\n' "$default_preset"
}
