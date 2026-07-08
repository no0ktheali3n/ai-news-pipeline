#!/usr/bin/env bash
# Full-stack deploy with ALL parameter overrides + the OpenRouter key.
#
# `sam deploy --parameter-overrides` REPLACES the samconfig override list
# wholesale — passing only the key would silently deploy with fallback OFF
# and template-default model pins (final review 2026-07-05, Important).
# This script always passes the full set; keep it in sync with samconfig.toml.
#
# The key is read from a local file at runtime and never persisted or echoed.
# Usage: AWS_PROFILE=pipeline-admin scripts/deploy-full-stack.sh
set -euo pipefail

KEY_FILE="${OPENROUTER_KEY_FILE:-$HOME/projects/00-cr/openrouter-key.txt}"
if [[ ! -f "$KEY_FILE" ]]; then
  echo "ERROR: OpenRouter key file not found: $KEY_FILE" >&2
  exit 1
fi
KEY="$(<"$KEY_FILE")"

sam build

sam deploy --no-execute-changeset --parameter-overrides \
  "S3OutputBucket=aws-sam-cli-managed-default-samclisourcebucket-k0ga8ni5vmbc" \
  "ScraperOutputPrefix=ai-research-pipeline/output/scraper/" \
  "SummarizerOutputPrefix=ai-research-pipeline/output/summarizer/" \
  "PosterOutputPrefix=ai-research-pipeline/output/poster/" \
  "BedrockModelId=us.anthropic.claude-haiku-4-5-20251001-v1:0" \
  "FinalSummarizedFile=final_summarized.json" \
  "MemoryOutputPrefix=ai-research-pipeline/output/memory/" \
  "MemoryOutputFile=article_memory.json" \
  "BedrockWriterModelId=us.anthropic.claude-sonnet-4-6" \
  "LlmFallbackProvider=openrouter" \
  "ScoringWRelevance=0.40" \
  "ScoringWNovelty=0.25" \
  "ScoringWHook=0.35" \
  "MediaEnabled=true" \
  "OpenRouterApiKey=$KEY"

echo
echo "Changeset created (not executed). Inspect it, then run:"
echo "  aws cloudformation execute-change-set --change-set-name <arn> --profile pipeline-admin"
echo "  aws cloudformation wait stack-update-complete --stack-name ai-research-pipeline --profile pipeline-admin"
