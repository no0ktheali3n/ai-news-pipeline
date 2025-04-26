# Technical Diary

This file documents major technical decisions, fixes, lessons learned, and recurring patterns.

---

## Phase 0 - first scraper (10/2023)
-Created initial `scraper-alpha` using BeautifulSoup
-very basic


## 🌱 Phase 1 – Scraper Foundation (04/07/2025)
- Refactored and updated initial `scraper-alpha`
- Defined target structure from arXiv.org advanced search
- Implemented random user agents and human-like delay via `random_delay()`
- Integrated basic pandas export to `.json`

### Lessons:
- arXiv structure is relatively stable but still needs tag inspection
- User-agent rotation helps avoid soft blocking and cloudflare

---

## 🧪 Phase 2 – Summarizer Evolution
- Integrated AWS Bedrock and Claude 3.5 (then tested 3.7)
- Hit throttling issues → resolved with retry + backoff logic
- Prompt v1 and v2 A/B testing implemented inside `summarizer.py`
- Token usage logging + character budgeting added
- Output schema enhanced with `summary_v1`, `summary_v2`, `hashtags`, etc.

### Challenges:
- Throttling required exponential retry handling (sensitive to backoff)
- AWS Bedrock doesn’t always fail predictably (JSON fallback logic needed)

---

## 🖋 Phase 3 – Poster Formatter
- `poster-lab.ipynb` created to format tweets with full trimming logic
- Added dynamic hashtag injection from summarizer output
- Found and fixed link formatting bug (double base URL)

---

## 🔐 Secrets Incident (2025-04-10)
- Accidentally committed AWS credentials to public repo
- GitHub Push Protection blocked push
- Used BFG Repo Cleaner and `git filter-repo` to purge Git history
- Added `.env.example` and full `.gitignore` enforcement

---
## 🖋 Phase 4 - Social Media Integration

## Tweepy development (2025-04-12)

Problems Encountered:
🧱 Initial 403/404 Forbidden error despite valid credentials.
🔍 Discovered missing app permissions (read/write not enabled).
🔐 OAuth 1.0a user context required — OAuth 2.0 not sufficient for tweeting.
🛠️ Misalignment between Twitter’s UI vs actual API capabilities caused confusion.

Solutions:
✔ Enabled read/write permissions in dev portal under project > app > settings.
✔ Regenerated OAuth 1.0a access tokens and added to .env.
✔ Used Tweepy’s Client.create_tweet() to verify tweet delivery.
✔ Confirmed success via printed tweet URL and live post check.

Recommendations:
🔒 Store sensitive tokens only in .env, commit .env.example instead.
🔁 Consider support for token rotation or Twitter app permissions audit as part of future hardening.
🧪 Use if __name__ == "__main__": block for standalone local tests on every module.

## 💡 Roadmap
- Migrate from `.env` to Secrets Manager for cloud usage
- Add Twitter/X Tweepy automation as optional Lambda trigger
- CI/CD automation via GitHub Actions + SAM deployment
- Add HuggingFace summarization fallback or multi-model support

## Phase 5 - Cloud Integration (AWS)

**AWS IAM + SAM Deployment v0.4.3 (2025-04-12)**

**Milestone:** First successful deployment of the full AI News Pipeline (Scraper, Summarizer, Poster) to AWS Lambda using SAM.

---

### 🏠 Objective
Deploy all three pipeline components to AWS Lambda via SAM CLI with proper IAM-based security, least privilege access, and environment validation. Ensure the project is production-ready for modular triggers and automation.

---

### ⚡ Problems & Challenges Faced

#### 1. **IAM User Group Setup**
- **Problem:** No predefined user structure. Unsure whether to assign permissions per user or group.
- **Solution:** Created two IAM groups:
  - `ai-pipeline-admin` — Full deployment, management, secrets, logs, and Bedrock access.
  - `ai-pipeline-contributor` — Read-only logs + minimal Bedrock invocation.
- **Outcome:** User permissions are now modular and easily assignable.

#### 2. **IAM Policy Incompleteness**
- **Problem:** Initial deployments failed due to missing permissions for `CreateRole`, `AttachRolePolicy`, etc.
- **Solution:** Expanded `ai-pipeline-admin-policy` to include:
  ```json
  "Action": [
    "iam:CreateRole", "iam:AttachRolePolicy", "iam:PutRolePolicy",
    "iam:DeleteRole", "iam:DetachRolePolicy", "iam:DeleteRolePolicy",
    "iam:TagRole", "iam:UntagRole"
  ]
  ```
- **Outcome:** Full Lambda stack creation works as intended.

#### 3. **CloudWatch Log Access Confusion**
- **Problem:** Couldn’t locate `logs:ViewLogEvents`, permissions UI split by service (CloudWatch vs Logs).
- **Solution:** Found `logs:GetLogEvents` under the dedicated **Logs** service. Enabled in contributor and admin roles.
- **Lesson:** AWS UI separates CloudWatch metrics vs Logs permissions.

#### 4. **Environment Variable Conflicts (`AWS_REGION`)**
- **Problem:** CloudFormation rejected Lambda creation due to `AWS_REGION` being a reserved environment variable.
- **Solution:** Removed `AWS_REGION` from `Globals.Environment.Variables` in the SAM template.
- **Additional Fix:** Rebuilt the SAM artifacts with:
  ```bash
  sam build
  sam deploy
  ```
- **Outcome:** Stack deployed successfully after this change.

#### 5. **Rollback-Complete State Blocks Re-Deploy**
- **Problem:** CloudFormation stack got stuck in `ROLLBACK_COMPLETE`, blocking further deploy attempts.
- **Solution:** Used AWS Console to delete the stack manually before retrying `sam deploy`.
- **Lesson:** In dev mode, avoid enabling rollback unless testing failure paths.

---

### 🏑 Achievements
- ✅ IAM roles modularized
- ✅ Admin/contributor user groups secured
- ✅ First SAM deployment succeeded for all three Lambda functions
- ✅ CloudFormation output confirmed with correct ARNs for each function:
  - `ai-news-scraper`
  - `ai-news-summarizer`
  - `ai-news-poster`

---

### 💡 Lessons for the Future
- Keep IAM policies flexible but explicit. Use least privilege, and always test with real users.
- Rebuild (`sam build`) before every deploy to avoid stale artifacts.
- Validate environment variables against [reserved Lambda keys](https://docs.aws.amazon.com/lambda/latest/dg/configuration-envvars.html).
- Manual deletion of stacks may be necessary during development.
- Consider enabling version control of `samconfig.toml` after first successful deploy.

---

### ⚙ Next Tasks
- Hook up CloudWatch log streams for validation
- Begin testing event-driven triggers
- Integrate Secrets Manager and Bedrock invocation permissions into function-level roles

---
**Status:** SAM environment and IAM user scaffolding complete. Ready to build automation layer.

🚀 **v0.4.3** milestone complete.

**AI News Pipeline - Lambda Deployment & Debug Log**

**Date:** April 17, 2025   
**Context:** Standalone deployment and debugging of the AI News Pipeline AWS Lambda architecture (scraper, summarizer, poster).

---

### Overview:
The purpose of this document is to track issues encountered during deployment and testing of individual Lambda functions for the AI News Pipeline project and how each was resolved. This will serve as a technical reference for future debugging and CI/CD pipeline optimization.

---

## 🐞 Deployment & Build Issues

### 1. **Missing IAM Permissions (initial deploy)**
- **Error:** `iam:CreateRole`, `iam:AttachRolePolicy`, `iam:DeleteRolePolicy` not authorized.
- **Fix:** Updated the `ai-pipeline-admin-policy` to include missing IAM actions:
  ```json
  "Action": [
    "iam:CreateRole",
    "iam:AttachRolePolicy",
    "iam:DeleteRolePolicy",
    "iam:PutRolePolicy",
    "iam:DetachRolePolicy"
  ]
  ```

---

### 2. **Lambda Reserved Environment Variables Error**
- **Error:** `AWS_REGION is a reserved key` in environment variables.
- **Fix:** Removed `AWS_REGION` from Lambda environment configuration. Instead, accessed it using `os.getenv("AWS_REGION", "us-east-1")` in-code only.

---

### 3. **File Size Limit Exceeded (262MB)**
- **Error:** `Unzipped size must be smaller than 262144000 bytes`
- **Fix:**
  - Used `pip freeze > requirements.txt` to generate dependency list.
  - Cleaned up non-essential dev dependencies using `pip uninstall` and `pip-chill`.
  - Removed boto3 (native on aws)
  - Verified build sizes in PowerShell:
    ```powershell
    Get-ChildItem .aws-sam/build/* -Directory | ForEach-Object {
      $size = (Get-ChildItem $_.FullName -Recurse | Measure-Object -Property Length -Sum).Sum
      $sizeMB = [math]::Round($size / 1MB, 2)
      "{0} - {1} MB" -f $_.Name, $sizeMB
    }
    ```
  - Result: All three functions reduced to ~<100MB after cleanup.

---

### 4. **Local Build Failing Due to `pywinpty`, `pywin32`**
- **Error:** `ResolveDependencies failed` with wheel-related issues.
- **Fix:** Removed incompatible packages from `requirements.txt`.
- **Alternative Fix:** Used container build:
  ```bash
  sam build --use-container
  ```
  - Confirmed Docker was running and used Python 3.11 container.

---

### 5. **SAM CLI Build Failing with Hash Mismatch**
- **Error:** `ERROR: THESE PACKAGES DO NOT MATCH THE HASHES FROM THE REQUIREMENTS FILE.`
- **Fix:** Cached hash, deleted aws-sam and rebuilt:
  ```powershell
  Remove-Item -Recurse -Force .aws-sam

  sam build --use-container  
  ```

---

### 6. **Successful Redeploy**
- Status: All three Lambda functions deployed successfully:
  - Scraper: `ai-research-scraper`
  - Summarizer: `ai-research-summarizer`
  - Poster: `ai-research-poster`
- CloudFormation automatically deleted and replaced old versions of functions.

---

## ✅ Next Steps: Function Testing
- [✅] **ScraperFunction** - Invoke and confirm ArXiv data is parsed and saved to S3.
- [ ] **SummarizerFunction** - Verify latest scraper output is summarized and uploaded.
- [ ] **PosterFunction** - Confirm summary is threaded and optionally previewed or posted.

---
### [2025-04-18] ✅ First Successful Scraper Lambda Deployment + Test

- **What**: `ScraperFunction` Lambda tested via AWS Console.
- **How**: Used default arXiv AI query. Triggered Lambda manually post-deploy.
- **Output**: Successfully scraped and stored 25 articles as structured JSON to S3.
- **S3 Path**: `s3://<bucket-name>/ai-research-pipeline/output/scraper/scraped_articles_20250419_042540.json`
- **Stack**: Deployed via AWS SAM, layered via Lambda Layer for utils, `boto3` minimal dependency.
- **Notes**:
  - Working directory confirmed as `/var/task`
  - Random delays correctly simulated
  - S3 upload succeeded with `put_object`
- **Next Step**: Begin testing `SummarizerFunction` using this S3 output as input.

Scripts were refactored into a shared Lambda Layer (/lambda/layers/common/python/utils) and attached to all 3 functions in the SAM template via the Layers: property. The layer helps minimize duplication and keeps deployment bundles lighter by separating reusable logic.

⚠️ Problems Encountered

Issue	Resolution
❌ Initial import errors — Lambda could not find lambda.scraper_lambda or local utils during deployment or runtime.	Adjusted CodeUri in the template.yaml to point to correct folders and moved reusable scripts into a shared Lambda Layer.
❌ Build size exceeded 262 MB Lambda limit	Removed local boto3, cleaned unused packages in requirements.txt, and moved shared utils to a dedicated Lambda Layer, reducing bundle size across all functions.
❌ SAM couldn't find utils despite being copied into lambda/	Layer strategy implemented. Defined in template.yaml as:
yaml
Copy
Edit
Layers:
  - !Ref CommonUtilsLayer
And pointed to lambda/layers/common/ | | ❌ Docker container utf-8 decode error (0xff) during sam build --use-container | Ensured requirements.txt was UTF-8 encoded and recreated it manually from terminal using pip freeze or pip list. | | ❌ Stack collisions (name already exists) | Deleted failed CloudFormation stacks (ai-news-pipeline, ai-research-pipeline) via AWS Console and CLI. Rebuilt clean deployments. | | ❌ Template param mismatch (S3_OUTPUT_BUCKET vs S3OutputBucket) | Re-aligned all parameter names in template.yaml, samconfig.toml, and Lambda env vars to match naming conventions (PascalCase for template inputs). |

✅ Execution Results (Successful Run)
Triggered From: AWS Lambda Console (manual test)

URL Queried: arxiv.org with "artificial+intelligence" search

Simulated Human Behavior: ✅ random delays, ✅ rotating user-agent

File Saved: scraped_articles_20250419_042540.json

Record Count: 25 articles

S3 Location:
s3://aws-sam-cli-managed-default-samclisourcebucket-<id>/ai-research-pipeline/output/scraper/

📌 Outcome
ScraperFunction is now fully functional, modular, and integrated with:

📦 S3 Input/Output pipeline

🧱 Reusable Layer shared across all functions

✅ Output confirmed via S3 console and JSON inspection

👣 Next up: Begin testing SummarizerFunction by reading from this S3 output and saving summaries + hashtags to output/summarizer/

### [2025-04-(20-21)] Claude Summarizer Evolution & Chunking Pipeline Deployment

---

### Overview:
Over the course of the past 48 hours, we successfully transitioned our Claude-based AI paper summarizer from a single-threaded sequential processor to a scalable, Lambda-distributed, chunked-processing pipeline. This milestone marks a significant leap in performance, throughput, and operational resilience for our AI News Poster Pipeline.

---

### Step 1: Refining the Non-Chunked Summarizer (April 19)

**Goals:**
- Generate both summaries and hashtags in one Claude call.
- Improve reliability against Bedrock throttling.
- Validate JSON parsing and enforce prompt structure.

**Actions Taken:**
- Consolidated summary and hashtag generation into a single prompt function (`build_summary_and_hashtag_prompt`).
- Updated parsing logic to handle structured JSON reliably.
- Implemented backoff retry logic using exponential delay and random jitter.
- Finalized `summarize_with_claude()` to return a complete structured response.
- Confirmed correct behavior by processing articles sequentially with complete outputs.

**Outcome:**
Achieved 100% successful return of summaries and hashtags using Claude with proper formatting. However, the sequential nature of the process revealed performance limitations (took 6-8 minutes to summarize 5 articles, NOT scalable!)

---

### Step 2: Architecting the Chunking Infrastructure (April 19-20)

**Objectives:**
- Parallelize summarization via Lambda chunking.
- Offload orchestration logic to a reusable module.
- Allow each summarizer Lambda to process a dedicated chunk of articles.

**Key Components Introduced:**

- `utils/orchestrator.py`:
  - `split_into_chunks()` - Slices full input dataset.
  - `invoke_lambda_for_chunk()` - Asynchronously triggers Lambda invocations.
  - `orchestrate_chunks()` - Drives end-to-end distribution of work.
  - `reassemble_chunks_from_s3()` - Collects all chunk outputs into a single `summarized_output.json`.

- `summarizer_lambda.py`:
  - Modified to accept a payload from the orchestrator (`chunk_id`, `articles`).
  - Processes only the articles passed via event.
  - Writes output to `/tmp`, then uploads to S3 with a unique timestamped key.

---

### Step 3: Deployment & Testing

**Deployment:**
- Integrated chunking orchestrator, updated Lambda templates and permissions.
- Resolved SAM build circular dependency errors involving shared layers.
- Cleaned environment variables and automated chunk naming with UUID.

**Testing:**
- Triggered `orchestrator_lambda` from the AWS Console.
- Verified correct invocation of multiple `summarizer_lambda` functions.
- Reassembled chunk results via CLI and validated JSON integrity.

---

### Next Steps:
- Create an automated `summarizer_batch_runner.py` or Lambda function to:
  - Call orchestrator.
  - Wait/poll for job completion.
  - Call `reassemble_chunks_from_s3()`.
  - Trigger poster Lambda with reassembled output.
- Optimize chunk size dynamically based on token budget or Lambda runtime.
- Add metadata tracking per chunk for performance monitoring and reprocessing.

---

### Conclusion:
The system now supports scalable, parallel AI summarization with robust output consolidation. We've moved from a single-threaded tool to a distributed summarizer service, increasing throughput and paving the way for full automation in the AI news publishing pipeline.  The only thing holding us back are timeouts from Claude 3.5 and the Bedrock API were calling it from.  May need to revisit waits later.

### ### [2025-04-(20-21)] ✅ Claude Summarizer Evolution & Chunking Pipeline Deployment Continued

---

### 🧠 Overview:
Transitioned the Claude-based AI paper summarizer from a sequential local processor to a Lambda-distributed, chunked-processing pipeline. This marks a significant leap in performance, fault tolerance, and throughput for the AI News Poster Pipeline.

---

### 🟩 Summarizer Lambda

**What:**  
- 🧠 Integrated Claude 3.5 Sonnet using a single unified prompt (summary + hashtags)  
- 🔄 Added exponential backoff + jitter to handle Bedrock throttling  
- 🧱 Introduced chunking: each Lambda invocation handles 2–5 articles  
- 🧾 Outputs structured results (JSON) with `run_id` + `chunk_id`-tagged filenames  
- 🛠️ Fixed early bug: missing `run_id` → failed reassembly during orchestration  

**How:**  
- Rewrote `summarizer.py` to consolidate summary + hashtag prompts  
- Created `summarizer_lambda.py` to accept `chunk_id`, `articles[]`, `run_id`  
- Outputs saved to `/tmp/`, then uploaded to S3 for chunk collection  

---

### 🟩 Orchestrator Module

**What:**  
- 🧵 Rewrote `orchestrator.py` for chunk-based coordination of summarizer Lambdas  
- 🪣 Polls S3 until all expected chunks for `run_id` are available  
- 🧩 Reassembles chunks in original source order using regex-sorted filenames  
- 📦 Uploads final combined results to `final_summarized_<run_id>.json` in S3  

**How:**  
- `orchestrate_chunks()` triggers async Lambdas with randomized cooldowns  
- `reassemble_chunks_from_s3()` waits for `expected_chunk_count` using `run_id`-tagged S3 keys  
- Bug fix: default S3 sorting by `LastModified` led to incorrect order → fixed via `chunk-<index>` extraction  

---

### ❌ Problems Encountered

- `[Errno 30]` — Attempted to write output to root directory → fixed by using `/tmp/`  
- ❌ Prefix mismatch between orchestrator and summarizer output path  
- ❌ Payload bug: `run_id` sent as `run` → caused missed chunk detection during reassembly  
- ✅ All resolved with consistent env variables and key naming refactor  

---

### ✅ Outcome

- Reassembled full summarization pipeline now operational in Lambda  
- Summarizer modules now work reliably with throttling management  
- Output is consistently ordered, accurate, and available for posting  
- S3 final output is saved with timestamped `run_id` for traceability  

---

### 🔜 Next Steps

- ⚙️ Implement `poster_lambda.py` and wire into orchestration  
- 🔁 Enable scraper → summarizer → poster automation  
- 📊 Consider tracking chunk failures with metadata to support selective retries  


To be updated as testing progresses.

---

### [2025-04-22] ✅ Poster Lambda Deployment (Dry Run Completion)

---

## 🦰 Overview:
- Built `poster_lambda.py` to post summarized outputs as threaded tweets using Tweepy.
- Implemented structured dry-run capability for safe preview without posting to Twitter.

## 🟩 Poster Lambda (Dry Run Phase)

**What:**
- 📦 Pulled final summarized JSON from S3 dynamically.
- 🛠️ Structured each article into a multi-tweet thread using `generate_tweet_thread()`.
- 🧪 Added local dry-run preview showing tweet structure and character counts.
- 🛡️ Verified Twitter API credential retrieval with `secretsmanager:GetSecretValue`.

**How:**
- Cleaned and upgraded `post_to_twitter.py` with logger-based observability.
- Fixed missing `.env` handling for Lambda runtime separation (dot-env only for local).

**Problems Encountered:**
- ⛔️ Initial EOFError on dry-run due to missing user input prompt → fixed by full dry-run bypass.

---

### [2025-04-23] ✅ SecretsManager Integration & Poster Lambda Full Validation

---

## 🦰 Overview:
- Finalized API key retrieval from AWS Secrets Manager into Tweepy client at runtime.

## 🟩 Security Improvements

**What:**
- 🔐 Bound `TwitterAPICreds` secret to poster Lambda's environment securely.
- 🔒 Replaced local environment secrets with dynamic retrieval inside `tweepy_client.py`.

**How:**
- Updated template.yaml to include correct secret resource ARNs.
- Refactored Tweepy initialization to pull credentials dynamically only when needed.

**Problems Encountered:**
- ⛔️ Secrets policy mismatch at first → corrected `secretsmanager:GetSecretValue` permissions.

---

### [2025-04-24] ✅ Full Pipeline Controller Scaffolding

---

## 🦰 Overview:
- Designed and scaffolded `pipeline_lambda.py` to orchestrate scraper → summarizer → poster as a single entrypoint.

## 🟩 Pipeline Controller

**What:**
- 🦰 Introduced dynamic event forwarding: scraper limit, chunk size, post limit, dry run flag.
- 🛠️ Built utility function `invoke_lambda()` for modular, controlled Lambda invocation.
- ⏳ Introduced intermediate stabilization sleeps after scrape/summarize stages.

**How:**
- Fully parameterized payload builds for modularity and override flexibility.
- Used explicit payload builders per stage: scrape, orchestrate, post.

**Problems Encountered:**
- ⛔️ JSON encoding errors due to emojis in Lambda logs → replaced emojis with ASCII-only logs.

---

### [2025-04-25] ✅ Full Pipeline Execution Test + Critical Fixes

---

## 🦰 Overview:
- Successfully ran scraper → summarizer → poster end-to-end inside a Lambda-controlled session.

## 🟩 End-to-End Validation

**What:**
- 📰 Scraped latest ArXiv articles with limit control.
- 📚 Summarized scraped articles in S3 chunked format.
- 🐧 Generated Twitter threads in dry-run preview mode.

**How:**
- Verified that all intermediate S3 outputs were correctly produced (scraper, summarizer).
- Fixed critical payload mismatch where scraper was ignoring limit due to wrong payload keys.

**Problems Encountered:**
- ⛔️ Scraper defaulted to 8 articles because scraper Lambda expected `"limit"`, but pipeline sent `"scrape_limit"` → corrected mapping via stage-specific payload override.
- ⛔️ Unicode encoding crash in logs → fixed by standardizing logger output to ASCII characters only.

---

### [2025-04-26] 🚀 Pipeline Milestone Reached: v0.5.0

---

## 🦰 Overview:
- Officially completed fully modular, serverless, cloud-native AI Research Automation Pipeline.
- All modules now execute properly in controlled sequence with dynamic configuration.

## 🟩 Highlights

**Accomplishments:**
- ✅ Parameterized full stack control via single test event JSON.
- ✅ Dry-run and live posting capabilities integrated safely.
- ✅ Dynamic chunking, multi-stage S3 handoff, Twitter formatting, and posting all functional.
- ✅ Lambda CloudWatch logging operational across all modules.

**Architecture Snapshot:**

| Stage | Lambda | Function |
|:-----|:-------|:---------|
| 1. Scraper | `ai-research-scraper` | Scrape articles |
| 2. Summarizer | `ai-research-summary-orchestrator` + `ai-research-summarizer` | Summarize with Bedrock |
| 3. Poster | `ai-research-poster` | Post summaries to Twitter |

**Problems Encountered (Final Fixes):**
- ⛔️ `run_id` unassigned edge case for single chunk summarization → patched orchestrator fallback.
- ⛔️ Minor CloudFormation template errors (`PipelineFunction` indentation) → resolved.

---

# ✅ Current State:

| Component | Status |
|:-----------|:--------|
| Scraper Lambda | ✅ Stable |
| Summarizer Lambda + Orchestrator | ✅ Stable |
| Poster Lambda | ✅ Stable |
| Unified Pipeline | ✅ Stable |

---

# 🛄️ Roadmap for v0.5.1+:

- 🔄 Add dynamic event triggers (scheduled, or new content detection).
- ⚡ Add memory to track posts and avoid/tactically schedule reposts
- ⚡ Add intelligent retries for partial failures.
- 🔥 Enhance poster to auto-resume threads based on memory of last posted ID.
- 🦰 Explore relevance ranking / trending mechanisms to prioritize highest-quality articles.

---

_Last updated: 2025-04-26_
