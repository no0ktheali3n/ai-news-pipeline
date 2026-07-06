# Phase 3 evening-slot min_score calibration — 2026-07-05

**Recommendation: `min_score = 8.25`** — by the rank-2 distribution the evening slot would post on ~54% of days and stay silent otherwise. Spec requirement (>=10 scored runs, no assumed 7.5) satisfied: 13 backfilled windows + 3 live scored runs already in S3.

## Method

- 13 historical 3-day windows (2026-04-21 .. 2026-07-02, 6-day step), production lane queries + parser via arXiv advanced search (date-filtered, every candidate's submitted date hard-validated in-window).
- Scoring: production `score_candidates` (Haiku, temp 0.2) via OpenRouter; buzz OFF (historical buzz is stale by construction).
- The evening slot sees the best ledger-UNPOSTED article. Noon consumes rank-1, so rank-2 is the calibration target; rank-1 shown for context.

## Distributions (composite, 10-point scale)

| series | n | min | p25 | median | p75 | max |
|---|---|---|---|---|---|---|
| per-window rank-1 | 13 | 7.75 | 8.00 | 8.75 | 8.75 | 8.75 |
| per-window rank-2 | 13 | 7.75 | 7.75 | 8.25 | 8.25 | 8.75 |
| all candidates | 370 | 1.50 | 5.50 | 6.75 | 7.75 | 8.75 |

## Evening post rate by threshold

| min_score | rank-2 days posting | rank-1 days posting |
|---|---|---|
| 7.00 | 13/13 (100%) | 13/13 (100%) |
| 7.25 | 13/13 (100%) | 13/13 (100%) |
| 7.50 | 13/13 (100%) | 13/13 (100%) |
| 7.75 | 13/13 (100%) | 13/13 (100%) |
| 8.00 | 8/13 (62%) | 12/13 (92%) |
| 8.25 | 7/13 (54%) | 9/13 (69%) |

## Per-window detail

| window end | n | rank-1 | rank-2 | rank-3 | median |
|---|---|---|---|---|---|
| 2026-04-21 | 29 | 8.00 | 7.75 | 7.75 | 6.25 |
| 2026-04-27 | 27 | 8.75 | 7.75 | 7.75 | 6.75 |
| 2026-05-03 | 30 | 7.75 | 7.75 | 7.75 | 6.25 |
| 2026-05-09 | 29 | 8.75 | 7.75 | 7.75 | 6.75 |
| 2026-05-15 | 28 | 8.25 | 8.25 | 8.25 | 6.75 |
| 2026-05-21 | 30 | 8.00 | 7.75 | 7.75 | 6.25 |
| 2026-05-27 | 30 | 8.75 | 8.25 | 8.00 | 6.50 |
| 2026-06-02 | 28 | 8.00 | 8.00 | 7.75 | 6.75 |
| 2026-06-08 | 27 | 8.75 | 8.25 | 8.25 | 6.50 |
| 2026-06-14 | 29 | 8.75 | 8.75 | 8.75 | 7.50 |
| 2026-06-20 | 29 | 8.75 | 8.75 | 8.75 | 7.25 |
| 2026-06-26 | 27 | 8.25 | 8.25 | 8.00 | 6.25 |
| 2026-07-02 | 27 | 8.75 | 8.25 | 7.75 | 6.75 |

## Caveats

- 3-day windows pool more candidates than a single daily run, biasing top ranks slightly HIGH — the derived threshold is therefore conservative (evening posts a bit less often live than backfill suggests). Safe direction for a quality gate.
- Buzz OFF here; live evening runs may blend sparse buzz, nudging composites up for trending papers. Revisit after 2-3 weeks of live scored runs.
- Scores from Haiku via OpenRouter; live noon runs use the same scorer model on Bedrock — provider should not change scores materially (same model, temp 0.2), but the first live weeks will confirm.
