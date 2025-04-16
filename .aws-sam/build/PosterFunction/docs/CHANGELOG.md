# 📜 CHANGELOG.md  
**Project:** `scraper-alpha`  
**Maintainer:** no0ktheali3n  
**Created:** April 2025  
**Purpose:** Version-controlled AI research scraper, summarizer, and social media poster pipeline

---
## [0.4.2] - 2025-04-14
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


## [0.4.1] - 2025-04-13
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


## [0.4.0] - 2025-04-12
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

