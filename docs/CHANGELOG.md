# 📜 CHANGELOG.md  
**Project:** `ai-news-pipeline`  
**Maintainer:** no0ktheali3n  
**Created:** April 2025  
**Purpose:** Version-controlled AI research scraper, summarizer, and social media poster pipeline

---

### [v0.6.0] – EventBridge Integration & Stable Pipeline – 2025-05-07

🐍 **New Features**
- 🎯 Fully automated pipeline now deploys with **EventBridge scheduled triggers** using CloudFormation/SAM.
- 🧠 Memory validation and deduplication logic now runs **before chunking or summarization**, terminating early if duplicates found.
- ✅ Initial support for **scheduled automation**: runs every 4 hours on weekdays (UTC), using `pipeline_lambda` as entrypoint.
- 🔐 Finalized IAM and role policies to support `iam:PassRole` permissions for all Lambda and Scheduler operations.
**adjusted prompt to give slightly more verbose output.  ive noticed ive been getting anywhere between 10-30 views on these and occasionally even a like or two.  going to do a little A/B test and see if longer threads are more or less engaging.

🔧 **Refactors & Stability Enhancements**
- Refined **common utils layer** to support `dry_run` prompt refactoring and centralized utility prompts.
- Hardened permissions and policies for all Lambdas, including scheduler-triggered roles.
- Updated all `sam deploy` and CloudFormation templates to support new scheduled deployment logic and runtime environment consistency.
- Resolved IAM policy bugs causing `iam:PassRole` errors during deployment.

⚠️ **Known Limitations**
- Memory deduplication still scoped to *single-article workflows*. Multi-article deduplication (for chunking) targeted for v0.6.6+.
- Scheduler currently uses **hardcoded parameters** (`scrape_limit = 1`, `chunk_size = 1`). Future update will externalize parameter profile sets.

🧠 **Strategic Significance**
This marks the first version where **"hands-off" automation** is possible. From scraping to posting, all steps are now autonomously scheduled and executed using AWS-native tooling, requiring no human intervention unless an error occurs. This milestone shifts the project from development tool to **production-grade research distribution pipeline**.

### [v0.5.1] – Memory Integration & Refactor Cleanup – 2025-05-03


## 🧠 *New Features*
#This version is deployable and runnable on AWS using defaults, grabs 1 article from arxiv, summarizes it, and posts it to social media in under a minute.  Cleanly exits if duplicate article detected.

* Pipeline now **terminates early** if duplicate articles are detected (prevents redundant summarization/posting).
* Implemented `memcon.py` (Memory Controller) to track scraped articles via a persistent `article_library.json` file in S3.
* Default `scrape_limit` set to **1 article per run** to ensure reliable memory validation until chunking logic is improved.
* Added safe memory fallback logic for missing memory file (initial run scenario).

## 🧹 *Refactors & Improvements*

- Renamed `summary_orchestrator_lambda.py` ➔ `summary_main_lambda.py`
- Renamed `orchestrator.py` ➔ `chunker.py`
- Refined log structure across `scraper`, `summarizer`, `poster` and `pipeline` to enhance readability and consistency.
- Improved function and module separation for better responsibility isolation.

## 🧪 *Known Limitations*

- Current memory system only supports **single-article workflows**; multiple article chunking bypasses memory deduplication.
- Future enhancement (`v0.6.0+`) will support **multi-article deduplication** and **intelligent memory indexing**.

## *Current Parameter Defaults/Overrides*
# Can be overridden by passing event json to pipeline_lambda

scraper: 
  scrape_limit (limits articles scraped, default 1), 
  url (defaults to arxiv, https://arxiv.org/search/?query=artificial+intelligence&searchtype=all&abstracts=show&order=-announced_date_first&size=25&classification-computer_science=y),
  skip_memory (skips memory check for pipeline testing)

chunker:
  chunk_size (each chunk has size N elements, in our case articles, default is 2)

poster: 
  dry_run (posts to X account if false, default true)
  post_limit (limits N posts to social media from start_index, default 1)
  start_index (tells poster which article to start from in index if multiple summarized articles in previous iteration, default 0 - first result)

***DEVNOTE: overriding start_index, post_limit or giving scraper_limit a value higher than 1 CURRENTLY DOES NOT WORK AND WILL BREAK PIPELINE.  

"scraper": ["scrape_limit", "url", "skip_memory"],
    "chunker": ["chunk_size"],
    "poster": ["dry_run", "post_limit", "start_index"]


## 💡 *Strategic Significance*

This update begins the foundation of **state-aware intelligence** in the pipeline. While currently limited to single-article tracking, it lays the groundwork for scalable memory, versioned content protection, and long-term deduplication analytics.


### [v0.5.0] – Pipeline Full Automation Integration – 2025-04-26

**✨ New Features**
- Introduced `pipeline_lambda.py` as unified controller for the full AI research automation cycle.
- Added dynamic payload forwarding (`scrape_limit`, `chunk_size`, `dry_run`, `post_limit`, `start_index`) across scraper, summarizer, and poster functions.
- Integrated structured `logger` output across all modules (no more prints).
- Full CloudWatch observability for all stages: scraping, summarization, and posting.
- Parameterized event JSON to allow flexible ad hoc and scheduled runs.
- Added clean error handling and consistent 200/500 status returns across pipeline stages.

**✅ Verified Completion**
- Scraper Lambda limited article pulls according to `scrape_limit`.
- Orchestrator Lambda chunked, triggered summarization, and reassembled outputs based on `chunk_size`.
- Poster Lambda successfully formatted and posted Twitter threads (with `dry_run` support).
- Pipeline exited with **code 200** on success and **uploaded logs for all operations**.

**🚀 Strategic Significance**
This release completes **MVP: Modular, Automated, and Observable Research-to-Twitter Pipeline**.  
Next planned phase (**v0.6.0**) will focus on **scheduling**, **resiliency**, and **dynamic filtering** based on relevance scoring.

---

### 📝 [v0.4.6] – Poster Lambda Integration & Dry Run Completion – 2025-04-22

**💬 Poster Lambda**
- Created `poster_lambda.py` to post AI summaries as threaded tweets using Tweepy.
- Integrated `post_to_twitter`, `twitter_threading`, and `tweepy_client` via shared `common/utils/` layer.
- Implemented `dry_run` support for preview-only Lambda executions.
- Pulled the latest `final_summarized.json` file dynamically from `output/summarizer/` in S3.
- Added `generate_tweet_thread()` to format tweets, ensuring 280-character compliance.
- Appended hashtags and URLs to increase visibility and engagement.
- Patched edge case: summary variant mismatch (`summary` vs `v1_summary`).
- Enabled structured observability with `get_logger()`-based logging.

**🛠️ Infrastructure**
- Updated `template.yaml` with:
  - `PosterFunction` environment variables: `S3_OUTPUT_BUCKET`, `SUMMARY_OUTPUT_PREFIX`, etc.
  - IAM permissions:
    - ✅ `s3:GetObject`, `s3:ListBucket` scoped to `output/summarizer/`
    - ✅ `secretsmanager:GetSecretValue` for future Twitter credential retrieval

**✅ Verified Dry Run**
- Lambda execution confirmed:
  - Correct summary-to-thread transformation
  - Hashtag logic applied correctly
  - Previewed tweet thread structure via CloudWatch logs
  - Logging operational

**✅ Live Tweet Execution Confirmed**
  - Successfully posted first real AI summary to Twitter in-thread format:
  - Thread ID: Tweet Link ✅
  - Full article summary posted in multitweet thread via Claude summarizer.
  - Logging confirmed in CloudWatch, output on Twitter.
  - Hashtag logic, threading, and metadata output all operational.

> 🔁 This version completes all core functionality for the Poster module, marking the first live publishing phase of the pipeline. The system is now fully capable of automated, credential-secure AI summary posting. Remaining features (article offset, multi-post resume, thread backup) targeted for v0.5.0.



### 🟦 [v0.4.5] – Summarizer Lambda & Chunked Orchestration - 2025-04-(20-21)

- 🧠 Introduced `summarizer_lambda.py`, receiving chunked input via Lambda events
- 📚 Refactored summarizer to combine summary + hashtag into one Claude 3.5 Sonnet prompt
- 🔁 Built `utils/orchestrator.py`:
  - `split_into_chunks()` – divides full scrape dataset into discrete chunks
  - `invoke_lambda_for_chunk()` – asynchronously triggers summarizer lambdas
  - `reassemble_chunks_from_s3()` – rebuilds full article set from S3 output
- 🧪 Implemented retry logic with jittered delay for Claude Bedrock throttling
- ⚙️ Added `run_id` timestamp logic to group chunk outputs under unique run sessions
- 📂 Reassembled output now sorted by chunk index, not S3 write time
- 📤 Uploaded final merged JSON to `final_summarized_<run_id>.json` in S3
- 📤 Integrated orchestrator summarizer into `template.yml`

> Achieves full orchestration of distributed summarization with reassembled output ready for posting

---

### 🟦 [v0.4.4] – Scraper Lambda Deployment - 2025-04-(19-20)

- 🛠️ Adjusted `scraper.py` and generated `scraper_lambda.py` for Lambda compatibility
- 🪣 Configured dynamic article limits + S3 output pathing using environment variables
- 🔐 Ensured proper IAM permissions for `s3:PutObject` scoped to `ScraperOutputPrefix`
- ✅ Verified scraper Lambda works independently and writes to correct S3 prefix
- 📦 Integrated scraper, summarizer, poster into `template.yaml` for `sam build && sam deploy`

> First Lambda module deployed into production with cloud-native output handling

---

### 🚀 [v0.4.3] — AWS Deployment and IAM Architecture - 2025-04-14

- 📦 Deployed full Lambda pipeline to AWS via SAM:
  - `scraper_lambda.py`
  - `summarizer_lambda.py`
  - `poster_lambda.py`
- 🔐 Created and attached IAM user groups for:
  - `ai-pipeline-admin` with full Lambda/IAM/SecretsManager privileges
  - `ai-pipeline-contributor` with scoped log and secrets access
- 🧾 Refined `template.yaml` to define:
  - All Lambda functions with separate roles
  - Environment configuration (excluding reserved AWS keys)
  - Outputs for live ARNs
- 🧪 Verified working deployment with `sam build && sam deploy`
- ✅ Rolled back and resolved permission errors related to:
  - `iam:CreateRole`, `iam:AttachRolePolicy`, tagging constraints
  - AWS reserved variable `AWS_REGION` conflict

> This version marks the full lift of the local stack into a cloud-native structure and sets the foundation for unified orchestration in `v0.5.0`.


## [v0.4.2] - 2025-04-14
### ✨ Enhancements & Polish
- ✅ Added support for `--dry-run` flag to preview tweet threads without posting.
- ✅ Added `--variant` CLI argument for summary style selection (defaults to `v1_summary`).
- ✅ Integrated structured logging using Python’s `logging` module:
  - Logs to both console and rotating file (`poster_pipeline.log`).
  - Configurable log level via `.env` (`LOG_LEVEL=INFO`, `DEBUG`, etc.).
- ✅ Implemented `.env` validation to check for required Twitter credentials before posting.
- ✅ Archived `summarized_output.json` to timestamped file in `/archive/` after successful post.
- ✅ Preserved user-facing `print()` statements for notebook/debug use, while logging in parallel.
- ✅ Consistently separated CLI and Lambda logic.

### 🧹 Cleanup
- ✅ Moved logger setup into reusable `utils/logger.py` module.
- ✅ Ensured `.env.example` is updated with `LOG_LEVEL`.

### 📂 Files Affected
- `utils/post_to_twitter.py`
- `utils/logger.py`
- `.env.example`
- `CHANGELOG.md`

---

🎯 This version completes our local CLI polish sprint. Next up: Deployment, CI/CD, and Bedrock Secrets Manager integration.


## [v0.4.1] - 2025-04-13
### 🎉 Added
- ✅ **Tweet threading fully operational** – Entire article summaries are now posted as threads via Tweepy.
- ✅ **`post_to_twitter.py`** implemented for posting from `summarized_output.json`.
- ✅ **`twitter_threading.py`** added to utils for generating properly chunked tweet threads.
- ✅ Interactive preview with character counts and user prompt before posting.
- ✅ Basic retry delay handling and graceful failure logging.

### ✅ Validated
- Full end-to-end test completed: single-thread article summary successfully posted to Twitter.
- Verified that posting works for both first tweet and all replies using v2 API.

### 🛠 Internal
- Resolved `403 Forbidden` errors by switching fully to `Client.create_tweet()` in Tweepy v4+.
- Updated Tweepy utility to use environment-loaded credentials correctly.
- Fixed module import errors by modifying `sys.path` and restructuring import paths.


## [v0.4.0] - 2025-04-12
### Added
- `utils/tweepy_client.py`: Modular Tweepy integration with support for tweet threading and test CLI.
- `.env.example`: OAuth1.0a token variables required for Twitter posting.
- Poster logic now exports tweet metadata to both JSON and CSV.
- First successful tweet posted via Tweepy client.

### Changed
- Finalized poster formatting logic to prioritize clarity and character-efficient summaries.

### Notes
- Twitter posting currently uses OAuth1.0a with v2 endpoint (`create_tweet`).
- Future upgrades may include OAuth2 flow and media/alt text support.
- Future upgrades will move to integrate poster into AI summary pipeline.


## [v0.3.0] - (2025-04-11)
### ✨ Added
- Claude-powered summarizer module with AWS Bedrock integration.
- Prompt templates for v1 (social/engaging) and v2 (technical/concise) summaries.
- Hashtag generation via Claude and appended to summary metadata.
- Retry mechanism for throttling errors with exponential backoff and jitter.
- Full local support via `.env` environment variables.
- Logging of estimated token usage and model version.
- Jupyter-based prompt testing in `notebooks/summarization-lab.ipynb`.

### 🛠️ Changed
- Refined `.env.example` with Bedrock-specific placeholders.
- Added summary and hashtag fields to `summarized_output.json` format for downstream poster usage.

### 🧪 Testing
- Summarizer tested with Claude 3.5 Sonnet on AWS Bedrock.
- Manual validation of summary accuracy, hashtag quality, and retry behavior.

### 🔐 Security
- Secret keys moved to `.env` and properly excluded via `.gitignore`.
- AWS IAM user/role configured with Bedrock access policy.

---

✅ This version completes the **AI Summarization Layer** for the pipeline. The next milestone (`v0.4.0`) will finalize tweet formatting and prepare for Tweepy/X API integration.

## ✅ [v0.2.1] – (2025-04-10)  
### Summary  
Stabilized and security-hardened scraper pipeline. Removed secret key exposure, added `.env.example`, implemented auto-versioning, and tested summarizer + poster locally. Streamlined ArXiv article parsing and improved output consistency.

### ✅ Added  
- `.env.example` template for secure environment setup  
- `.gitignore` to prevent secrets from being committed  
- Auto-trimming of tweets for 280-character Twitter formatting  
- Dynamic hashtag generation from summarizer output  
- Claude Sonnet 3.5 Bedrock integration for summarization  
- Retry logic for Bedrock API throttling  
- Jupyter notebooks for summarizer and poster module previews  

### 🛠️ Fixed  
- **Redundant URL bug**: `base_url + href` caused malformed links  
  - **Fix**: Removed `base_url` in `scraper.py` logic  
- **AWS keys pushed accidentally**  
  - Secrets were detected by GitHub Push Protection  
  - BFG Repo Cleaner used with `--no-blob-protection` to scrub history  
  - `.env` untracked and `.env.example` introduced  
- **VSCode module resolution issue (`utils` not found)**  
  - Fixed by appending project root to `sys.path`  
- **Virtual environment activation error in PowerShell**  
  - Resolved by setting execution policy to `RemoteSigned`  
- **FileNotFoundError in summarizer/poster notebooks**  
  - Fixed by dynamically resolving path via `os.path.join(__file__)`  
- **Throttling from Claude API (Bedrock)**  
  - Implemented exponential backoff and graceful retry logic  

### 🔐 Security Actions  
- Verified no real secrets were committed (`git log -p | Select-String`)  
- Enabled GitHub Secret Scanning and Push Protection  
- Revoked and rotated AWS credentials  
- Ensured `.env` is now untracked and ignored  

---

## 🧪 [v0.2.0] – Initial Refactor Commit (Pre-Release)

### Summary  
Refactored `scraper-alpha` from a simple prototype into a modular pipeline. Introduced structure, utilities, and isolated web scraping logic into a dedicated `ScraperClient` class.

### ✅ Added  
- `ScraperClient` class with configurable target URL  
- `utils/user_agents.py` for rotating user agents  
- `utils/request_helpers.py` for random request delays  
- Initial scraping logic for ArXiv articles (AI + CS filters)  
- Article parsing for title, link, authors, and abstract snippet  
- Export to `test_output.json`  
- Tagged pre-release as `v0.2.0`  

### ⚠️ Known Issues at the Time  
- Redundant URL bug (later fixed in `v0.2.1`)  
- No environment variable management or `.env` file structure  
- No LLM integration or summarization/posting modules  

---

## 📌 Notable Development Events

- **Claude v3.7 Bedrock error**  
  > `Invocation with on-demand throughput isn’t supported.`  
  - ✅ Switched to Claude 3.5 Sonnet for reliable support

- **Push Protection Triggers**  
  - ✅ GitHub blocked commit before secrets reached remote  
  - ✅ BFG Repo Cleaner used to wipe historical traces

- **Jupyter Notebook adoption**  
  - ✅ Chosen for previewing summarizer and poster logic outside Lambda

- **VSCode edge-case interpreter issues**  
  - ✅ Confirmed interpreter path manually  
  - ✅ Switched to CLI-only execution in some test cases

---

## [v0.1.0] – 2023-10
### 🛠 Prototype
- Initial scraper built using BeautifulSoup.
- First version very basic, manually developed to automate scraping general data 

---

