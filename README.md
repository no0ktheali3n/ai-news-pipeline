# ai-news-pipeline

Autonomous pipeline that scrapes three arXiv lanes daily, scores up to 40
candidates on builder-relevance with a single batched Haiku call, blends free
public attention signals (Hugging Face Daily Papers, Hacker News, Semantic
Scholar), and posts the top unposted paper as a Twitter/X thread — every
weekday at 16:00 UTC, running entirely on serverless infrastructure and free
API tiers.

---

## Architecture

```
EventBridge Scheduler (cron 0 16 * * MON-FRI)
        |
        v
  PipelineFunction  (controller, 900s ceiling)
        |
        +--invoke--> ScraperFunction
        |              - queries 3 arXiv lanes (ai-security / agents / llm-systems)
        |              - merges, dedupes, ledger-filters up to 40 candidates
        |              - one batched Haiku call scores all candidates
        |              - buzz enrichment (HF / HN / Semantic Scholar) — best-effort
        |              - selects top scorer; enforces min_score gate
        |              - writes one candidate to S3 scraper prefix
        |              - writes scored-candidates sidecar to separate S3 prefix
        |
        +--invoke--> SummarizerMainFunction  (controller)
        |              - reads scraper output; chunks article text
        |              - fans out to SummarizerFunction worker(s)
        |              - reassembles into final_summarized.json
        |              SummarizerFunction (worker)
        |                - Bedrock Sonnet call: hook-first thread contract
        |                - returns {"tweets": [...], "summary": "..."}
        |
        +--invoke--> PosterFunction
                       - validates thread contract; runs repair table
                       - deduplicates via posted ledger (S3 conditional write)
                       - posts thread to Twitter/X via Tweepy
                       - writes ledger entry with full provenance fields
                       - SNS alert on error; dry_run path posts nothing
```

**S3 is the message bus** between stages. No SQS, no Step Functions.
**SNS** handles failure alerts (email) and Slack webhook forwarding.

---

## Deployment states

| Feature | State |
|---|---|
| 3-lane arXiv scraping | **deployed** (v0.8.0) |
| Batched Haiku scoring (`builder_relevance`, `novelty`, `hook_potential`) | **deployed** (v0.8.0) |
| Scored-candidates sidecar (score history for calibration) | **deployed** (v0.8.0) |
| min_score gate + fallback-to-newest | **deployed** (v0.8.0) |
| Buzz signal blend (HF / HN / Semantic Scholar) | **built; deploy-gated** — ships behind `BuzzEnabled` template param |
| Thread contract (hook-first, no hashtags, mid-thread failure policy) | **built; A/B quality gate pending Bedrock quota** (feat/content-engine-phase2) |
| Evening second-slot (gated re-post of scored sidecar) | **designed; not built** (Phase 3) |
| Analytics dashboard | **designed; not built** (Phase 4) |

The current production stack runs **v0.8.0**: scored selection is live.
Thread contract code is merged into `feat/content-engine-phase2` and awaits
A/B evaluation before promotion to main.

---

## Key invariants

- **No post without a valid score.** In the evening/gated slot, if no
  candidate clears `min_score`, the run exits as a clean no-op. The
  invariant: nothing posts without a score.
- **Dedup via posted ledger.** `memory/posted_library.json` is the single
  source of truth. The scraper ledger-filters candidates before scoring; the
  poster writes a conditional S3 put (If-Match on ETag) before calling the
  Twitter API, so concurrent invocations cannot double-post.
- **Buzz never blocks.** Any source failure (HF, HN, Semantic Scholar)
  degrades gracefully to LLM-only scoring. `fetch_buzz`/`apply_buzz` never
  raise.
- **Sidecar is read-only to the pipeline.** The scored-candidates sidecar
  (`output/scored/`) is not scanned by the chunker or poster latest-file
  lookups. It exists solely for calibration and the future evening slot.
- **Scoring uses id-echoing, not positional zipping.** Haiku has violated
  JSON format instructions in production (see `docs/FIX_NOTES.md`). The
  validator requires an exact id-set match; any mismatch triggers fallback,
  never a silently wrong selection.
- **Retry safety.** `EventInvokeConfig: MaximumRetryAttempts: 0` on
  PipelineFunction. Retried invocations would spawn duplicate Bedrock runs
  and double-charge the write-post budget.

---

## Running locally

**Prerequisites:** Python 3.12, [uv](https://docs.astral.sh/uv/).

```bash
# Install deps (workspace root)
uv sync

# Run any test suite — no pytest, no live AWS calls
uv run python tests/test_fixes.py           # v0.7 regression suite (dedup, freshness, ledger)
uv run python tests/test_content_engine.py  # Phase 1: scoring, sidecar, gate, fallback
uv run python tests/test_buzz.py            # Phase 1.5: buzz fetch/blend, per-source degradation
uv run python tests/test_thread_contract.py # Phase 2: writer prompt, sanitize, validate/repair
uv run python tests/test_ab_harness.py      # A/B harness: blind labeling, per-pair isolation
```

All suites use `tests/stubs.py` to fake boto3/Tweepy/requests — no
credentials needed. Keep all five green before any deploy.

---

## Deploying

Requires AWS CLI configured with the `pipeline-admin` IAM profile.

```bash
# Step 1 — build
sam build

# Step 2 — preview (always inspect before executing)
sam deploy --no-execute-changeset \
  --parameter-overrides \
    S3OutputBucket=<your-bucket> \
    AlertEmail=<your-email>

# Step 3 — execute (after inspecting the change table)
aws cloudformation execute-change-set \
  --change-set-name <ARN from step 2>

# Step 4 — wait for completion
aws cloudformation wait stack-update-complete \
  --stack-name <stack-name>
```

See `.claude/skills/pipeline-ops-gotchas/SKILL.md` for layer-change
behaviour, Bedrock entitlement issues, and SAM permission classifier
quirks that affect this specific account.

**Dry-run invoke** (manual test — never invoke near 16:00 UTC weekdays,
ledger race risk):

```bash
aws lambda invoke \
  --function-name ai-research-pipeline \
  --payload '{"scrape_limit":5,"max_new_articles":1,"chunk_size":1,"skip_memory":false,"dry_run":true}' \
  --cli-binary-format raw-in-base64-out \
  response.json
```

`dry_run: true` posts nothing and never writes the ledger.

---

## Repo map

| Path | Contents |
|---|---|
| `lambda/pipeline_lambda.py` | Pipeline controller — stage orchestration, abort logic |
| `lambda/scraper/` | Scraper Lambda — lane queries, scoring, buzz, sidecar, gate |
| `lambda/summarizer/` | SummarizerMain (controller) + SummarizerFunction (worker) |
| `lambda/poster/` | Poster Lambda — thread contract enforcement, Tweepy, ledger write |
| `lambda/layers/common/python/utils/` | Shared modules: `scoring.py`, `buzz.py`, `thread_contract.py`, `summarizer.py`, `post_to_twitter.py` |
| `tests/` | Five dependency-free test suites + `stubs.py` |
| `scripts/` | One-off ops scripts |
| `docs/FIX_NOTES.md` | v0.7 incident — root cause, changes, remaining items |
| `docs/superpowers/specs/` | Content engine design spec (phases, invariants, rollout) |
| `docs/superpowers/plans/` | Phase build plans |
| `.claude/skills/pipeline-ops-gotchas/SKILL.md` | Operational gotchas — Bedrock entitlements, SAM quirks, testing conventions |
| `template.yaml` | SAM template — all functions, schedules, alarms, params |

---

## Versions

| Tag | Contents |
|---|---|
| `v0.7.0` | Bug-fix era: same-article dedup via posted ledger, freshness guards, SNS alerting, injection guard, secrets moved to env, Python 3.12, retry safety |
| `v0.8.0` | Content engine Phase 1: 3-lane scraping, batched Haiku scoring, sidecar, min_score gate, score-carrying ledger entries |
| `v0.9.0` | Phase 1.5 buzz signal — pending merge (BuzzEnabled kill switch; `buzz.py` built and tested) |
| `v0.10.0` | Phase 2 thread contract — pending A/B evaluation (built on feat/content-engine-phase2) |

---

## Further reading

- `docs/FIX_NOTES.md` — detailed write-up of the v0.7 incident and every
  fix applied during that deploy cycle
- `docs/superpowers/specs/2026-07-03-content-engine-design.md` — full content
  engine design: selection rubric, ledger-as-queue, thread contract spec,
  buzz signal, rollout gating criteria
- `.claude/skills/pipeline-ops-gotchas/SKILL.md` — operational knowledge
  specific to this account and stack; read before any deploy or manual invoke
