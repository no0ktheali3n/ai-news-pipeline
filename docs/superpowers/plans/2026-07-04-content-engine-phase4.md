# Content Engine Phase 4 — Self-Built Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture the free outcome signal (follower count per post) before more data is lost, and ship a weekly Lambda that renders a static HTML analytics report to S3 (top posts by follower delta, lane performance, buzz-vs-outcome, follower curve, run/post stats) and emails a digest + presigned link via a NON-failure SNS topic. Zero LLM calls anywhere in this phase.

**Architecture:** Poster gains a non-blocking `get_follower_count()` (tweepy `get_me`, errors → None) and stores `follower_count` + `tweet_count` in each ledger entry. A new `ReporterFunction` (weekly EventBridge schedule) reads the posted ledger + scored sidecars from S3, computes aggregates in a pure module, renders dependency-free HTML (inline CSS + one SVG sparkline), writes it under `output/reports/`, and publishes a one-paragraph digest with a 7-day presigned URL to a new `ReportTopic` (distinct subject prefix; never the failure AlertTopic — spec §1/§4 rule).

**Tech Stack:** Python 3.12, stdlib only for aggregates/HTML (no jinja/pandas), Tweepy (existing), AWS SAM. No new pip dependencies.

## Global Constraints (spec §4 + §6)

- **Follower capture is strictly non-blocking:** any tweepy/API failure logs and yields `follower_count: None` — it can NEVER fail or delay a post. Free-tier budget: `GET /2/users/me` ≤ 25 req/24h; we make ≤ 2/day.
- **Log now, dashboard later:** ledger entries gain `follower_count` (int|None) and `tweet_count` (int) from the moment Task 1 deploys — the dashboard renders gracefully from day one with sparse/None data (every aggregate must tolerate missing fields on OLD entries; never KeyError on pre-Phase-4 entries).
- **The digest goes to a NEW SNS topic** (`ReportTopic`, subject prefix `[report]`), never `AlertTopic`. Owner must confirm the email subscription once.
- Report artifacts live under a NEW prefix `output/reports/` — scanned by nothing (chunker scans scraper prefix, poster scans summarizer prefix).
- Reports are static HTML, self-contained (inline CSS, inline SVG, zero JS, zero external requests) — they must render from a presigned S3 URL in any browser.
- The paid-analytics milestone check (spec: 500 followers) appears in the digest when follower data exists.
- Tests: dependency-free scripts via `uv run python tests/test_analytics.py` (new suite; stubs from tests/stubs.py — FakeTweepy needs a `get_me` addition). All 5 existing suites stay green.
- All work on branch `feat/content-engine-phase4` (created off the `feat/content-engine-phase2` tip — Phase 4's poster edits touch files Phase 2 changed; merge order is 1.5 → 2 → 4).
- **Deploy sequencing (Task 6 gate):** Phase 4 deploys only AFTER Monday's autonomous run is verified AND Phase 2's deploy has survived a scheduled run (one new variable per autonomous run — the poster follower-capture is in the posting path). Target version v0.11.0.

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `lambda/layers/common/python/utils/tweepy_client.py` | Modify | `get_follower_count()` — lazy-creds, non-blocking |
| `lambda/layers/common/python/utils/post_to_twitter.py` | Modify | metadata gains `follower_count` + `tweet_count` |
| `lambda/poster/poster_lambda.py` | Modify | ledger entry stores both fields |
| `lambda/layers/common/python/utils/analytics.py` | Create | Pure aggregates from ledger entries + sidecar listing |
| `lambda/layers/common/python/utils/report_html.py` | Create | Aggregates → self-contained HTML string |
| `lambda/reporter/reporter_lambda.py` | Create | Weekly handler: read S3 → aggregate → render → write → presign → SNS |
| `tests/test_analytics.py` | Create | All Phase 4 tests |
| `tests/stubs.py` | Modify | FakeTweepy `get_me`; FakeS3 `generate_presigned_url` |
| `template.yaml` | Modify | ReporterFunction + weekly schedule + ReportTopic + IAM + envs |

---

### Task 1: Follower + thread-shape capture in the poster

**Files:** Modify `tweepy_client.py`, `post_to_twitter.py`, `poster_lambda.py`; extend `tests/test_content_engine.py` provenance tests; Modify `tests/stubs.py`.

**Interfaces produced:** `tweepy_client.get_follower_count() -> int | None`; `post_thread` metadata gains `"follower_count"` and `"tweet_count": len(tweet_ids)`; ledger entries store both.

Steps (TDD, mirroring the Phase 2 Task 4 test style):
1. Stub: give the fake tweepy client a `get_me` returning `{"data": {"public_metrics": {"followers_count": 42}}}`-shaped object matching real tweepy (`resp.data.public_metrics["followers_count"]` — read tweepy_client.py first to mirror how the real client object is used, then shape the fake accordingly) plus a `FAKE_TWEEPY.get_me_error` flag to simulate failure.
2. Failing tests: (a) successful post metadata has `follower_count == 42` and `tweet_count == 3`; (b) with `get_me_error` set, metadata has `follower_count is None` and the post still succeeds; (c) ledger entry stores both (extend `test_ledger_entry_carries_provenance`).
3. Implement `get_follower_count()` in tweepy_client (call AFTER `_ensure_twitter_creds`; wrap everything in try/except → None with one warning log). Call it in `post_thread` ONCE after the posting loop (both `posted` and `partial` paths), never before/during.
4. All suites green; commit `feat: capture follower_count + tweet_count into the posted ledger`.

### Task 2: Pure aggregates — `utils/analytics.py`

**Interfaces produced:**
- `load_entries(ledger: dict) -> list[dict]` — ledger is `{url: entry}`; returns entries sorted by `posted_at`, each with `url` injected.
- `follower_series(entries) -> list[tuple[str, int]]` — (posted_at, follower_count) for entries with counts.
- `post_deltas(entries) -> list[dict]` — per post: title, url, composite, buzz, delta (follower_count − previous post's count; None when either side missing).
- `lane_stats(entries) -> dict[str, dict]` — per lane (first `query_source` element, `"unknown"` fallback): posts, avg composite (2dp).
- `buzz_outcome(entries) -> dict` — counts + avg delta for buzzed vs unbuzzed posts (None-tolerant).
- `run_stats(n_sidecars: int, entries) -> dict` — runs seen, posts made, posts with `status:"partial"`.
- ALL functions must return sensible empties for `entries=[]` and tolerate entries missing ANY Phase-4/1.5/1 field (old-format entries have none of them).

TDD: failing tests with a fixture ledger of 4 entries (one old-format with only title/posted_at, one unbuzzed, two buzzed with follower counts) asserting exact values incl. the None-delta cases; then implement; commit `feat: analytics aggregates (pure, sparse-tolerant)`.

### Task 3: HTML renderer — `utils/report_html.py`

**Interface:** `render_report(agg: dict, generated_at: str) -> str` where `agg` bundles Task 2's outputs (`{"series": ..., "deltas": ..., "lanes": ..., "buzz": ..., "runs": ..., "milestone": {"target": 500, "current": int|None}}`).

Requirements: single `<html>` string; inline CSS only; sections render "collecting data — N posts so far" placeholders when their input is empty/None; follower curve as inline SVG polyline (points scaled into a 600×120 viewBox; skip the SVG entirely for <2 points); a top-posts table sorted by delta desc (None deltas last); no external URLs except post links to twitter.com. TDD: assert placeholder text on empty agg; assert `<svg` present with 2+ points and absent with <2; assert a known delta lands in the table row; assert `"http"` occurs only in allowed link hrefs. Commit `feat: self-contained HTML report renderer`.

### Task 4: Reporter Lambda — `lambda/reporter/reporter_lambda.py`

Handler flow (mirror poster_lambda's S3/env conventions — read it first):
1. Env: `S3_OUTPUT_BUCKET`, `MEMORY_OUTPUT_PREFIX`, `POSTED_LEDGER_FILE`, `SCORED_OUTPUT_PREFIX`, `REPORTS_OUTPUT_PREFIX`, `REPORT_TOPIC_ARN`.
2. Read ledger (tolerate missing → empty report, still publish digest saying "no posts yet"); count sidecar objects via paginator (runs).
3. Aggregate (Task 2) → render (Task 3) → `put_object` to `{REPORTS_OUTPUT_PREFIX}report_{YYYY-MM-DD}.html` (ContentType `text/html`) → `generate_presigned_url` (`ExpiresIn=604800`).
4. Digest: one paragraph — posts this period/total, current followers (or "not yet captured"), best post title+delta, milestone progress (x/500) — `sns.publish` to `REPORT_TOPIC_ARN` with subject `[report] ai-research-pipeline weekly`.
5. Any per-section failure degrades (log + placeholder), only S3-read-of-nothing + SNS-publish failure may raise (alarm-worthy).
TDD via stubs (FakeS3 needs `generate_presigned_url` returning a deterministic URL; FAKE_SNS already records publishes): happy path writes HTML + publishes digest containing the presigned URL; empty-ledger path publishes "no posts yet". Commit `feat: weekly reporter lambda`.

### Task 5: Template wiring

- `ReportTopic` (SNS) + email subscription to the existing `AlertEmail` param value, `DisplayName` distinct from AlertTopic.
- `ReporterFunction`: CodeUri `lambda/reporter/`, handler `reporter_lambda.handler`, layer ref, envs from step 4.1 (`REPORTS_OUTPUT_PREFIX` default `ai-research-pipeline/output/reports/`), policy: S3 Get/List on ledger+scored prefixes, Put on reports prefix, `sns:Publish` on `ReportTopic` ONLY.
- Schedule: `ReporterSchedule` (EventBridge Scheduler, like PipelineSchedule) `cron(0 17 ? * SUN *)`, RetryPolicy MaximumRetryAttempts 0, reusing `SchedulerInvokeRole` pattern (check whether that role's policy is function-scoped — if so, add the reporter ARN or a second role; read the existing role definition first).
- `sam validate --lint`; all suites; commit `infra: weekly reporter — function, schedule, report topic`.

### Task 6: Deploy + verify (CONTROLLER-RUN; sequenced)

**GATES:** Monday 2026-07-06 autonomous run verified AND Phase 2 deployed + survived one scheduled run. Then: two-step changeset deploy → confirm the ReportTopic subscription email (owner clicks) → manually invoke ReporterFunction once (zero Bedrock; it only reads S3 + sends email) → verify HTML renders from the presigned link + digest email arrived → lifecycle rule consideration for `output/reports/` (90d, owner-approved same as before) → version 0.11.0 + `uv lock`, FIX_NOTES note, tag, push, merge after final review.

---

## Self-Review

- **Spec coverage:** §4 follower capture (T1, incl. ≤25/day budget note, non-blocking rule); §6 signal classes 1+2 (T1/T2), owner CSV import explicitly DEFERRED (spec marks it optional; revisit with Premium), weekly static report + digest via non-failure channel (T3/T4/T5), milestone-500 in digest (T4), "log every field the dashboard needs" (T1 adds the two missing fields; hook-length deferred until a dashboard section needs it — noted, not silent).
- **Placeholder scan:** interface contracts are exact; implementer reads named files for local conventions (tweepy client object shape, poster env/S3 patterns, scheduler role scoping) — flagged explicitly per task. No TBDs.
- **Type consistency:** `follower_count: int|None` and `tweet_count: int` named identically in T1 metadata, T1 ledger, T2 aggregates, T3 renderer input; `REPORTS_OUTPUT_PREFIX`/`REPORT_TOPIC_ARN` identical in T4 code and T5 template.
