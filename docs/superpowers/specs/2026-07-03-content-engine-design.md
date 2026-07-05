# Content Engine — Design

**Date:** 2026-07-03 · **Status:** approved (design) — rev 2 after adversarial review · **Baseline:** v0.7.0

## Purpose

Shift the pipeline from "post the newest AI paper" to an audience-growth
content engine. Goals, in priority order: (A) grow a Twitter/X audience,
(B) build the owner's professional brand, (D) remain a portfolio-grade
autonomous system. A feeds B and D.

**Positioning:** practitioner-curator. The account's lens is a working AI
engineer surfacing research that matters to people who *build* — across the
applied-AI cluster (agents/LLM systems, AI security, AI ops) — not an academic
authority in one subfield.

## Constraints

- **Owner time ≈ zero** (60–80h workweeks). The primary loop must be fully
  autonomous; any human-in-the-loop element is optional and non-blocking.
- **No paid X API reads.** Posting is free-tier; reading tweet metrics is not.
  Analytics-by-API is milestone-gated. Nothing may depend on paid reads.
- **Write budget:** worst-case scheduled volume is 2 threads × 5 tweets =
  10 posts/day. Free-tier `POST /2/tweets` limits (last known ~17 requests/24h
  per user and 500/month) must be re-verified during Phase 2 — they have
  changed repeatedly. Scheduled volume must leave ≥40% daily headroom (cap
  threads at 4 tweets if it doesn't), and manual same-day tests use `dry_run`
  so a cap hit never truncates a live thread mid-hook.
- **Never regress reliability.** The v0.7.0 guarantees stand: posted-ledger
  dedup, poster gating, freshness guards, alerting, injection guard.
- Cost envelope: cents/day (one Haiku scoring call + 1–2 Sonnet-tier writer
  calls daily).

## Design

### 1. Selection: score, don't sort

**Queries.** The scraper queries **three lane-defining arXiv searches** (exact
strings tuned during implementation): AI security/safety of LLMs and agents;
agents/tool-use/multi-agent; LLM systems/ops. Results are merged, deduped by
URL, and ledger-filtered. `query_source` is recorded per candidate as the list
of every lane whose query returned the URL (lanes evaluated in a fixed,
documented order).

**Scoring.** One batched Haiku call scores all candidates on a practitioner
rubric: `builder_relevance`, `novelty`, `hook_potential` (each 0–10) →
composite `0.5*relevance + 0.25*novelty + 0.25*hook` (starting weights;
env-tunable). Robustness requirements:

- Hard cap: newest **40** candidates after merge/dedup/ledger-filter.
- Each candidate is sent as `{id: arXiv id, title, abstract truncated to
  ~400 chars}`.
- The response schema echoes the `id` per score object; validation requires
  `count == len(candidates)` AND an exact id-set match — any mismatch
  (FIX_NOTES documents Haiku violating JSON-format instructions in
  production) triggers the fallback path, **never positional zipping**.
- `max_tokens` is sized to the cap (~40 tokens/candidate + margin) so the
  array cannot truncate mid-object on busy announcement days.

**Selection & artifacts.** Scoring and selection happen **inside the scraper
Lambda, in memory**. The scraper writes exactly two artifacts:

1. The pipeline file under the existing scraper prefix containing **only the
   single top-scoring candidate** — the existing `max_new_articles=1`
   truncation becomes select-by-score instead of newest-first, preserving the
   one-article-per-file invariant the summarizer and poster rely on.
2. A same-day **scored-candidates sidecar** (full candidate records + scores +
   `query_source`) under a separate S3 prefix NOT scanned by the
   chunker/poster latest-file lookups. Full score tables are also logged to
   CloudWatch.

**Fallback.** Fallback-to-newest applies **only** to runs invoked with
`min_score: 0` (the noon slot), preserving daily cadence. For runs with
`min_score > 0`, a scoring failure means the gate cannot be evaluated: the run
exits as a clean no-op and emits the WARN webhook ("gate unevaluable").
**Invariant: no article is ever posted in the evening slot without a valid
score ≥ min_score.** Fallback firing on 3+ consecutive runs escalates from
WARN webhook to SNS email, so a permanently failing scoring path (e.g.,
AccessDenied) cannot hide behind green pipelines.

**Time budget & retry safety.**

- Remove the per-result `random_delay` in `utils/scraper.py`'s parse loop
  (each query is one HTTP fetch; delay only *between* the three query fetches
  — the current ~25–75 × 0.1–1.5s sleeps are pure waste).
- Per-stage budgets summing to ≤750s including the scoring call and the
  Sonnet-tier writer (pipeline Lambda ceiling is 900s).
- `template.yaml` adds `AWS::Lambda::EventInvokeConfig` with
  `MaximumRetryAttempts: 0` on PipelineFunction and scheduler `RetryPolicy`
  `MaximumRetryAttempts: 0` on both schedules, so a timed-out run that
  already posted is never replayed (a replay would ledger-filter the noon
  winner and post the runner-up as an unintended second tweet).

### 2. Second slot: the ledger is the queue

- A **second EventBridge schedule** (~20:00 UTC / 4pm ET weekdays) invokes the
  same pipeline with `min_score` in its payload (threshold set by calibration
  — see Rollout; adjustable in the schedule Input without redeploying code).
- **The evening run does not re-scrape or re-score** (arXiv announces once
  daily, so the candidate set is unchanged). The scraper, seeing
  `min_score > 0`, loads the same-day scored-candidates sidecar
  (freshness-guarded, <8h — same pattern as `chunker.get_latest_scraper_key`),
  ledger-filters it, and gates on the **persisted noon scores**: if the best
  remaining composite ≥ `min_score` it writes that single candidate to the
  scraper prefix and the pipeline proceeds; otherwise clean no-op. Missing or
  stale sidecar ⇒ clean no-op + WARN webhook — the gated slot never scores
  fresh. (Deterministic gate, one fewer Bedrock call and scrape per day.)
- `min_score` is enforced **in the scraper, after selection and before the S3
  write**: if no candidate clears it, the scraper returns the existing
  zero-new-articles result and the pipeline takes its established 200 no-op
  (no SNS email — enforcing later would spend writer cost or trip
  `abort_pipeline`'s failure email). `min_score` is added to
  `FUNCTION_PAYLOADS['scraper']` in `pipeline_lambda.py`, and the scraper
  logs the applied threshold on every run so a missing whitelist entry is
  visible as `threshold=0` in logs.
- **Observability:** every evening no-op logs a structured line with the max
  composite score and candidate count; `template.yaml` adds a log metric
  filter + alarm when the evening slot posts 0 times for 10 consecutive
  weekdays (this pipeline has already shipped one months-long silent
  degradation).
- **Ledger integrity is queue integrity:** `save_posted_ledger` uses S3
  conditional writes (`PutObject` If-Match on the ETag read at load; on 412,
  reload, merge, retry). Manual verification runs during rollout use
  `dry_run` or run outside the two scheduled windows.
- **Ledger growth:** entries older than 12 months are archived to a dated S3
  key and pruned on write — safe because lane queries sort by
  `-announced_date_first` and cannot resurface year-old papers; archival
  preserves analytics history.
- No queue infrastructure; one scored-candidates file per day in the existing
  bucket.

### 3. Voice: structured thread contract

- The writer prompt is rebuilt around the practitioner-curator voice. The
  model returns a **structured thread**: `{"tweets": [...], "summary": "..."}`
  with contract: tweet 1 = hook ≤ 240 chars, **no link**; middle tweets =
  substance with explicit builder-relevance; final tweet = paper title +
  arXiv link. **2–5 tweets total** (hook + link-tweet is a valid minimal
  thread; the prompt instructs: never pad to reach length — a tight 2-tweet
  post beats a stretched 4-tweet thread).
- **No hashtags.** `DEFAULT_HASHTAGS` is **deleted from
  `post_to_twitter.py`**, not bypassed.
- **Repair table** (contract violations): link in tweet 1 → strip; >5 tweets
  → truncate to 5; any tweet >280 chars post-sanitize, empty tweet, missing
  final arXiv link, or <2 tweets → hard-fail to fallback. The fallback path
  calls the legacy formatter with the writer's plain `summary` string and an
  empty tag block (no hashtags possible — the constant is gone).
- **Mid-thread failure policy:** on a mid-thread post failure (previously:
  abort, leave partial tweets up, never ledger), retry the failed tweet once;
  if still failing, post a minimal closing reply containing the arXiv link so
  the hook has its payoff (or delete the partials — `DELETE /2/tweets` is
  free-tier), and in all cases record the article in the ledger with status
  `partial` so it is never re-selected. A 429 mid-thread follows the same
  policy.
- **Models:** scoring = Haiku (`BedrockModelId`); writing = Sonnet-tier via a
  new `BedrockWriterModelId` template parameter. The summarizer role's
  Bedrock wildcards cover the writer model; **the scraper role currently has
  S3-only permissions, so Phase 1 adds `bedrock:InvokeModel` to
  ScraperFunction** scoped to the same anthropic foundation-model +
  inference-profile wildcards.
- **Provenance passthrough:** the summarizer copies `builder_relevance`,
  `novelty`, `hook_potential`, `composite`, and `query_source` verbatim from
  input to output; the poster writes all five into each ledger entry.

### 4. Human lane + free feedback floor

- When an evening (high-potential) post goes out, send the thread URL + a
  model-drafted one-line personal take suitable for a quote-tweet. This goes
  to the **WARN webhook channel by default (or a new dedicated SNS topic with
  a distinct subject prefix) — never the failure AlertTopic**, consistent
  with §1's rule that non-failures don't email as failures.
- **Free feedback floor:** after each successful post, the poster calls
  `GET /2/users/me?user.fields=public_metrics` (free tier, ≤25 req/24h — well
  within 2 posts/day) and records `follower_count` into that ledger entry;
  strictly non-blocking, logged no-op on any failure or if the endpoint
  leaves the free tier. The human-lane message includes the current follower
  count. The paid-analytics milestone is **defined numerically (500
  followers)** so it is checkable from the ledger.

### 5. Buzz signal (Phase 1.5)

Ground `hook_potential` in observed attention instead of model guesswork —
free, programmatic, no X involvement:

- **Hugging Face Daily Papers**: community upvotes per arXiv id (free JSON).
- **Hacker News (Algolia API)**: points + comment counts on submissions
  linking the arXiv id.
- **Semantic Scholar API**: early citation counts (useful for older
  candidates).

Fetched per candidate at scoring time (batched, best-effort — any source
failing degrades to LLM-only scoring, never blocks). Blended as a `buzz`
component into the composite (starting blend: replace half the
`hook_potential` weight; env-tunable). Raw per-source values are stored in
the sidecar and carried into the ledger for calibration. Ships only after
Phase 1's LLM-only scoring is proven live.

### 6. Self-built analytics (log now, dashboard later)

**Premise check:** per-post impressions/likes are not freely readable by API
— that is precisely the paid wall. A self-built layer therefore tracks three
free signal classes, structured so paid signals can join later without
rework:

1. **Selection-time signals** (free, automatic): rubric scores, buzz values,
   `query_source`/lane, thread shape (tweet count, hook length), slot
   (noon/evening), day-of-week — all already in the sidecar/ledger per this
   design.
2. **Outcome proxies** (free, automatic): `follower_count` captured per post
   (§4); follower *delta* between consecutive posts is a noisy but real
   per-post performance signal that de-noises over months of data.
3. **Owner-side enrichment** (optional, manual, cheap): X Premium's
   analytics dashboard exports per-post data; a monthly 5-minute CSV export
   dropped into `s3://…/analytics/imports/` joins real impressions/likes to
   ledger entries by tweet id. The dashboard renders with or without it.

**Dashboard (Phase 4):** a weekly Lambda renders a static HTML report to S3
(top posts by follower delta, lane performance, buzz-vs-outcome hit rate,
follower curve, threshold/no-op stats) and emails a one-paragraph digest +
link via the non-failure channel. No servers, no hosting cost, zero owner
obligation — the report accrues value passively as data accumulates.

**Design rule:** Phases 1–3 must log every field the dashboard needs, even
though the dashboard ships last. Data gaps are the only unrecoverable
failure in an analytics system.

### 7. X subscriptions: noted, gated on ROI

Current promo (2026-07): Premium ≈ $5/mo (first 2 months) includes the
account analytics dashboard; Premium+ ≈ $25/mo adds "Radar" trend features.
**Policy: no subscription until it justifies itself.** Concrete triggers —
Premium when the Phase 4 dashboard exists and impressions data would answer
a real open question (the manual CSV import is designed and waiting);
Premium+/Radar only if the free buzz trio (§5) proves insufficient for
selection. Revisit at each phase boundary; the paid **API** milestone
remains 500 followers.

### 8. Out of scope (explicitly deferred)

- Paid X API metrics / engagement feedback loop (milestone: 500 followers).
- Cross-posting (Bluesky/LinkedIn), weekly roundups, images/figures.
- Posting-time optimization beyond the two fixed slots (incl. weekend
  spillover — recorded deferral).
- Reply engagement and paper-author @-mentions are **deliberate non-goals** —
  the injection sanitizer defangs all mentions, so author attribution is
  structurally excluded; recorded as a chosen trade-off.

## Rollout

| Phase | Contents | Verification |
|---|---|---|
| 0 | One-time, ~30 min, **owner**: bio rewritten to the practitioner-curator lens, stating the account is an autonomous pipeline (the transparency IS the portfolio piece); pin the best early thread; profile link to repo/portfolio | — |
| 1 | Multi-query scrape + batched scoring (validation per §1) + sidecar + fallback + scraper Bedrock IAM + retry-safety config + score-carrying ledger | Tests; live run shows scored selection; ledger entry contains all five provenance fields; measured worst-case wall-clock ≤750s; observe ≥10 runs |
| 2 | Thread contract + writer model + repair table + mid-thread failure policy + sanitizer adaptation + hashtag removal + write-cap re-verification | Tests incl. contract validation, partial-thread path, and fallback-path-has-no-hashtags; dry-run + live thread inspected |
| 1.5 | Buzz signal: HF Daily Papers + HN + Semantic Scholar fetchers, blended composite, sidecar/ledger fields | Tests incl. per-source failure degradation; live run logs buzz values |
| 3 | **Entry gate:** ≥10 scored Phase-1 runs; set initial `min_score` from the observed distribution (~85th percentile of daily-best composites), not the assumed 7.5. Evening schedule + sidecar gating + no-op observability/alarm + human-lane message + follower-count capture | Tests; force both paths via payload override: `min_score: 11` (must no-op cleanly) and `min_score: 0` (must post) against the live scorer; forced scoring-failure on the evening slot must no-op, not post; evening log shows configured threshold |
| 4 | Analytics dashboard: weekly static HTML report to S3 + digest email; optional Premium CSV import path | Report renders correctly from ledger-only data (no import present); import path joins by tweet id |

Each phase: green tests → changeset deploy → verified live run → commit,
push, tag.

## Success criteria

- Pipeline remains fully autonomous and alarm-quiet; no reliability
  regression.
- Posted threads follow the contract (hook first, no hashtags, link last);
  partial threads are closed or cleaned and ledgered.
- Selection demonstrably prefers lane-relevant papers over "newest."
- Evening slot fires only on persisted scores ≥ threshold; silent no-op
  otherwise, with the no-op observable and alarmed on prolonged silence.
- Ledger carries scores + provenance + follower count, making the 500-follower
  milestone and future calibration checkable without paid reads.
- Owner input remains strictly optional throughout.

### 9. Premium-aware thread limits (designed 2026-07-05, deferred)

Detection rides the existing per-post `GET /2/users/me` call (§4 follower capture
— zero extra API calls): request `verified_type` alongside `public_metrics`;
`verified_type == "blue"` ⇒ Premium. Env `PREMIUM_OVERRIDE` (auto|true|false) for
testing. When Premium: thread-contract limits switch to a tier profile (working
caps well below the raw ~25k — e.g. TWEET_MAX ~4000, HOOK_MAX ~1000; exact caps
get their own A/B — longer ≠ better), the writer prompt gains a premium variant,
validation uses the active profile, and every ledger entry records `account_tier`
so §6 analytics can compare engagement across modes. Goal: the pipeline
self-adapts free → premium → lapsed with ZERO code changes, enabling promotional
trials of Premium against an established baseline. Verify the exact detection
field empirically on the live account before building. Perks in scope: char
limit, reply-priority visibility (growth-relevant), analytics dashboard (§7's
CSV import); edit/media perks out of scope.
