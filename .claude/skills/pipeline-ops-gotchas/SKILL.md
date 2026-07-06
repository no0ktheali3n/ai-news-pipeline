---
name: pipeline-ops-gotchas
description: Use when working on ai-news-pipeline operations — deploying (SAM/CloudFormation), invoking Bedrock, pushing to GitHub, running tests, or diagnosing AWS failures in this repo. Hard-won account- and repo-specific facts that prevent repeating past incidents.
---

# ai-news-pipeline Ops Gotchas

Facts learned the expensive way in this repo/account (894495940143, us-east-1). Verify against reality if months have passed — cloud regimes change (that's how half of these were learned).

## Bedrock (models, entitlements, quotas)

- **Model access is now AWS-Marketplace-subscription based** (the old console "Model access" page is retired). A model can appear in `list-inference-profiles` yet be uninvokable. First invoke may *succeed once* (optimistic provisioning) then fail forever — never trust n=1.
- **Error decoder:** `AccessDenied ... aws-marketplace:Subscribe/ViewSubscriptions` = subscription can't complete → the calling principal needs those IAM actions once, or an admin completes it. `ThrottlingException: Too many tokens per day` = subscription fine, **quota** layer. `ResourceNotFound ... Legacy` = model retired by provider; pick another. Each error names its layer — read all of it.
- **New-model quotas default to 0 TPM / 0 RPM** on this account tier. Check Service Quotas → Bedrock → the model's **Geo cross-region** rows (that's what `us.` profiles use; `global.` uses Global rows). Request modest increases (RPM 50 / TPM 200k) — likelier to auto-approve.
- **The daily token budget is small — protect prod.** A day's testing (a few E2E runs + failed experiments' successful halves) can exhaust it. The scheduled 16:00 UTC run needs ~40–60k Haiku tokens (scoring 40 candidates + summarize). Budget experiments accordingly; probe with `max_tokens: 5`; never re-run a multi-model harness without fixing the known failure first.
- Working model ids as of 2026-07: scoring/summarizing `us.anthropic.claude-haiku-4-5-20251001-v1:0` (entitled, works); writer `us.anthropic.claude-sonnet-4-6` (subscribed; quota pending). Sonnet 4.5 subscribed but was never quota'd; Sonnet 4/3.7/3.5 legacy-locked.

## CloudFormation / SAM deploys

- **Deploy flow is two-step by policy:** `sam build` → `sam deploy --no-execute-changeset` → inspect the change table → `aws cloudformation execute-change-set --change-set-name <ARN>` → `wait stack-update-complete`. Blind `--no-confirm-changeset` is blocked by the permission classifier; the execute step itself sometimes gets classifier-blocked (approved before, denied later — it's non-deterministic). If denied twice, hand the exact command to the owner.
- **CFN creates resources with the CALLER's credentials** — deploying a template with a new resource type (SNS topic, etc.) requires pipeline-admin to hold that service's actions, or the stack rolls back. Remember this whenever a template adds its first resource of a kind.
- **`Globals.Function.Timeout: 600` is inherited.** A function with no `Timeout:` already has 600s. Adding an explicit `Timeout:` to a function REDUCES its budget — never add one "for safety."
- Layer changes ripple: any commit touching `lambda/layers/common` produces changeset Modify entries on every function (new layer version ARN). That's normal, not scope creep. `Replacement: False` on everything is the safety check.

## Git / GitHub

- **Pushes use an inline PAT URL** (`git push "https://$(cat ~/projects/00-cr/gh-pat.txt)@github.com/no0ktheali3n/ai-news-pipeline.git" <ref>`); never write the PAT into tracked files, and filter it from output (`| grep -v "https://"`).
- **Because of PAT-URL pushes, local tracking refs (`origin/main`) are STALE.** `git status` saying "up to date with origin/main" is often false. Verify remote state with `git ls-remote`; compute branch diffs against a known base commit (e.g. the version-tag commit), never against local `main` — a stale merge-base once produced a 193MB "review diff" full of pre-hygiene history.

## Testing conventions

- Tests are **dependency-free scripts**: `uv run python tests/<file>.py`. NOT pytest. Fakes live in `tests/stubs.py` (`install_stubs()` must run before importing layer modules; `FAKE_BEDROCK.mode` defaults to `"denied"` — set `"ok"` and reset in `finally`).
- Suites (keep all green): `test_fixes.py`, `test_content_engine.py`, `test_buzz.py`, `test_thread_contract.py`, `test_ab_harness.py`.
- Unit tests seed `top_n`-style functions with clean lists — they do NOT cover real artifact shapes (a sidecar is `{"generated_at", "candidates"}`, not a bare list). After harness/script changes, do one real-shape smoke run before trusting it.
- `summarize_articles` does LOCAL file I/O via module attrs `INPUT_FILE`/`OUTPUT_FILE` (the Lambda handler points them at /tmp). It never touches S3 — don't write tests that seed FAKE_S3 for it.

## Operational invariants

- **Manual pipeline runs**: always `dry_run: true`, and stay outside the 16:00 UTC weekday window (ledger race). Dry runs post nothing and never write the posted ledger.
- **The posted ledger (`memory/posted_library.json`) is the dedup source of truth**; sidecars live under `output/scored/` (30d lifecycle) and are scanned by nothing.
- **One new variable per autonomous run**: don't deploy a second change before the previous one has survived a scheduled run. The durable build ledger is `.superpowers/sdd/progress.md` — read it before resuming anything; append one line per completed step.
- Long waits (quota resets, propagation): detached background watcher loops that probe cheaply and notify — never silent foreground sleeps.

## Git (addendum)
- **Edits made AFTER `git add` are not in the commit** — the stage is a snapshot. If you edit following a bulk `git add -A`, re-add before committing, and run `git status` AFTER committing (a lingering ' M' means the commit is missing your latest change).
- **CI red while local is green → diff committed vs working tree FIRST** (`git status`, `git diff HEAD -- <file>`) before blaming the runner environment. Local suites read the working tree; CI reads the commit.
