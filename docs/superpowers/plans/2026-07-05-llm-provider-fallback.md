# LLM Provider Abstraction + OpenRouter Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** All model calls route through one thin provider layer — Bedrock primary (the project's AWS story), OpenRouter automatic fallback on primary failure — so the pipeline runs even while AWS quotas are dead, and future providers are a ~30-line adapter, not a refactor.

**Architecture:** New `utils/llm.py` exposes `complete(prompt, *, model, max_tokens, temperature) -> str` and hides providers behind it. `scoring.py` and `summarizer.py` (both call sites) swap their inline `invoke_model` blocks for `llm.complete(...)`, keeping ALL their existing validation/retry/sentinel semantics. The A/B harness gains `--provider`. Config is env/param-driven; secrets follow the MakeWebhookUrl NoEcho pattern.

**Verified facts (2026-07-05):** OpenRouter slugs exist for the exact models: `anthropic/claude-haiku-4.5` (ctx 200k), `anthropic/claude-sonnet-4.6` (1M), `anthropic/claude-sonnet-4.5` (1M). OpenRouter speaks OpenAI chat-completions (`POST https://openrouter.ai/api/v1/chat/completions`, Bearer key, `choices[0].message.content`).

## Global Constraints

- **Bedrock stays primary by default.** `LLM_PROVIDER` env (default `"bedrock"`); `LLM_FALLBACK_PROVIDER` env (default `""` in code; deploy config sets `"openrouter"`). Fallback triggers on ANY primary-provider exception (quota/access/transport) — the goal is "the run happens"; a request that fails identically on both just fails twice with both errors logged.
- **Missing key degrades, never crashes:** if a fallback/provider needs `OPENROUTER_API_KEY` and it's empty, log ONE warning and behave as if no fallback is configured. `llm.py` import must never raise (Lambda-safe, mirroring buzz.py's `_env_float` philosophy).
- **Caller semantics are untouched:** `score_candidates` still raises `ScoringError` on validation/transport failure (with the same messages the tests assert); `summarize_with_claude`/`write_thread_with_claude` still raise into `retry_until_timeout`'s sentinel machinery. `llm.complete` returns the assembled TEXT (providers' content joined) and raises `LLMError(provider, cause)` — callers wrap as they already do.
- **Model ids stay Bedrock-flavored everywhere** (envs, template, ledger provenance). Translation to OpenRouter slugs happens inside llm.py: explicit table for the known family (haiku-4-5, sonnet-4-6, sonnet-4-5, opus variants) + regex derivation fallback (`(?:us|global)\.anthropic\.claude-(\w+)-(\d)-(\d)` → `anthropic/claude-{name}-{maj}.{min}`) + optional `LLM_MODEL_MAP` env (JSON) override; ids already containing `/` pass through untouched.
- **No new dependencies:** OpenRouter via `requests` (already shipped in scraper + check summarizer function requirements — add `requests` there if absent). `timeout=120` on generation calls.
- Tests: dependency-free scripts (`uv run python tests/<file>.py`); all 6 existing suites stay green; fake `requests` router (FAKE_HTTP) gains the openrouter route; FakeBedrock `mode="denied"` is the primary-failure lever for fallback tests.
- Branch `feat/llm-provider-fallback` off `feat/content-engine-phase4` tip. NO deploys inside the tasks (Task 4 is controller-run).
- Secrets: `OPENROUTER_API_KEY` never in tracked files; local runs read `~/projects/00-cr/openrouter-key.txt` inline; deploys pass the NoEcho param.

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `lambda/layers/common/python/utils/llm.py` | Create | Provider registry, complete(), fallback, model mapping, LLMError |
| `lambda/layers/common/python/utils/scoring.py` | Modify | invoke_model block → llm.complete |
| `lambda/layers/common/python/utils/summarizer.py` | Modify | both call sites → llm.complete |
| `lambda/summarizer/requirements.txt` | Verify/Modify | ensure `requests` present |
| `tests/stubs.py` | Modify | FAKE_HTTP openrouter route (configurable reply/error) |
| `tests/test_llm.py` | Create | provider select, fallback, mapping, key-degrade |
| `tests/test_content_engine.py` | Modify | one integration test: scoring via fallback when bedrock denied |
| `scripts/ab_writer_eval.py` | Modify | `--provider` flag; calls route through utils.llm |
| `template.yaml` | Modify | `LlmFallbackProvider` + `OpenRouterApiKey` (NoEcho) params → envs on Scraper + Summarizer worker |
| `samconfig.toml` | Modify | `LlmFallbackProvider="openrouter"` in parameter_overrides |

### Task 1: `utils/llm.py` + unit tests
Interfaces produced (verbatim for later tasks): `complete(prompt: str, *, model: str, max_tokens: int, temperature: float = 0.2) -> str`; `class LLMError(Exception)` with `.provider` attr; `to_openrouter_model(model_id: str) -> str`; module envs `LLM_PROVIDER`, `LLM_FALLBACK_PROVIDER`, `OPENROUTER_API_KEY`, optional `LLM_MODEL_MAP`. Bedrock path reuses the existing anthropic-payload shape (copy from scoring.py: anthropic_version, max_tokens, temperature, messages; text = join of content blocks with type text). OpenRouter path: requests.post, Bearer auth, 120s timeout, raise LLMError on status != 200 / missing choices; return `choices[0].message.content`. Fallback wrapper: try primary → except Exception as e → if fallback configured+usable, log warning with BOTH provider names, try fallback → its failure raises LLMError chaining both. TDD in new tests/test_llm.py (header pattern = test_buzz.py): bedrock-ok path (FAKE_BEDROCK); openrouter-ok path (route `openrouter.ai` in FAKE_HTTP returning a chat-completions body); fallback engages on mode="denied"; no-key degrade (fallback configured, key empty → primary error propagates as LLMError, ONE warning); mapping table+derivation+passthrough+`LLM_MODEL_MAP` override. Commit: `feat: provider-agnostic llm.complete with openrouter fallback`.

### Task 2: rewire scoring + summarizer
Replace the `invoke_model` blocks in `scoring.score_candidates`, `summarizer.summarize_with_claude`, `summarizer.write_thread_with_claude` with `llm.complete(...)` (same max_tokens/temperature values they use today). Their except-paths keep raising ScoringError/propagating exactly as now — read each function's current error handling FIRST and preserve messages the suites assert. Delete the now-unused module-level bedrock clients ONLY if nothing else in the module uses them (scoring's `_bedrock` — check; summarizer's `bedrock` — check summarize_articles/others). Add ONE integration test to test_content_engine.py: with FAKE_BEDROCK.mode="denied" AND fallback envs set AND FAKE_HTTP openrouter route returning a valid scoring reply → `score_candidates` succeeds (proves the whole chain). Ensure `lambda/summarizer/requirements.txt` includes `requests`. All suites green. Commit: `feat: scoring + writer route through llm.complete (bedrock primary, openrouter fallback)`.

### Task 3: harness flag + template
Harness: add `--provider {bedrock,openrouter}` (default bedrock) — sets `os.environ["LLM_PROVIDER"]` BEFORE importing utils.llm; replace `call_bedrock` internals with `utils.llm.complete` + keep `_parse_model_json` local (harness stays standalone-ish; utils import is already established for thread_contract). Read `OPENROUTER_API_KEY` from env, else from `~/projects/00-cr/openrouter-key.txt` if present (local convenience; never print it). Template: `LlmFallbackProvider` (String, default "", AllowedValues ["", "openrouter"]) and `OpenRouterApiKey` (String, default "", NoEcho) → envs `LLM_FALLBACK_PROVIDER` + `OPENROUTER_API_KEY` on ScraperFunction AND SummarizerFunction (worker). samconfig parameter_overrides gains `LlmFallbackProvider="openrouter"` (key is passed at deploy time, NOT samconfig — via `scripts/deploy-full-stack.sh`, which passes the FULL override set: `--parameter-overrides` REPLACES the samconfig list wholesale, it does not append). `sam validate --lint`; suites green. Commit: `feat: harness provider flag; template fallback params (key NoEcho, never persisted)`.

### Task 4 (CONTROLLER): A/B via OpenRouter + final review + deploy decision
Requires the owner's OpenRouter key at `~/projects/00-cr/openrouter-key.txt`. Sanity probe (1 tiny completion) → run harness `--provider openrouter --n 8` → judge panel → 7/8 gate verdict. Final whole-branch review of this branch. Deploy decision with owner: if gate passes, deploy the full stack (1.5+P2+P4+fallback) before Mon 16:00 UTC with Bedrock primary + fallback on — Monday runs regardless of AWS. Post-Monday: normal merge train.

## Self-Review
- Coverage: primary/fallback/swap-forever (env-driven provider = future adapters register in one module) ✓; Monday insurance ✓; A/B unblocked via provider flag ✓; AWS-primary story preserved ✓.
- Placeholders: none — interfaces exact; implementers read current call sites before rewiring (flagged).
- Consistency: `LLMError` name in T1/T2; env names identical in T1 code and T3 template; harness flag reuses T1's module.
