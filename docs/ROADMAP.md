# 🛣️ AI News Poster Pipeline – Roadmap v2

This roadmap outlines the strategic path toward a fully automated, serverless CI/CD-enabled AI news summarization and publishing system. Each version builds toward robustness, modularity, and long-term scalability.

---

## ✅ Completed Releases

### v0.1.0 — Initial Proof of Concept
- Simple site-specific scraper using BeautifulSoup
- CLI-based local scraping and printing of raw article titles

### v0.2.0 — Modular Scraper with Utilities
- ArXiv-specific selector logic with BeautifulSoup
- User-agent randomization and human-like delays
- Secret key removal, `.env.example`, and `.gitignore`

### v0.2.1 — Output Redundancy Fixes
- URL redundancy patch (base URL no longer double-appended)
- Markdown documentation added (`README.md`, `CHANGELOG.md`, `TECHNICAL_DIARY.md`)

### v0.3.0 — Claude Summarizer via AWS Bedrock
- Bedrock integration for multi-prompt summaries (v1 fun/engaging, v2 technical)
- Retry logic and token/cost tracking per article
- Auto-saving of summarized output as JSON

### v0.4.0 — Poster Formatting + Export
- Hashtag merging (default + dynamic Claude-suggested)
- Twitter character trimming logic
- Output previews + export to CSV and JSON

### v0.4.1 — Tweepy Integration + Threaded Summary Posting
- End-to-end working pipeline with thread handling
- OAuth credentials securely managed in `.env`
- Tweet preview with confirmation before posting

### v0.4.2 — Polish and UX Improvements
- CLI flags for dry run, variant choice, verbosity
- Auto-clean or archive output files after posting
- Enhanced preview and error handling in `post_to_twitter.py`
- Timestamped logging and unified logger utility
- Improved `.env` validation before posting

### v0.4.3 — AWS Integration prework
- Pipeline lambda modules deployed
- IAMs usergroups and permissions established
- Enhanced preview and error handling in `post_to_twitter.py`
- Timestamped logging and unified logger utility
- Improved `.env` validation before posting

### v0.4.4-v0.4.6 — Lambda Deployment and Testing
- Implemented "chunking" in summarizer to scale process (but still running into Bedrock API timeouts w/ claude 3.5)
- Pipeline lambda modules adjusted to work from AWS environment and individually tested
- Introduced SecretsManager for TwitterAPI keys
- Event-driven, overrideable json parameters
- Manual Process: Scraper_Lambda -> scraped_output.json -> Orchestrator_Lambda -> summarized_output.json -> Poster_Lambda -> formats tweet, shows in console, posts to twitter if dry_run = false

### v0.5.0 — Fully assembled pipeline
- Pipeline_Lambda created as main controller for process
- Automated process:   Scraper_Lambda -> scraped_output.json -> Orchestrator_Lambda -> summarized_output.json -> Poster_Lambda -> formats tweet, shows in console, posts to twitter if dry_run = false

---

## 🚧 Current Release (in progress)

### v0.6.0 — Memory & Scheduled Automation (S3/EventBridge)

- Memory / Controller to track/store scraped articles in library
- Trigger Lambda process on interval (e.g. every 4-12 hours, or whenever new data is detected)
- Monitor logs in CloudWatch
- Run full automated pipeline on AWS--

## 🧭 Upcoming Milestones

### v0.7.0 — CI/CD with GitHub Actions + SAM
- Auto-deploy Lambda functions via GitHub push to `main`
- SAM build and deploy with environment staging

### v0.8.0 — Secrets Manager as Default
- Make Secrets Manager the default for all AWS Lambda modules
- Auto-pull and rotate credentials securely
- Final deprecation of local `.env` for prod

---

## 🏁 Finalization Milestone

### v1.0.0 — Production-Ready Auto Poster
- Stable, scalable full pipeline
- Secrets Manager + CI/CD + CloudWatch
- Modular CLI interface for dev preview or manual triggering
- Ready for open source release or private deployment

---
