# Content Engine — Design

**Date:** 2026-07-03 · **Status:** approved (design) · **Baseline:** v0.7.0

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
- **No paid X API reads.** Posting is free-tier; reading metrics is not.
  Analytics-by-API is milestone-gated ("buy the data when there's an audience
  worth measuring"). Nothing in this design may depend on reading metrics.
- **Never regress reliability.** The v0.7.0 guarantees stand: posted-ledger
  dedup, poster gating, freshness guards, alerting, injection guard.
- Cost envelope: a few Bedrock calls/day (Haiku for scoring, Sonnet-tier for
  writing). Cents per day.

## Design

### 1. Selection: score, don't sort

- Scraper queries **three lane-defining arXiv searches** (exact query strings
  tuned during implementation): AI security/safety of LLMs and agents;
  agents/tool-use/multi-agent; LLM systems/ops. Results merged, deduped by
  URL, ledger-filtered. Target ~40 candidates/run.
- **One batched Haiku call** scores all candidates on a practitioner rubric:
  `builder_relevance`, `novelty`, `hook_potential` (each 0–10) → composite
  `0.5*relevance + 0.25*novelty + 0.25*hook` (starting weights; env-tunable).
  Truncated title+abstract per candidate; JSON array out.
- Post the top-scoring unposted candidate. Scores + query-source are stored in
  the scraped file and carried into the posted ledger (analytics-ready).
- **Fallback:** any scoring failure (Bedrock error, parse failure, empty
  result) reverts that run to v0.7.0 behavior (newest unposted). The daily
  post never depends on the scoring path. Fallback use is logged and alerted
  at WARN level (webhook only, not email).

### 2. Second slot: the ledger is the queue

- A **second EventBridge schedule** (~20:00 UTC / 4pm ET weekdays) invokes the
  same pipeline with `min_score` in its payload (starting threshold: 7.5
  composite; adjustable in the schedule Input without redeploying code).
- Because the noon winner is already in the ledger, the evening run naturally
  evaluates the runner-up; it posts **only if** the best remaining candidate's
  composite score ≥ `min_score`. Otherwise it exits cleanly ("no candidate
  cleared the bar" — a no-op, not an error).
- No queue infrastructure, no new state, posts spaced by hours.
- The noon run carries `min_score: 0` semantics (always posts its best
  available candidate) to preserve daily cadence.

### 3. Voice: structured thread contract

- The writer prompt is rebuilt around the practitioner-curator voice. The
  model returns a **structured thread**, not a text blob:
  `{"tweets": ["...", ...]}` with contract: tweet 1 = hook ≤ 240 chars,
  **no link**; middle tweets = substance with explicit builder-relevance
  ("why this matters if you deploy/build X"); final tweet = paper title +
  arXiv link. 3–5 tweets total.
- **No hashtags.** `DEFAULT_HASHTAGS` and the hashtag block are removed from
  posted output (rubric may still use topical tags internally for scoring).
- **Models:** scoring = Haiku (`BedrockModelId` param, current default);
  writing = Sonnet-tier via a new `BedrockWriterModelId` template parameter.
  Existing IAM wildcards already cover both.
- The poster's injection-guard sanitizer moves to per-tweet validation
  (foreign-URL strip, mention defang, length caps) against the new contract;
  contract violations (e.g., link in tweet 1) are repaired if trivial
  (strip) or fail the article (fallback to old formatter) if not.

### 4. Human lane: optional by construction

- When an evening (high-potential) post goes out, publish to the existing SNS
  topic: thread URL + a model-drafted one-line personal take suitable for a
  quote-tweet. Owner may use it or ignore it; nothing waits on a response.

### 5. Out of scope (explicitly deferred)

- Paid X API metrics / engagement feedback loop (milestone: revisit at
  meaningful follower count).
- Cross-posting (Bluesky/LinkedIn), weekly roundups, images/figures.
- Posting-time optimization beyond the two fixed slots.

## Rollout

| Phase | Contents | Verification |
|---|---|---|
| 1 | Multi-query scrape + batched scoring + fallback + score-carrying ledger | Tests; live run shows scored selection; observe several days |
| 2 | Thread contract + writer model + sanitizer adaptation + hashtag removal | Tests incl. contract validation; dry-run + live thread inspected |
| 3 | Evening schedule + `min_score` gating + human-lane email | Tests; forced high/low-score runs; confirm no-op path |

Each phase: green tests → changeset deploy → verified live run → commit,
push, tag. Same discipline as v0.7.0.

## Success criteria

- Pipeline remains fully autonomous and alarm-quiet.
- Posted threads follow the contract (hook first, no hashtags, link last).
- Selection demonstrably prefers lane-relevant papers over "newest."
- Second slot fires only on high scores; silent no-op otherwise.
- Owner input remains strictly optional throughout.
