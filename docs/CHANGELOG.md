# 📜 CHANGELOG.md  
**Project:** `scraper-alpha`  
**Maintainer:** no0ktheali3n  
**Created:** April 2025  
**Purpose:** Version-controlled AI research scraper, summarizer, and social media poster pipeline

---

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

## ✅ v0.2.1 – (2025-04-10)  
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

## 🧪 v0.2.0 – Initial Refactor Commit (Pre-Release)

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

## 🔮 Next Steps

| Version | Goals |
|---------|-------|
| `v0.3.0` | Merge summarizer + poster modules into a unified Lambda pipeline |
| `v0.4.0` | Claude prompt tuning + editorial control features |
| `v0.5.0` | Add Tweety integration for Twitter/X automation |
| `v1.0.0` | Production release with CI/CD, Secrets Manager, and scheduling |

---

