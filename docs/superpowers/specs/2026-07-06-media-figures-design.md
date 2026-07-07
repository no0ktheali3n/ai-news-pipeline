# Media/Figures Feature — Design Spec (rev 2)

**Date:** 2026-07-06 (rev 2 same day) · **Baseline:** main @ v0.13.0 · **Branch:** `feat/media-figures` · **Ships as:** v0.14.0

**Goal:** attach the paper's key figure to the hook tweet of each posted thread — the largest remaining engagement lever after voice v2.

**Review provenance:** design adversarially reviewed (4 lenses, 11/12/7 findings), then this spec adversarially reviewed again (4 lenses, 6 blockers/10 important/7 minor) — rev 2 folds in all accepted findings. Media-upload entitlement **probe-verified on the live account** (v1.1 `media_upload` + `create_media_metadata` succeed with `TwitterAPICreds`). Rev-2 reversal of a rev-1 claim: unversioned `https://arxiv.org/html/<id>` does **not** redirect to a versioned URL — the version lives in the img `src` prefixes, and the resolver below is built on that.

## Owner decisions

- Figure attaches to the **hook tweet (tweet 1) only**.
- The **writer picks** the figure from a pre-gated caption list inside its existing single LLM call.
- Ship gate: stub tests + deployed dry-run + **owner's eye on the first live post**; `MediaEnabled` defaults **"false"**.
- **License gate ON:** attach only from CC-licensed papers (BY / BY-SA / BY-NC / CC0 / public domain); everything else — including arXiv's default perpetual license and unknown/unparseable — posts text-only, license class recorded in the ledger. *(Owner may strike during review.)*

## Architecture

```
summarizer worker                             poster
  fetch_figures(url)  ─► license+dim gates    download chosen image ─► guards
  [figures.py]         ─► writer picks index  ─► upload_media (v1.1, once)
        └─ figure dict onto article ──────────► media_id on tweet 1 (+retry, same id)
```

## 1. `utils/figures.py` (new; lives in the common layer)

```
fetch_figures(arxiv_abs_url: str) -> dict
# {"figures": [{"index", "url", "caption", "width", "height"}],
#  "license": str|None,        # always populated when the page parsed
#  "reason": str|None}         # None on success with candidates; else one of:
#  no_html | no_candidates | license | fetch_error | parse_error
```
Never raises; any internal failure → `{"figures": [], "license": <best-effort>, "reason": ...}`. Called ONLY when `MEDIA_ENABLED` is truthy (caller checks env first). Deps: `requests` + `bs4` — **`beautifulsoup4` must be added to `lambda/summarizer/requirements.txt`** (spec-review verified it is absent from that bundle); plan includes a sam-build smoke check that `import bs4` works in the built summarizer artifact.

- **Fetch:** `https://arxiv.org/html/<id>` unversioned (serves the current rendering; probe-verified it does NOT redirect — do not expect a versioned final URL). One GET, 10s timeout, browser UA, no retries; 403/429/503 → `reason: fetch_error`.
- **License (spec-review blocker — the href is generic, the class is anchor TEXT):** select the anchor `a#license-tr` (stable id, present on all probed pages) — or, fallback, the `<a>` whose href contains `info.arxiv.org/help/license` — and classify from its **stripped text** (`"License: CC BY 4.0"` → CC; substring map: `CC BY`/`CC BY-SA`/`CC BY-NC`/`CC0`/`public domain` → CC set; anything else incl. "arXiv.org perpetual" → non-CC). **Whole-page regex is forbidden** — probed papers carry `CC-BY-4.0` strings as *table data* (fixture asserts those are not picked up). Anchor absent/unparseable → `license: "unknown"`, treated as non-CC while the gate is on.
- **Figure candidates:** `<figure>` elements whose `<figcaption>` text starts with `Figure` (case-insensitive) AND that contain **exactly one** `<img>` (spec-review: multi-`<img>` subfigure grids yield a single sub-panel fragment — excluded; "(a)/(b)" subcaption starts likewise never qualify). First **4** qualifying candidates are considered.
- **URL resolver (both reviews; three observed src forms, all pinned by tests):**
  1. `src` starts with `http` → use as-is only if host is `arxiv.org`, else drop the candidate;
  2. `src` carries a `<id>v<n>/` leading segment (the version's actual home) → resolve as `https://arxiv.org/html/` + `src`;
  3. otherwise (bare `x1.png`, `extracted/<n>/images/...`) → resolve as `<response.url rstrip '/'>` + `/` + `src`.
  The resolved URL must then GET as `200` with `Content-Type: image/*` — the fetch below is the final arbiter; 404 → drop the candidate.
- **Dimension gate (recalibrated — rev-1 numbers rejected ~75% of real good figures, incl. 2 of 3 fixture papers):** full GET per candidate (10s timeout, read capped at 2MB — ranged-GET machinery dropped per YAGNI review; real figures measured < 1MB), parse width/height from PNG IHDR / JPEG SOF bytes (stdlib). Drop: aspect ratio < 1.0 or > 3.0, width < 600px, or unparseable. **Plan task: re-measure the pass-rate on a ~20-paper sample and tune before locking; target 40–70% of figure-bearing papers passing.** Format allowlist png/jpg/webp.
- **Caption cleaning:** remove `<math>`/`<annotation>` subtrees before `get_text()`, collapse whitespace, truncate to 400 chars. Fixture: paper 2607.01600's caption must not contain `\leq` or doubled `p<0.001`.
- **Politeness/SSRF:** ≤1 HTML GET + ≤4 image GETs per posted article, browser UA, no retries; image URLs only ever on `arxiv.org`.

## 2. Summarizer wiring (spec-review blocker — previously unspecified; exact contract)

- `summarize_articles` (summarizer.py, in the per-article loop): before the writer call, compute
  `fig_result = figures.fetch_figures(article["url"]) if os.getenv("MEDIA_ENABLED","false") == "true" else {"figures": [], "license": None, "reason": "disabled"}`.
- `write_thread_with_claude(article, figures=None)` — signature gains the optional list; passes it to `build_writer_prompt(article, figures=figures)`; validates the writer's returned `"figure"` index (int, in-range, else None) and **resolves it to the figure dict itself**, returning `{"tweets", "summary", "figure": <dict|None>}`.
- `summarize_articles` spreads onto the output article (the existing `{**article, ...}` merge): `"figure": result["figure"]` and `"media_license": fig_result["license"]`, plus `"media_reason": fig_result["reason"]` when no figure. (No exact-key-set assertion exists in the tests — rev-1's claim corrected; membership tests are unaffected. A positive assertion that `figure` is present when picked is ADDED.)
- `build_writer_prompt(article, figures=None)`: when non-empty, append the numbered caption list plus: *"Optionally pick ONE figure whose visual would stop a scroll at thumbnail size — return its number as `figure`. Default to `null`; prefer null over a weak pick; dense multi-panel grids are weak picks."* Zero candidates → the parameter is None and the prompt is byte-identical to today's (existing prompt tests unaffected).

## 3. Poster

- **v1.1 subsystem** (`tweepy_client.py`): `get_v1_api()` — calls `_ensure_twitter_creds()`, builds `tweepy.API(tweepy.OAuth1UserHandler(TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET))`, constructed per call (matches the existing non-cached client pattern). `upload_media(image_bytes, filename, alt_text) -> media_id|None` — exact calls: `api.media_upload(filename=filename, file=io.BytesIO(image_bytes))` then `api.create_media_metadata(media.media_id, alt_text=alt_text[:1000])`; **returns None on ANY exception (never raises)** — metadata failure alone still returns the media_id (alt text is best-effort). tweepy pin: **bump `lambda/poster/requirements.txt` to `tweepy==4.17.0`** (the version the entitlement probe actually ran on); media methods re-verified at build.
- **Poster flag semantics (mixed-state rule):** the poster attaches iff `article["figure"]` is present and well-formed **AND its own `MEDIA_ENABLED` is true** — the summarizer flag gates fetching, the poster flag is the kill switch with immediate effect. Every mixed state during a param flip is safe: worst case is a fetched-but-unattached figure (logged `skip_reason: disabled`).
- **Download guards:** GET figure URL (15s timeout); require `Content-Type: image/*`, 10KB–4.9MB; any failure → text-only, `skip_reason` recorded.
- **Upload-once invariant:** upload happens once in `post_thread` BEFORE the posting loop; media_id memoized; tweet 1's initial attempt AND its single retry pass the SAME id; no re-upload; the closing-reply path never carries media. `run_posting_pipeline` does not retry `post_thread` itself (verified) — the invariant holds at one level.
- `post_tweet(text, reply_to_id=None, media_ids=None)`; `post_thread` passes `media_ids` **only when non-None and only for index 0** (unpatched call shape preserved for every other call). The 4 explicit-signature test fakes (test_content_engine.py:550/571/587/607) gain `media_ids=None` and assert None off-hook / the id on-hook.
- **dry_run:** logs resolved figure URL + a "would upload" line inside the Tweet Thread Preview block; upload skipped entirely.

## 4. Config & rollout

- `MediaEnabled` template param (String, **default "false"**) → env `MEDIA_ENABLED` on SummarizerFunction (worker) AND PosterFunction. Added with value `"false"` to BOTH samconfig.toml parameter_overrides and deploy-full-stack.sh in the same commit (full-override-list rule); the flip to `"true"` is an edit of that value + re-run of the SAME full-override deploy path — never a partial override.
- **Rollout order:** deploy dark → dry-run (verify figure selection + would-upload logs) → **manual live post, exact procedure:** flip `MediaEnabled=true`, then invoke PipelineFunction once outside the posting window with `{"skip_memory": true, "scrape_limit": 10, "max_new_articles": 1, "chunk_size": 1, "dry_run": false}` — a fresh figure-bearing summarized file is produced and posted in the same run (satisfies the 6h freshness guard; posted-ledger dedup prevents re-posting it at the next scheduled run). Owner inspects the live tweet; param stays true or is flipped back.
- **Timeout budget note:** SummarizerFunction Lambda Timeout is 600s while `summarize_articles`' internal `max_runtime` default is 900s (pre-existing mismatch, now documented); media adds worst-case ~50s/article (1×10s HTML + 4×10s images). The plan pins figures-fetch timeouts and leaves the Lambda timeout unchanged.

## 5. Failure philosophy (invariant)

No-HTML (~8% measured), zero qualifying candidates, non-CC/unknown license, writer null, download/guard/upload failure, flag off — **every branch posts exactly today's text-only thread**, logs a structured reason, never aborts. The no-figure path is the default outcome, not an exception.

## 6. Observability & ledger (plumbing enumerated — spec-review found it promised but unwired)

- `post_thread`'s returned metadata gains `"media": {attempted, figure_url, license, uploaded, attached, skip_reason}`.
- `record_posted` persists `media` into the posted ledger.
- `analytics.py` gains `media_stats(entries)` using `entry.get("media", {})` — **tolerant of pre-media ledger entries** (named back-compat test).
- `report_html.render_report` gains a media-outcomes section (attached / skipped-by-reason counts).
- One structured log line per article: `MEDIA attached` / `MEDIA skipped: <reason>` / `MEDIA failed: <stage>`.

## 7. Testing (harness work called out as real tasks, not footnotes)

**Stub extensions (prerequisite task):** `stubs.py` fake tweepy gains `tweepy.API`, `tweepy.OAuth1UserHandler`, `media_upload(filename=, file=) -> obj with .media_id`, `create_media_metadata(media_id, alt_text=)` — all capturing calls; `_HttpResp` gains `.content` (bytes), `.text`, `.headers` (incl. Content-Type) so FAKE_HTTP can serve HTML fixtures and image bytes.

**Fixtures (modeled on probed real papers):** version-prefixed src (2607.02116 form), bare src (2511.04694 form), `extracted/<n>/images/` src form, table-first `<figure>`, multi-`<img>` subfigure grid (asserted excluded), MathML caption (2607.01600), license anchor text page + table-cell `CC-BY-4.0` decoy (asserted NOT matched), non-CC page, synthetic PNG/JPEG headers for the dimension parser (JPEG has no real fixture in this lane — PNG measured at 78/78 — synthetic bytes acceptable).

**Named tests:** resolver (all 3 forms + foreign-host drop + 404-candidate drop), candidate filter, dimension gate (aspect/width/parse-fail), caption cleaning, license text-parse + decoy, forced-null on zero candidates, writer index out-of-range, figure+license spread onto article (positive assertion), prompt byte-identical when no candidates, kill switch = zero fetches, poster guards each branch, **upload-once/retry** (force tweet-1 first-attempt failure → exactly one upload, media on retry), hook-only attachment (4 fakes updated), writer-picked-but-download-fails → text-only + `attached: false`, mixed-state batch (figure-bearing article + poster flag off → skip logged), dry-run logging, **ledger media persisted + old-entry-without-media no KeyError**, report media section renders.

## 8. Out of scope (YAGNI)

PDF figure extraction / page rendering; SVG conversion; generated title cards; multi-image posts; media on non-hook tweets; S3 image staging; ranged-GET optimization (dropped rev 2); Premium media features; engagement-metric reads (paid) — `media.attached` in the ledger is the correlation hook for later.

## Adjudication notes

- Rejected (design review): "abs pages have no figures — premise fails" (misread; we fetch /html).
- Reversed (spec review): "/html/<id> redirects to versioned URL" — it does not; resolver rebuilt on src-prefix evidence.
- Merged conflicting fixes: license via `a#license-tr` TEXT on the /html page (single fetch preserved) rather than a second /abs GET or export-API call.
- Dimension-gate numbers are explicitly provisional pending the 20-paper calibration task in the plan.
