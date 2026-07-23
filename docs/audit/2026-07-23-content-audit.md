# Content Audit — 2026-07-23 (posts 2026-07-03 → 2026-07-21)

Sources: posted ledger (14 entries), reconstructed thread text from poster logs
(15 previews incl. dry-runs), pipeline/scraper logs for gap days, schedule state.

## 1. Voice: the "Your/You" formula (owner-flagged — CONFIRMED, severe)

**10 of 15 reconstructed threads open with "Your/You(r)" — and in the v3 era
(07-07 onward) it is effectively 11 of 11** (the one "clean" hook still has
"your" as its second word). Samples back-to-back:

> Your agent is going to fail the task…
> Your agent forgets what it already figured out…
> Your web agent will do whatever a malicious webpage tells it…
> Your RAG system can score zero hallucinations…
> Your per-step safety monitor can pass every single check…
> Your coding agent is re-reading files it already saw…
> Your agent optimizer probably destroys itself…

Root cause: the writer prompt says "Open inside the READER'S world." Each run
is independent, so the model greedy-collapses that instruction to the same
surface form every day. Individually fine; as a timeline, robotic.
Secondary formula: connective crutches ("The core…", "The fix…") in ~4/15.

## 2. Errors / mechanical quality

- Dash tell: ZERO em/en-dashes in any post after the 07-08 fix (flags appear
  only on pre-fix threads). Fix holding in prod.
- Trailing-off: zero after the 07-08 `_untrail`+repack fix. Holding.
- Thread shape: 4-5 tweets, hooks 67-164 chars, middles packed. Healthy.
- **Missed posts: 2 of 14 weekdays** — 07-09 and 07-22, BOTH arXiv throttle.
  07-22 ran the full v0.17.0 hardening (3 retries/lane, backoff) and still got
  zero results, then failed LOUDLY (SNS at 16:02 UTC) — alerting works; posts
  still lost. 07-11/07-18 are Saturdays (schedule fine). Schedules ENABLED.

## 3. Engagement (free-tier signal only: follower count at post time)

20 (07-06) → 19 (07-10) → 18 (07-13 onward). **Flat-to-declining across 15
days of daily posting.** No like/reply/impression data on free tier. Honest
read: broadcast-only + one formula opener is not converting; nothing here
says the content engine's quality gates are wrong, but nothing says the
timeline is winning either. The voice fix is the cheapest big lever.

## 4. Media/figures

Media-era posts: 10. **4 ATTACHED (40% — right at the 45% calibration)**,
2 blocked by the CC-only license gate, 4 legitimately no qualifying figure.
Feature working as designed. Owner lever: dropping the license gate would
have roughly +2 attachments (66% of the no-attach days were license/none).

## 5. Diversity

- Lanes: agents 7 (58%), ai-security 3, llm-systems 2 — agents dominates.
- Topics: heavy overlap (agent memory/safety/injection × several posts).
- Composite scores cluster hard at 8.1/8.35 (Haiku scoring compression) —
  the gate discriminates weakly within the pool.
- Combined with the identical opener, consecutive posts read near-identical.

## 6. Recommendations (owner decisions)

1. **Hook-form rotation (fix the formula).** Day-seeded style selection in the
   summarizer: rotate ~6 distinct opener FORMS (concrete-number-first,
   scene/incident-first, bold-claim-first, contrast-first, finding-quote-first,
   second-person [rationed, not banned]) via date hash → passed into
   build_writer_prompt. Deterministic, testable, needs no cross-run state.
   Also ban the "The core/The fix" connective openers on middle tweets.
2. **arXiv resilience (2 lost weekdays/2 weeks).** Short term: shift cron off
   the top-of-hour peak (e.g. 16:07). Medium term: replace HTML-search
   scraping with the export.arxiv.org Atom API (designed for programmatic
   use, separate rate limits) — feature-sized, needs a spec.
3. **License gate revisit (owner call):** CC-only cost 2 image days out of 10.
4. Make-up post for 07-22 once (1) ships — owner-triggered.
5. (Observation only) Follower growth likely needs activity beyond broadcast;
   out of pipeline scope.
