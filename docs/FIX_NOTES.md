# Fix Notes — "same article posted every run" (2026-07-03)

## Root cause

Changing `BEDROCK_MODEL_ID` (~Dec 2025, via console) broke every Bedrock call:
the summarizer's IAM policy hardcoded the **old** model ARN
(`template.yaml` pinned `anthropic.claude-3-5-sonnet-20240620-v1:0`), so the new
model returned `AccessDeniedException` on every invoke.

The failure then cascaded silently:

1. `utils/summarizer.py` swallowed the error and retried the *same article
   forever* (index never advanced on failure) until the Lambda was killed at its
   600s timeout → **no summary file was ever written to S3 again**.
2. `pipeline_lambda.py` ignored the summarizer failure and invoked the poster
   anyway.
3. `poster_lambda.py` selected "newest `.json` under the summarizer prefix" —
   frozen since the model change — and posted it. Every run. 6×/day, Mon–Fri.

Each broken run also burned ~10 min of Lambda compute in the retry loop.

## Changes

| File | Change |
|---|---|
| `template.yaml` | Bedrock IAM now uses scoped wildcards (`foundation-model/anthropic.*` + `inference-profile/*.anthropic.*`) so a model change can never outrun the policy again. Default model → `us.anthropic.claude-haiku-4-5-20251001-v1:0` (override via the `BedrockModelId` parameter). Poster gets memory-prefix R/W + ledger/freshness env vars. |
| `lambda/layers/common/python/utils/summarizer.py` | Fail-fast: max 2 attempts per article then skip (`MAX_ATTEMPTS_PER_ARTICLE`); throttling re-raised so backoff actually engages; non-throttle error return type fixed (was a bare string, crashed callers). |
| `lambda/summarizer/summarizer_lambda.py` | Never uploads an empty chunk; returns 500 so failure is visible upstream. |
| `lambda/summarizer/summarizer_main_lambda.py` | Chunk-wait loop actually re-polls S3 (old loop listed once — latent race). Response now includes `final_key`. |
| `lambda/pipeline/pipeline_lambda.py` | Poster only runs on a verified summarizer success (`statusCode==200`, `article_count>0`, `has_summaries`); otherwise aborts and alerts Slack via the Make webhook. Passes `final_key` to the poster as `summary_key`. |
| `lambda/poster/poster_lambda.py` | Posts the exact file from this run (`summary_key`); fallback listing has a freshness guard (`MAX_SUMMARY_AGE_HOURS`, default 6h — stale ⇒ refuse + alert). New **posted ledger** (`memory/posted_library.json` in S3): already-posted URLs are skipped; successful posts are recorded. Fixed `post_limit` event-key mismatch (was silently ignored). Alerts webhook on failure. |
| `tests/test_fixes.py` | Dependency-free regression tests (stubbed boto3/tweepy/requests): 9 tests covering the retry cap, the poster gate, ledger dedup, and the stale guard. `python3 tests/test_fixes.py` |

## Additional fixes found during deployment (2026-07-03)

- **Markdown-fenced JSON** — Haiku 4.5 wraps its JSON in ```` ```json ```` fences despite
  prompt instructions; `parse_model_json()` in `utils/summarizer.py` now strips fences and
  extracts the object. (Regression test included.)
- **Pipeline read timeout** — the pipeline's Lambda client used boto3's default 60s read
  timeout; now 780s with retries disabled (a retried invoke would spawn duplicate Bedrock
  runs). Pipeline function timeout raised to 900s to outlive its stages.
- **`lambda/pipeline/requirements.txt`** — the new webhook-alert import needs `requests`.
- **Runtime bumped python3.11 → python3.12** — matches local interpreter, so `sam build`
  runs natively (no container image pull).
- **samconfig.toml** was pinning the old Sonnet 3.5 model in `parameter_overrides` — updated.

Deployed and verified E2E 2026-07-03 (dry run: fresh article scraped, summarized by
`us.anthropic.claude-haiku-4-5-20251001-v1:0`, poster gated correctly). Deploys now run as
IAM user `pipeline-admin` (profile `pipeline-admin`, policy `ai-pipeline-admin-policy` v11).

## Deploy

```bash
sam build
sam deploy   # uses samconfig.toml; pass --parameter-overrides BedrockModelId=... to choose a different model
```

Post-deploy verification:

1. `aws lambda invoke --function-name ai-research-pipeline --payload '{"scrape_limit":1,"chunk_size":1,"dry_run":true}' out.json` → expect fresh titles in the response.
2. Check CloudWatch logs of `ai-research-summarizer` for a successful Bedrock call.
3. Confirm `s3://<bucket>/ai-research-pipeline/output/memory/posted_library.json` appears after the first real post.

## Known remaining items

All items from the original v0.6.x list (4-hour schedule, venv/snapshot repo bloat, import-time secrets, stale top-level `utils/`, CLI double-post) were fixed in v0.7.0. As of v0.8.0 (content engine Phase 1 — lane scraping + batched scoring + sidecar + min_score gate):

- ~~S3 lifecycle rules~~ applied 2026-07-03 with owner approval: scraper 14d / summarizer 14d / scored 30d (verified via get-bucket-lifecycle-configuration).
- Phase 1.5 buzz ships behind the BuzzEnabled template parameter — deploy with "false" to restore pure Phase 1 selection without a code change. Consumers must read buzz fields with .get(): rows have no buzz keys when the switch is off, buzz/buzz_raw = None when no source had signal, and populated values otherwise.
- Verify ledger provenance fields (`builder_relevance`, `novelty`, `hook_potential`, `composite`, `query_source`) in `posted_library.json` after the next scheduled run.
- Evening min_score slot needs threshold calibration from ≥10 scored runs before enabling (Phase 3 — do not assume 7.5).
- Rotate the Make webhook (low priority; value moved to `MAKE_WEBHOOK_URL` env in v0.7.0).
- Phases 1.5 (free buzz signal), 2 (thread contract), 4 (self-built analytics) are designed but not built — see `docs/superpowers/specs/2026-07-03-content-engine-design.md`.
