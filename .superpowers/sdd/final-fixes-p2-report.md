# Final Review Fixes — Phase 2 (feat/content-engine-phase2)

## Fix 1: A/B Harness OLD-side v0.9 Fidelity

**Files:** `scripts/ab_writer_eval.py`

- Added `legacy_sanitize_summary` + its constants (`_LEGACY_URL_RE`, `_LEGACY_MENTION_RE`, `_LEGACY_MAX_SUMMARY_CHARS`) as a frozen verbatim copy from `post_to_twitter.py @ e5115538`.
- Rewrote the `generate_pair` OLD side: applies `legacy_sanitize_summary(raw_summary, allowed_url=url)` before `legacy_thread`; parses `raw_tags` from `old_result.get("hashtags", "")` (str → split on comma; list → keep strings); filters with `re.fullmatch(r"#\w+", tag)`; builds `tag_block = ["#AI"] + hashtags[:3]` — no more doubling.
- **New tests (3)** added to `tests/test_ab_harness.py` section [6]: evil-URL+mention+1500-char sanitize; missing-hashtags no-doubling; bad-tag filter.

## Fix 2: Stale `hashtags` Key in Pipeline Controller

**File:** `lambda/pipeline/pipeline_lambda.py` line ~186

- Changed response field `"hashtags": chunker_result.get('hashtags', [])` → `"tweet_counts": chunker_result.get('tweet_counts', [])` to match what summarizer-main now returns.
- Updated both occurrences of `"hashtags": []` in `tests/test_fixes.py` (fake summarizer payloads) → `"tweet_counts": []`.

## Fix 3: Transit Re-check Gains Hook Cap

**File:** `lambda/layers/common/python/utils/post_to_twitter.py`

- Imported `HOOK_MAX` alongside `MIN_TWEETS`, `TWEET_MAX` from `utils.thread_contract`.
- Added `and len(thread[0]) <= HOOK_MAX` to the `ok` expression in the transit re-check block.
- **New test** added to `tests/test_content_engine.py` section [10]: hook of 250 chars (valid ≤280 but >240) → fails transit re-check → summary fallback.

## Fix 4: Clamp MAX_TWEETS

**File:** `lambda/layers/common/python/utils/thread_contract.py`

- Changed `MAX_TWEETS = int(os.getenv("THREAD_MAX_TWEETS", "5"))` → `MAX_TWEETS = max(MIN_TWEETS, int(os.getenv("THREAD_MAX_TWEETS", "5")))`. `MIN_TWEETS` is defined above this line.
- **New assertion** added to `tests/test_thread_contract.py` section [1]: `assert tc.MAX_TWEETS >= tc.MIN_TWEETS`.

## Fix 5: Haiku Deploy Pin

**File:** `samconfig.toml`

- Added `BedrockWriterModelId=us.anthropic.claude-haiku-4-5-20251001-v1:0` to both `[default.deploy]` array and `[default.deploy.parameters]` string, with comment: `# writer pinned to Haiku until Sonnet 4.6 quota approved — flip param, redeploy, re-A/B`.

## Test Results

| Suite              | Result         |
|--------------------|----------------|
| test_fixes         | 17/17 passed   |
| test_content_engine| 33/33 passed   |
| test_buzz          | 11/11 passed   |
| test_thread_contract| 7/7 passed    |
| test_ab_harness    | 18/18 passed   |

**Total: 86/86 passed, 0 failed.**
