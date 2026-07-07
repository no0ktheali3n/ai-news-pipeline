# A/B Writer Evaluation — 2026-07-06 (voice v2 vs v1)

> 8 of 8 pairs generated.

> **Blind review**: Version 1 and Version 2 labels are randomized per pair.
> The mapping (which version is OLD vs NEW) is recorded only in the companion JSON.

## Pair 1: ContextNest: Verifiable Context Governance for Autonomous AI Agent
**URL**: https://arxiv.org/abs/2607.02116  |  **Composite**: 7.750

### Version 1

> Your agent gave a confident answer from a document that was deprecated three months ago. Retrieval found it. Nothing stopped it.

> The insight: retrieval (finding relevant stuff) and governance (proving what was approved, when, and by whom) are separate problems. Conflating them means your RAG pipeline has no way to answer 'was this doc AI-eligible at query time?' - only whether it scored well.

> The concrete result worth stealing: deterministic rule-based selection (think: 'approved docs matching these criteria') returns the exact same document set every run.

> Dense vector search with HNSW (approximate nearest-neighbor lookup) was non-deterministic on 80% of queries - sometimes returning completely different docs for identical queries. If your evals are flaky, check this first. Also curious: has anyone actually hit the…

> Paper: ContextNest - Verifiable Context Governance for Autonomous AI Agents https://arxiv.org/abs/2607.02116

### Version 2

> Dense vector retrieval is non-deterministic on 80% of repeated identical queries (mean Jaccard 0.611, worst 0.210) - your agent gets different context chunks each run with no audit trail.

> ContextNest sits below your retrieval layer and enforces provenance, version identity, and integrity before any search runs.

> SHA-256 hash-chained histories + deterministic set-algebraic selectors mean you can reconstruct exactly which document versions an agent saw at inference time.

> Governed selection beat BM25 on answer quality (97% vs 90-93%) at one-third the token cost in their stale-version attack experiment.

> ContextNest: Verifiable Context Governance for Autonomous AI Agents https://arxiv.org/abs/2607.02116

---

## Pair 2: Towards Load-Aware Prefill Deflection for DisaggregatedLLMServing
**URL**: https://arxiv.org/abs/2607.02043  |  **Composite**: 7.750

### Version 1

> In disaggregated LLM serving, prefill execution is only 2-23% of P95 TTFT. Queuing and KV-cache transfer eat the rest.

> The fix: when prefill nodes are saturated, deflect requests to decode nodes and run prefill as chunked steps interleaved with active decode batches. No inter-node KV transfer needed since prefill runs in place.

> Scheduler estimates TTFT on each path and deflects only when it helps tail latency, while respecting TBT SLOs on in-flight decodes. Sub-millisecond routing overhead. On a 2P2D A100 cluster with DeepSeek-V2-Lite: P95 TTFT down 81%, SLO attainment up 79% vs.

> state-of-the-art disaggregated schedulers.

> Paper: Towards Load-Aware Prefill Deflection for Disaggregated LLM Serving https://arxiv.org/abs/2607.02043

### Version 2

> Your inference cluster has separate GPU pools for prompt processing and generation, and most of your tail latency is just requests sitting in queue — not actual compute.

> The twist: when your prompt-processing nodes are slammed, your generation nodes are sitting half-idle. Instead of waiting, you can steal that idle capacity — run the prompt there in small chunks, interleaved with ongoing generation.

> No cross-node memory transfer needed, which turns out to be the bigger win since that transfer was eating most of the remaining latency budget.

> Numbers that earned their place: 81% reduction in P95 first-token latency, 79% better SLO attainment, routing decision costs under 1ms. The trick is estimating whether the generation node's chunk schedule keeps per-token gaps within budget before committing. I'd want to know…

> Paper: 'Towards Load-Aware Prefill Deflection for Disaggregated LLM Serving' https://arxiv.org/abs/2607.02043

---

## Pair 3: Lynx: Progressive Speculative Quantization for accelerating KV Transfer in Long-Context Inference
**URL**: https://arxiv.org/abs/2607.01831  |  **Composite**: 7.750

### Version 1

> Waiting for the full KV cache to arrive before decoding starts is not a law of physics - it's just an assumption nobody questioned.

> Lynx splits the KV cache into two streams: high-priority 'coarse' bits that unlock decoding immediately, and low-priority 'refinement' bits that trickle in while you're already generating. Decoding starts speculative, then gets verified against the full-precision result.

> The key insight: most-significant bits alone are enough to get attention roughly right. If you're building on disaggregated inference (prefill and decode on separate machines), this is the bottleneck you're actually fighting.

> The numbers: TTFT (time until first token appears) matches aggressive 4-bit compression, accuracy matches full BF16 - without having to pick one. 1.43x TTFT improvement over standard 8-bit transfer, 5.1% accuracy recovery over current best quantization schemes. The…

> Paper: 'Lynx: Progressive Speculative Quantization for accelerating KV Transfer in Long-Context Inference' https://arxiv.org/abs/2607.01831

### Version 2

> Lynx cuts TTFT by 1.43x over 8-bit KV quantization while matching BF16 accuracy - by treating the KV cache as a stream, not a blob.

> The key insight: MSBs of the KV cache capture coarse attention structure, LSBs refine precision. Lynx splits transfer into an Anchor stream (MSBs) and a Residual stream (LSBs). Decoding starts on Anchor arrival, runs speculatively, then verifies against the full precision result.

> For builders running disaggregated prefill/decode: this directly attacks the prefill-to-decode handoff bottleneck in long-context RAG and agentic workloads. You get 4-bit latency with BF16-equivalent accuracy.

> The speculative verification step is what makes the accuracy claim hold.

> Paper: Lynx: Progressive Speculative Quantization for accelerating KV Transfer in Long-Context Inference https://arxiv.org/abs/2607.01831

---

## Pair 4: Beyond the Prompt:JailbreakingFunction-Calling LLMs via Simulated Moderation Traces
**URL**: https://arxiv.org/abs/2607.00481  |  **Composite**: 7.750

### Version 1

> Prompt-level safety filters are blind to multi-turn function-calling attacks - and this paper shows exactly how to exploit that gap.

> The attack (SMT) works by constructing a fake moderation-auditing workflow across multiple turns. It plants adversarial intent across tool schemas, structured arguments, and tool outputs - not in a single prompt.

> Safety refusals get reframed as execution failures, and the model iteratively relaxes its own constraints. Black-box, minimal queries, beats all baselines on HarmScore across 5 commercial LLM providers.

> If you're building agents: sanitizing the user message is not enough. You need context-aware validation across the full state - schemas, tool arguments, tool outputs, and conversation history. The shared context window is the attack surface.

> Paper: Beyond the Prompt - Jailbreaking Function-Calling LLMs via Simulated Moderation Traces https://arxiv.org/abs/2607.00481

### Version 2

> Sanitizing your system prompt is not enough if you're running tool-calling agents. A new attack walks right past it.

> The twist: when LLMs run tools, the conversation context mixes your trusted instructions with untrusted tool outputs in one shared buffer.

> Attackers don't need to touch your prompt - they can smuggle intent across multiple tool-call turns, distributed so no single message looks harmful.

> The attack (SMT) pretends to be a legitimate moderation-audit workflow. It frames harmful requests as 'red-team testing', then treats the model's safety refusals as test failures that need fixing - iteratively eroding guardrails over several turns. High success rate, low…

> Paper: 'Jailbreaking Function-Calling LLMs via Simulated Moderation Traces' https://arxiv.org/abs/2607.00481

---

## Pair 5: Understanding and Evaluating Claw-like Agent Security Through a Computer-Systems Lens
**URL**: https://arxiv.org/abs/2606.30755  |  **Composite**: 7.750

### Version 1

> Malicious plugins (think: third-party add-ons) attacking always-on AI agents succeed 100% of the time regardless of which model you use.

> The actual insight: the model isn't the security boundary. These agents have OS-level access - credentials, files, scheduled tasks - and nobody has built the equivalent of an OS's permission model. Swapping GPT for Claude doesn't save you. The runtime does.

> Concrete numbers worth stealing: best-case attack success rate across tested platforms was 70%. The most 'secure' platform cut that to 22% - but partly by just breaking features, not through real defenses.

> Claude Opus was already near that 22% floor on its own, which is either impressive or a coincidence I wouldn't bet production systems on. Real question: if your agent installs Skills/Plugins from any external source, what's your supply-chain integrity check right now?

> Paper: 'Understanding and Evaluating Claw-like Agent Security Through a Computer-Systems Lens' https://arxiv.org/abs/2606.30755

### Version 2

> Malicious plugins in always-on AI agents succeed 100% of the time regardless of which LLM you use underneath.

> SafeClawArena benchmarks 406 adversarial tasks across 4 attack surfaces: skill supply-chain integrity, persistent state exploitation, cross-boundary data flow, and indirect prompt injection. They use canary-marked credentials + automated taint tracking across 9 output channels.

> The threat model maps agent components to OS analogues - plugins are loadable kernel extensions, skills are user apps. That framing makes the severity obvious: these aren't chatbot jailbreaks, they're privilege escalation.

> Numbers worth internalizing: best-case attack success rate is 22% (Claude-Opus-4.6 or SeClaw's restricted config). Worst case is 70%. The 'secure' platform SeClaw gets there partly by crippling utility, not through active defenses. If you're shipping an always-on agent with…

> Paper: Understanding and Evaluating Claw-like Agent Security Through a Computer-Systems Lens https://arxiv.org/abs/2606.30755

---

## Pair 6: Adoption and Ecosystem Health: A Longitudinal Analysis of Open-SourceMulti-AgentFrameworks
**URL**: https://arxiv.org/abs/2607.02453  |  **Composite**: 7.500

### Version 1

> AutoGPT hit 111,967 stars in a single month but converted fewer than 9 contributors per 1,000 stars. LangChain converted 41. Stars are a hype metric, not an adoption metric.

> The paper tracks 15 agentic frameworks from late 2022 to early 2026 across 808K stars, 74K PRs, 86K commits, and 987K user profiles. Key signal: contributor density (contributors per 1K stars) separates real adoption from viral noise.

> Pydantic-AI outperforms MetaGPT and LangFlow on this despite lower visibility. LangChain pulls 82.5% of cross-ecosystem contributors, meaning it functions as shared infra regardless of what framework you ship on top.

> Practical implication: if you're evaluating frameworks for a long-running project, check 90-day contributor retention and cross-ecosystem overlap, not star trajectory. Retention stabilizes around day 90 - projects that can't hold contributors past 30 days are fragile bets.

> Paper: Adoption and Ecosystem Health: A Longitudinal Analysis of Open-Source Multi-Agent Frameworks https://arxiv.org/abs/2607.02453

### Version 2

> You picked your agent framework based on GitHub stars. This paper suggests that's roughly as useful as picking a library by its logo.

> The twist: star counts are a lagging hype metric, not a health signal. AutoGPT hit 112k stars in a month but converted fewer than 9 contributors per 1,000 stars. LangChain converted 41. Stars measure virality. Contributor density measures whether people actually stayed to build.

> Practical steal: before committing to a framework, check (1) contributor density - contributors per 1k stars, (2) 90-day retention (half of new contributors ghost within 30 days), and (3) cross-ecosystem overlap.

> LangChain pulls 82.5% of contributors who also work in other frameworks - that's a sign of shared infrastructure, not just popularity. Worth asking: does institutional backing (like openai-agents-python) ever substitute for community depth, or does it always hollow it out?

> Paper: 'Adoption and Ecosystem Health: A Longitudinal Analysis of Open-Source Multi-Agent Frameworks' https://arxiv.org/abs/2607.02453

---

## Pair 7: Securing the AI Agent: A Unified Framework for Multi-Layer Agent Red Teaming
**URL**: https://arxiv.org/abs/2606.31227  |  **Composite**: 7.310

### Version 1

> Your agent stack has at least four distinct ways to get owned, and you're probably only testing one of them.

> The insight: infrastructure, protocol, behavior, and model aren't just different attack surfaces - they need different detection methods.

> Treating them the same is why your red team finds prompt injections but misses vulnerable MCP servers or supply-chain issues in agent skill packages.

> Concrete numbers: 75+ AI components covered, 1,400+ vulnerability rules, 26+ jailbreak attack operators across 16 datasets. What I'd steal immediately is the supply-chain auditing for agent skills - that's the layer almost nobody is checking right now. What's your current…

> Securing the AI Agent: A Unified Framework for Multi-Layer Agent Red Teaming https://arxiv.org/abs/2606.31227

### Version 2

> AI agent attack surfaces have 4 distinct layers and no single detection method covers all of them - this paper maps exactly what breaks at each layer.

> AI-Infra-Guard structures red teaming around layer-paradigm matching: deterministic rules for 75+ infra components (1,400+ vuln rules), LLM-driven audits for MCP servers and agent-skill supply chains, multi-turn black-box agent probing, and a jailbreak harness with 26+ attack…

> Paper: 'Securing the AI Agent: A Unified Framework for Multi-Layer Agent Red Teaming' - https://arxiv.org/abs/2606.31227

---

## Pair 8: HARC: Coupling Harmfulness and Refusal Directions for Robust Safety Alignment
**URL**: https://arxiv.org/abs/2607.00572  |  **Composite**: 7.250

### Version 1

> Jailbreaks work by suppressing either the harmfulness or refusal direction in the residual stream before a single token is generated - and these attack classes cluster into separable regions of that 2D plane.

> HARC fine-tunes by coupling the harmfulness and refusal directions across both prompt and response token positions. The intervention stays inside that subspace, so general capability and over-refusal rates don't move.

> Beats 6 baselines on the robustness-capability-usability tradeoff, and the directions transfer across 5 model families without architecture-specific tuning.

> One practical implication: the model can detect it's generating harmful content mid-response even when it missed the harmful intent at the prompt - that's a hook for inference-time interventions too.

> HARC: Coupling Harmfulness and Refusal Directions for Robust Safety Alignment https://arxiv.org/abs/2607.00572

### Version 2

> Your safety-tuned model refuses harmful prompts until someone slightly rephrases them - this paper explains the exact internal mechanism why, and it's more fixable than you think.

> The twist: jailbreaks don't 'confuse' the model - they surgically suppress one of two internal signals (harm recognition OR refusal intent) before the first token is generated. Worse, the model often *detects* harm mid-generation but already committed to the response.

> Two separate failure modes, not one.

> The fix (HARC) couples those two signals together during fine-tuning so suppressing one drags the other. Result: stronger jailbreak resistance without the usual tax of refusing everything borderline or losing capability on normal tasks. Held up across 5 model families without…

> Paper: 'HARC: Coupling Harmfulness and Refusal Directions for Robust Safety Alignment' https://arxiv.org/abs/2607.00572

---
