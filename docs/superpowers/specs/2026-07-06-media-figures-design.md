# Media/Figures Feature — Design Spec

**Date:** 2026-07-06 · **Baseline:** main @ v0.13.0 · **Branch:** `feat/media-figures` · **Ships as:** v0.14.0

**Goal:** attach the paper's key figure to the hook tweet of each posted thread — the largest remaining engagement lever after voice v2. Adversarially reviewed (4-lens panel, 2026-07-06: 11 blockers/12 important/7 minor raised; 1 blocker rejected as a misreading, all others folded in below). Entitlement **probe-verified on the live account**: v1.1 `media_upload` + `create_media_metadata` both succeed with the existing `TwitterAPICreds`.

## Owner decisions

- Figure attaches to the **hook tweet (tweet 1) only**.
- The **writer picks** the figure from a pre-gated caption list inside its existing single LLM call (`"figure": <index|null>` in the writer JSON).
- Ship gate: stub tests + deployed dry-run + **owner's eye on the first live post**; `MediaEnabled` defaults **"false"** (ship dark, flip after the watched post).
- **License gate ON:** figures attach only from CC-licensed papers (BY / BY-SA / BY-NC / CC0 / public domain). Non-CC (incl. arXiv default license) → text-only post; license class recorded in the ledger either way. *(Owner may strike this section during spec review to trade gray-area risk for attach-rate.)*

## Architecture

Three touch points, one new module. Summarizer selects; poster uploads and attaches; everything else unchanged.

```
summarizer worker                          poster
  fetch_figures(url) ──► gates ──► writer    download chosen image ──► v1.1 upload
  [figures.py]          (dim/    picks       (guards)                 (+alt text)
                        license) index                                  │
        └── figure {url, caption, license} on article dict ──► media_id → tweet 1
```

## 1. `utils/figures.py` (new)

`fetch_figures(arxiv_abs_url) -> {"figures": [{index, url, caption, width, height}], "license": str|None, "reason": str|None}`
— a single return object so the license class reaches the ledger even when figures are empty (reason ∈ {no_html, no_candidates, license, fetch_error, ...}). At most the first 4 qualifying `<figure>` candidates are dimension-probed. Only called when `MEDIA_ENABLED` is truthy (worker checks the env before any fetch). Uses `requests` + `bs4` (bs4 must be ADDED to `lambda/summarizer/requirements.txt` — review finding: it is not currently in that bundle; verify `sam build` packages it).

- **Fetch:** `https://arxiv.org/html/<id>` **unversioned** (redirects to latest — hardcoding v1 serves stale figures for revised papers). One GET, 10s timeout, browser UA. Read the resolved version from the final URL.
- **Figure candidates:** only `<figure>` elements whose `<figcaption>` text starts with `Figure` (case-insensitive) AND that contain an `<img>`. Review evidence: 3/10 real papers wrap **tables/algorithm listings** in `<figure>` first — caption-prefix filtering excludes them.
- **URL resolver (review blocker — two src conventions exist):** given page final URL `https://arxiv.org/html/<id>v<n>` and img `src`:
  1. if `src` starts with `http` → use as-is (must be `arxiv.org` host, else drop);
  2. else strip any leading `<id>v<n>/` prefix from `src`, then join to `https://arxiv.org/html/<id>v<n>/` (trailing slash mandatory).
  Pinned by tests using BOTH observed forms: `2607.02116v1/figures/cn-in-agent-stack.jpg` and bare `x1.png` (paper 2511.04694 style).
- **Dimension gate (review blocker — caption-blind selection):** ranged GET (first 64KB) per candidate image; parse width/height from PNG IHDR / JPEG SOF header bytes (stdlib only, no PIL). Drop: aspect ratio <1.2 or >2.0, width <900px, or unparseable. Format allowlist png/jpg/webp (SVG measured at 0/78 real figures — allowlist is insurance, no conversion machinery).
- **Caption cleaning (review: MathML doubling verified live):** remove `<math>`/`<annotation>` subtrees before `get_text()`, collapse whitespace, truncate to 400 chars. Test fixture: paper 2607.01600's caption must not contain `\leq` or doubled `p<0.001`.
- **License:** parse the license link from the fetched HTML page (arXiv pages carry it); always return the class string in the result object. If the license gate is on and the class is not CC → `figures: []`, `reason: "license"`.
- **Politeness:** ≤1 HTML GET + ≤4 ranged image GETs per posted article, browser UA, no retries; any 403/429/503 from arXiv → `[]` with reason. Image URLs only ever constructed on `arxiv.org` (SSRF containment).

## 2. Writer integration (`thread_contract.py`, `summarizer.py`)

- `build_writer_prompt(article, figures=None)`: when gate-passing figures exist, append a numbered caption list plus: *"Optionally pick ONE figure whose visual would stop a scroll at thumbnail size — return its number as `figure`. Default to `null`; prefer null over a weak pick; dense multi-panel grids are weak picks."* (Null-default framing is the review's anti-eagerness fix; zero gate-passing figures forces null **in code**, deterministically.)
- Writer JSON gains optional `"figure": <int|null>`. `write_thread_with_claude` validates index-in-range else null. `validate_and_repair` untouched (figure is not a tweet).
- **Placement of data (review finding):** the chosen `figure` dict `{url, caption, license, width, height}` is written onto the **article dict** by the summarizer (survives the summarizer→chunk→poster merge; the writer return only carries the index). Exact-keys assertions in `test_content_engine.py` updated accordingly.

## 3. Poster (`post_to_twitter.py`, `tweepy_client.py`)

- **New v1.1 subsystem (review blocker — v2 `Client` has zero media methods):** `tweepy_client.py` gains `get_v1_api()` building `tweepy.API(OAuth1UserHandler(consumer_key, consumer_secret, access_token, access_token_secret))` from the same lazily-loaded secrets. `upload_media(image_bytes, filename, alt_text) -> media_id` = `media_upload` + `create_media_metadata` (probe-verified on tweepy 4.15.0 pin).
- **Download guards:** GET the chosen figure URL (15s timeout); require `Content-Type: image/*`, size 10KB–4.9MB; failure → text-only.
- **Ordering/retry invariant (review blocker):** upload happens ONCE, before the posting loop; media_id memoized; tweet 1's initial attempt AND its single retry pass the SAME media_id; no re-upload ever; the mid-thread closing-reply path never carries media. Test: force tweet-1 first-attempt failure, assert exactly one upload and media on the retried tweet 1.
- `post_tweet()` gains optional `media_ids` param; `post_thread` passes it only for index 0. `dry_run` logs the resolved figure URL + "would upload" line in the Tweet Thread Preview block and skips the upload entirely.

## 4. Config & rollout

- `MediaEnabled` template param (String `"true"/"false"`, **default `"false"`**) → env `MEDIA_ENABLED` on SummarizerFunction (worker) and PosterFunction. samconfig + deploy-full-stack.sh updated in lockstep (full-override-list rule).
- Rollout: deploy dark → dry-run (verify figure selection + would-upload logs) → owner-watched manual live post → flip param to "true" via param-only redeploy.

## 5. Failure philosophy (invariant, unchanged from draft)

No-HTML (~8% of real candidates, measured), zero qualifying figures, non-CC license, writer null, download/guard/upload failure — every branch posts **exactly today's text-only thread**, logs a structured reason, never aborts. The no-figure path is the default outcome, not an exception.

## 6. Observability

Ledger/metadata gains `media: {attempted, figure_url, license, uploaded, attached, skip_reason}`. One structured log line per article (`MEDIA attached` / `MEDIA skipped: <reason>` / `MEDIA failed: <stage>`). Weekly report (P4) gains a media-outcome count row so "media never fires" is visible without log spelunking.

## 7. Testing

Dependency-free suites (house pattern). FAKE_HTTP gains `arxiv.org/html` fixture routes (fixtures modeled on the probed real papers incl. a table-first `<figure>`, both src conventions, MathML caption, non-CC license page); fake tweepy gains `media_upload`/`create_media_metadata` capture. Coverage: resolver (both forms + http + foreign-host drop), candidate filter (table/algorithm exclusion), dimension gate (aspect/width/parse-fail), caption cleaning, license gate, forced-null on zero candidates, index-out-of-range, article-dict carriage through merge, poster guards, upload-once/retry invariant, hook-only attachment, dry-run logging, kill switch off = zero fetches.

## 8. Out of scope (YAGNI, explicit)

PDF figure extraction / page rendering; SVG conversion; generated title-card images; multi-image posts; media on non-hook tweets; S3 image staging; Premium-tier media features; engagement-metric collection (needs paid reads — `media.attached` in the ledger is the hook for later correlation with follower deltas).

## Adjudication note

The integration lens's "abs pages contain no figures — premise fails" blocker was **rejected**: the design fetches `/html/` renderings (probe-verified figures on 9/10 recent lane papers), not `/abs/` pages. All other blockers accepted and reflected above.
