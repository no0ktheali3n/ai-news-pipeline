# A/B Writer Verdict — 2026-07-05 (thread contract vs frozen v0.9 legacy)

**SHIP GATE (round 3, final): PASS**

Ship config gated here: writer = Sonnet 4.6 (`us.anthropic.claude-sonnet-4-6-20260101-v1:0`), 180-char hook prompt target, split/trim repair in `validate_and_repair`. OLD side = frozen v0.9 legacy formatter on Haiku 4.5 (prod parity). All generation via OpenRouter (`--provider openrouter`) during the AWS Bedrock quota outage.

## How we got here (3 rounds, 1 diagnostic)

- **Round 1** (Haiku both sides — format isolated): all 3 blind judges preferred NEW in **8/8** pairs (clarity medians 8.75 vs 6.50) — the format wins decisively. BUT the writer overshot the 240-char hook cap on all 8 pairs (260-287); in production that raises ContractError -> demotion to the losing legacy format. Gate voided: the experiment must test what ships.
- **Round 2** (prompt hook target 240->180, NEW regenerated): Haiku still blew the cap on 6/8 (237-282). Conclusion: Haiku ignores character budgets regardless of the stated number — not a prompt problem.
- **Sonnet 4.6 diagnostic** (same articles/prompt): hooks perfect (113-195) but one substance tweet ballooned to 284-486 on every pair. No model reliably fits char budgets by prompt alone.
- **Owner decision (Option A)**: add mechanical repair — over-280 non-hook tweets sentence-split when the thread has room, word-trim otherwise; final tweet trims around the preserved arXiv link; hook stays hard-fail (a truncated hook defeats its purpose). Writer pinned to Sonnet 4.6 (template default; the Haiku pin was a quota workaround). 3 new contract tests.
- **Round 3** (this gate): Sonnet 4.6 + repair = production-true output, fresh 3-judge panel.

## Round 3 — gate results

- Preference gate (>=7/8 per-pair judge majorities for NEW): **8/8** -> PASS
- Clarity mean guard (mean median clarity NEW 8.00 >= OLD 6.00 - 0.5): PASS
- Clarity per-pair guard (worst regression +0.0 on pair 7, limit 1.5): PASS
- Contract compliance (NEW side, production-postable): 8/8 clean -> PASS
- Generation failures: 0

Judges: 3 independent blind subagents (Opus) per judged round — round-3 judges fresh, never saw earlier rounds; identical rubric, no cross-talk; blinding = randomized Version 1/2 per pair (`new_first`), mapping never shown to judges.

## Per-pair table (round 3)

| Pair | Title | NEW was | Votes for NEW | Winner | NEW tweets | Clarity NEW (med) | Clarity OLD (med) |
|---|---|---|---|---|---|---|---|
| 1 | Steerability via constraints: a substrate for scalable oversight of co | V1 | 3/3 | NEW | 5 | 8.0 | 6.0 |
| 2 | Distributed Attacks in Persistent-StateAIControl | V2 | 3/3 | NEW | 5 | 8.0 | 6.0 |
| 3 | Beyond the Prompt:JailbreakingFunction-Calling LLMs via Simulated Mode | V1 | 3/3 | NEW | 4 | 8.0 | 6.0 |
| 4 | Security--Fidelity Tradeoffs: The Hidden Cost ofPromptInjectionDefense | V2 | 3/3 | NEW | 5 | 8.0 | 5.0 |
| 5 | Understanding and Evaluating Claw-like Agent Security Through a Comput | V1 | 3/3 | NEW | 5 | 8.0 | 6.0 |
| 6 | Reasoning effort, not tool access, buys first-try reliability inagenti | V2 | 3/3 | NEW | 4 | 9.0 | 6.0 |
| 7 | HARC: Coupling Harmfulness and Refusal Directions for Robust Safety Al | V1 | 3/3 | NEW | 5 | 7.0 | 7.0 |
| 8 | Forensic Trajectory Signatures for Agent Memory Poisoning Detection | V2 | 3/3 | NEW | 5 | 8.0 | 6.0 |

## Dimension means (round 3; mean over pairs of per-pair judge medians)

| Dimension | NEW | OLD | Δ |
|---|---|---|---|
| hook_strength | 8.38 | 5.62 | +2.75 |
| practitioner_value | 9.00 | 5.62 | +3.38 |
| clarity | 8.00 | 6.00 | +2.00 |
| coherence | 8.50 | 6.00 | +2.50 |
| follow_likelihood | 8.00 | 4.62 | +3.38 |
| share_likelihood | 7.12 | 4.62 | +2.50 |

## Judge rationales (round 3, per pair, judges 1-3)

**Pair 1** (NEW):
- J1: V1 leads with the concrete recall lift and gives a tight, actionable read; V2 buries the numbers in hype and generic advice.
- J2: V1 opens with a concrete result (54.5%->90.9%) and delivers an actionable 'lock down access, give reviewer context' takeaway; V2 buries the number in generic hype and emoji.
- J3: V1 opens with a concrete recall gain and cheap-setup detail; V2 buries the numbers under generic hype and a robot emoji.

**Pair 2** (NEW):
- J1: V2 opens with a sharp attack mechanic, names the models, and gives precise evasion deltas; V1 is emoji hype that dilutes the same facts.
- J2: V2 names the mechanism (split payload across PRs), the specific defense (stateful link-tracker, 93%->47%), and the models it holds across; V1 is emoji-driven and vaguer.
- J3: V2 names the attack construct, cites cross-model evasion numbers and the mitigation delta cleanly; V1 drowns the same facts in emoji and cliches.

**Pair 3** (NEW):
- J1: V1's thesis-first hook and concrete multi-layer defense guidance beat V2's analogy-heavy, low-density hype.
- J2: V1 states the threat model crisply and ends with a concrete checklist (validate at schema/tool-output/conversation-state level); V2 restates the same ideas with more words and less precision.
- J3: V1 states the threat model precisely and gives concrete schema/output/state validation guidance; V2 substitutes analogies and hype for specifics.

**Pair 4** (NEW):
- J1: V2 leads with the exact security/fidelity numbers and crisply explains the metric flaw; V1 is a long emoji ramble that reads slower.
- J2: V2 leads with the sharp tradeoff numbers (99.3% security / 71% fidelity) and a deployment-specific decision rule; V1 is long, emoji-heavy, and slower to reach the point.
- J3: V2 leads with the sharp security/fidelity numbers, nails the metric-conflation insight, and gives deployment-specific guidance; V1 is long, padded, and emoji-heavy.

**Pair 5** (NEW):
- J1: V1's striking 100%-plugin-attack hook, dense real numbers, and 'LLM is not your security boundary' land far harder than V2's analogy hype.
- J2: V1's '100% regardless of model' hook plus hard numbers and 'the LLM is not your security boundary' is quotable and dense; V2 restates it as an analogy-laden wake-up call.
- J3: V1 hooks with the 100% plugin-attack stat, packs concrete benchmark numbers, and lands 'the LLM is not your security boundary'; V2 trades numbers for hype.

**Pair 6** (NEW):
- J1: V2 is dense and precise (28->89%, cost delta, hidden container-deploy defect) with a clean takeaway; V1 wraps the same finding in emoji hype.
- J2: V2 front-loads the punchline (28%->89%, cost +42-68% for nothing, container-deploy defect) and ends 'spend on reasoning, not tooling'; V1 pads it with emoji and a student-calculator analogy.
- J3: V2 leads with the 28-to-89% reasoning-effort result plus the container-deploy defect and paraphrase-reproduction detail; V1 wraps the same in emoji and student-calculator analogies.

**Pair 7** (NEW):
- J1: V1's mechanistic hook and the 'recoverable failure mode most safety work ignores' insight give real depth; V2 softens it into accessible hype.
- J2: V1 is mechanistically precise (residual-stream directions, subspace-confined intervention, transfer across 5 families) and surfaces the recoverable-failure-mode insight; V2 softens it into general-audience prose.
- J3: V1 is mechanistically precise (residual stream, 2D separability, confined subspace) and surfaces the recoverable-failure insight; V2 dilutes it with hype and a guard analogy.

**Pair 8** (NEW):
- J1: V2 packs the invariant rule, precise AUCs, and the triage-by-channel insight into a scannable post; V1 carries the numbers but drowns them in emoji.
- J2: V2 gives the operational invariant (recall-before-send), ablation robustness (AUC 0.990 with recall features stripped), and triage-by-channel value; V1 covers the same facts but with emoji framing and less rigor.
- J3: V2 leads with the AUC, names the core invariant, shows the ablation robustness, and gives triage utility; V1 has the numbers but smothers them in emoji hype.

## Rate-limit re-verification (pre-judgment, per Task 7)

Verified 2026-07-05 at docs.x.com: X API v2 is pay-per-usage; the 2M/month cap
applies to Post READS only. Writes (`POST /2/tweets`) are rate-limited at
100/15min per user (10,000/24h per app) with no monthly write cap — worst case
~132 writes/month is unconstrained. `THREAD_MAX_TWEETS=5` stands.

## Artifacts

- Round 1: `2026-07-05-writer-pairs.json`, `2026-07-05-writer-report.md`, `2026-07-05-judge-{1,2,3}.json`
- Round 2: `2026-07-05-writer-pairs-r2.json`, `2026-07-05-writer-report-r2.md` (compliance-failed pre-judging; never judged)
- Sonnet diagnostic: `2026-07-05-sonnet46-diagnostic.json`
- Round 3: `2026-07-05-writer-pairs-r3.json`, `2026-07-05-writer-report-r3.md`, `2026-07-05-judge-r3-{1,2,3}.json`
