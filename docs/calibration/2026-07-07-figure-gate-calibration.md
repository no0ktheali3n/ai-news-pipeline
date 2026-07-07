# Figure dimension-gate calibration — 2026-07-07 (Task 6)

Live measurement, 20 recent lane papers (urls from the two newest calibration sidecars). Each run through the REAL `figures.fetch_figures` plus an instrumented first-candidate pass recording the drop rule.

**Gate constants tested:** AR 1.0-3.0, width >= 600. **DECISION: keep as-is — no change.**

**The operationally meaningful rate is in-band.** A daily post draws ONE paper from
the full scored pool (CC or not, HTML or not), so the number that predicts "how often
does a post carry a figure" is attach-over-ALL-papers = **9/20 = 45%** — squarely in the
40-70% target band.

The plan's literal metric, attach-over-CC-papers-with-candidates, is 9/10 = **90%**. That
is above the nominal 70% ceiling, and that is fine:
- The dimension gate is a **legibility floor, not a quality filter.** Quality selection is
  downstream — the writer sees only gate-passing figures and may still return `null`. A high
  dimension-level pass rate just means "most CC papers have at least one legible figure,"
  which is true of arXiv.
- The gate demonstrably **rejects genuinely bad figures**: 2 ultra-wide first-candidates
  (ar 3.69, 3.59) and 1 sliver (571x159) were dropped. In paper 2607.01153 the first
  candidate (ar 3.69) was rejected while 3 legible siblings passed — the gate filters
  *within* a paper without killing the paper's chance.
- The only widen-trigger in the plan was "if BELOW target, widen." We are not below.

**Breakdown:** 20 papers; CC-licensed 11 (55%); non-CC "arXiv perpetual" 7 (gated out by
license, correct); no-HTML 2 (11%, normal). Of 11 CC papers, 10 have >=1 single-img Figure
candidate, 9 ship >=1 gate-passing figure (the 1 miss: 2511.04694, all candidates <600px wide).

Gate outcomes (first candidate): {'PASS': 14, no_html: 2, 'no_candidates': 1, 'ar>3.0': 2, 'width<600': 1}

| # | paper | license | CC | cands | dims | ar | gate | shipped |
|---|---|---|---|---|---|---|---|---|
| 1 | 2607.01641 | arXiv.org perpetua | False | 4 | 996x673 | 1.48 | PASS | 0 |
| 2 | 2607.00481 | arXiv.org perpetua | False | 4 | 777x361 | 2.15 | PASS | 0 |
| 3 | 2607.01661 | CC BY 4.0 | True | 4 | 3426x1949 | 1.76 | PASS | 4 |
| 4 | 2607.01597 | None | None | None | NonexNone | None | None | 0 |
| 5 | 2607.01277 | CC BY 4.0 | True | 1 | 1912x694 | 2.76 | PASS | 1 |
| 6 | 2607.00895 | CC BY 4.0 | True | 0 | NonexNone | None | no_candidates | 0 |
| 7 | 2606.31227 | CC BY 4.0 | True | 4 | 2470x1298 | 1.9 | PASS | 4 |
| 8 | 2607.01299 | arXiv.org perpetua | False | 4 | 996x598 | 1.67 | PASS | 0 |
| 9 | 2606.22686 | CC BY 4.0 | True | 4 | 997x918 | 1.09 | PASS | 4 |
| 10 | 2607.01600 | CC BY 4.0 | True | 1 | 917x386 | 2.38 | PASS | 1 |
| 11 | 2607.00572 | CC BY 4.0 | True | 4 | 996x674 | 1.48 | PASS | 2 |
| 12 | 2607.01640 | arXiv.org perpetua | False | 3 | 976x665 | 1.47 | PASS | 0 |
| 13 | 2607.01647 | None | None | None | NonexNone | None | None | 0 |
| 14 | 2607.01153 | CC BY 4.0 | True | 4 | 996x270 | 3.69 | ar>3.0 | 3 |
| 15 | 2607.00972 | CC BY 4.0 | True | 1 | 3607x1529 | 2.36 | PASS | 1 |
| 16 | 2511.04694 | CC BY 4.0 | True | 3 | 571x159 | 3.59 | width<600 | 0 |
| 17 | 2607.01276 | arXiv.org perpetua | False | 1 | 1470x1020 | 1.44 | PASS | 0 |
| 18 | 2607.01103 | arXiv.org perpetua | False | 4 | 1619x972 | 1.67 | PASS | 0 |
| 19 | 2606.31876 | arXiv.org perpetua | False | 4 | 2972x620 | 4.79 | ar>3.0 | 0 |
| 20 | 2603.19127 | CC BY 4.0 | True | 1 | 996x398 | 2.5 | PASS | 1 |