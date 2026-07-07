# Voice v2 A/B Verdict — 2026-07-06 (stakes/arc/stance/jargon-gloss prompt vs shipped v1)

**SHIP GATE: PASS**

Both sides production-true (Sonnet 4.6 + split/trim repair); OLD = writer
prompt at 629bb767 (frozen verbatim); articles = Mon 2026-07-06 live sidecar
top-8; 0 contract errors both sides. Trigger: owner read the first live
thread and found it dry — stat-dense, mechanism-heavy, no stance, unexplained
jargon (Jaccard, hash-chained versions, set-algebraic selectors).

## Gate results

- Preference (>=7/8 majorities, 'more likely to FOLLOW'): **8/8** -> PASS
- credibility guard: mean NEW 8.12 vs OLD 7.25 (PASS); worst pair regression +0.0 on pair 4 (PASS)
- accessibility guard: mean NEW 8.00 vs OLD 5.50 (PASS); worst pair regression +0.0 on pair 6 (PASS)

Judges: 3 independent blind subagents (Opus), engagement-first rubric
(scroll_stop / read_completion / reply_urge / share_urge / accessibility /
credibility), judging as a jaded practitioner timeline reader.

## Dimension means (per-pair judge medians, averaged)

| Dimension | NEW (v2) | OLD (v1) | Δ |
|---|---|---|---|
| scroll_stop | 8.25 | 6.38 | +1.88 |
| read_completion | 7.75 | 5.88 | +1.88 |
| reply_urge | 6.88 | 4.62 | +2.25 |
| share_urge | 7.00 | 5.75 | +1.25 |
| accessibility | 8.00 | 5.50 | +2.50 |
| credibility | 8.12 | 7.25 | +0.88 |

## Per-pair

| Pair | Title | Votes NEW | Winner |
|---|---|---|---|
| 1 | ContextNest: Verifiable Context Governance for Autonomous AI | 3/3 | NEW |
| 2 | Towards Load-Aware Prefill Deflection for DisaggregatedLLMSe | 3/3 | NEW |
| 3 | Lynx: Progressive Speculative Quantization for accelerating  | 3/3 | NEW |
| 4 | Beyond the Prompt:JailbreakingFunction-Calling LLMs via Simu | 3/3 | NEW |
| 5 | Understanding and Evaluating Claw-like Agent Security Throug | 3/3 | NEW |
| 6 | Adoption and Ecosystem Health: A Longitudinal Analysis of Op | 3/3 | NEW |
| 7 | Securing the AI Agent: A Unified Framework for Multi-Layer A | 3/3 | NEW |
| 8 | HARC: Coupling Harmfulness and Refusal Directions for Robust | 3/3 | NEW |

## Judge rationales

**Pair 1** (NEW):
- J1: V1 opens with a concrete failure story and glosses jargon; V2 leads with a Jaccard metric dump only insiders parse.
- J2: V1's deprecated-doc scenario and inline glosses beat V2's cold Jaccard/hash-chain metric dump.
- J3: V1 opens with a concrete deprecated-doc failure and a real question; V2 leads with a Jaccard metric dump that stops fewer scrolls.

**Pair 2** (NEW):
- J1: V2 explains the whole idea in plain words (idle GPUs, queue wait) before numbers; V1 front-loads P95/TTFT/TBT acronyms.
- J2: V2 translates serving-infra jargon into plain 'steal idle GPU capacity' and earns its numbers; V1 is TTFT/SLO soup.
- J3: V2 translates the whole idea into plain 'idle GPUs, steal the capacity' language; V1 buries it under unglossed TTFT/TBT/SLO/2P2D jargon.

**Pair 3** (NEW):
- J1: V1's 'not a law of physics' hook plus inline glosses reads more human; V2 opens with a bare metric and heavier unexplained terms.
- J2: V1's 'not a law of physics' framing hooks harder and glosses TTFT/MSB better than V2's metric-first open.
- J3: V1's 'not a law of physics, just an assumption' reframe plus inline glosses beats V2's metric-forward open and unglossed MSB/LSB/Anchor/Residual.

**Pair 4** (NEW):
- J1: Both strong and clear; V2's shared-buffer framing of trusted vs untrusted context lands the 'why' slightly more viscerally.
- J2: V2 opens on the reader's exact pain and explains the shared-buffer mechanism more plainly; both solid.
- J3: Both sharp; V2's shared-buffer explanation and plain 'walks right past it' stakes are a touch more accessible and readable.

**Pair 5** (NEW):
- J1: V1 ends on a sharp practitioner question and hedges the Claude claim honestly; V2 dumps benchmark internals that flood context.
- J2: V1's opinionated engineer voice and closing supply-chain question outshine V2's benchmark-spec dump.
- J3: V1's honest hedge ('impressive or a coincidence I wouldn't bet on') and closing question read like a real engineer; V2 is benchmark-spec heavy.

**Pair 6** (NEW):
- J1: Both excellent and readable; V2's 'picking a library by its logo' hook plus an open ecosystem question edges scroll-stop and reply-bait.
- J2: V2's 'picking a library by its logo' jab and debatable closing question invite more reply and shares.
- J3: V2's 'picking a library by its logo' hook and closing debate question are far more shareable than V1's raw-number open.

**Pair 7** (NEW):
- J1: V1 'four ways to get owned' is vivid and names a real gap to argue with; V2 is a truncated tool-spec list with a dry open.
- J2: V1's 'four ways to get owned' stance and question beat V2's abrupt jargon-forward capability dump.
- J3: V1's plain 'four ways to get owned, you test one' stakes and question beat V2's truncated, metric-dense open.

**Pair 8** (NEW):
- J1: V1 opens deep in residual-stream jargon; V2 translates the mechanism ('rephrase and it complies') into a stakes-first hook a generalist gets.
- J2: V2 opens on relatable rephrase-jailbreak pain and explains the two-signal mechanism plainly; V1 buries in residual-stream jargon.
- J3: V2's 'refuses until someone rephrases, more fixable than you think' is a recognizable pain; V1 opens in residual-stream/2D-plane jargon.
