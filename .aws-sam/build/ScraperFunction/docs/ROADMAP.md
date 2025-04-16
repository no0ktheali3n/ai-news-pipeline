# 🗺️ Poster Pipeline – Development Roadmap

This document outlines the structured development phases leading to a full production release of the Automated Poster Pipeline. Each version increment reflects a meaningful system milestone based on modular maturity, automation depth, and operational readiness.

---

## 🔁 Completed Versions

| Version  | Highlights                                                                 |
|----------|----------------------------------------------------------------------------|
| `v0.1.0` | Basic scraper built using Python and BeautifulSoup                        |
| `v0.2.0` | Scraper refactored and enhanced for reusability & applied use in scraping ArXiv for AI articles |
| `v0.2.1` | Bug fixes; Initial testing of summarizer and poster in Jupyter begins     |
| `v0.3.0` | Claude integration via AWS Bedrock with summarizer prompt tuning          |
| `v0.4.0` | Hashtag generation, tweet formatter preview logic, editorial UI in Jupyter |
| `v0.4.1` | Functional Tweepy integration with full-thread support + confirmation UX  |

---

## 🔮 Upcoming Milestones

| Version  | Goals                                                                                     |
|----------|--------------------------------------------------------------------------------------------|
| `v0.4.2` | Polish pass: hashtag minimizer, tweet prioritization, dry-run flag, better error reporting |
| `v0.5.0` | Merge summarizer + poster logic into a unified Lambda function (single event pipeline)    |
| `v0.5.1` | Add CLI entry point, local mock runners, argument selectors for summaries/feeds           |
| `v0.6.0` | Package for AWS Lambda deployment with SAM + env-aware output logging                      |
| `v0.6.5` | CloudWatch logging and custom logger integration                                           |
| `v0.7.0` | GitHub Actions integration for CI/CD testing and deploy workflow                           |
| `v0.8.0` | **Migrate to AWS Secrets Manager for all credentials (Bedrock, Twitter, etc.)**           |
| `v0.9.0` | Dynamic feed scheduling via EventBridge and modular scraper configuration                 |
| `v1.0.0` | Full production deployment: CI/CD + secrets + runtime monitoring + modular runtime updates |

---

## 🔐 Best Practices Decision: Secrets Manager Timing

**Current Plan:**
- Deploy to AWS Lambda (v0.6.0) with `.env`-based secret injection
- Migrate to **AWS Secrets Manager** in `v0.8.0` after validating CI/CD infrastructure

### ✅ Why Not Immediately Before Lambda?
- Secrets Manager integration introduces IAM policy design, retrieval logic, and potentially encryption/decryption policies.
- Jumping into that *before* verifying the Lambda package works as expected could obscure where errors are coming from (Secrets vs Logic).

### 🔐 Justification for `v0.8.0` Timing:
| Criteria                | Explanation                                                                 |
|------------------------|-----------------------------------------------------------------------------|
| 🧪 Separation of Concerns | Decouples functional bugs from permission/config issues                      |
| 🔄 CI/CD Alignment       | Once deployment pipeline exists, secure secret loading can be validated      |
| ⚙️ Policy Flexibility     | Gives time to write least-privilege IAM roles with confidence                |
| 🧼 Rollback Safety        | Easier to roll back `.env` than reconfigure Secrets/IAM mid-deployment       |

We want to **ensure logic correctness before security plumbing**.

> "Secure a system that works before you secure a system that doesn’t." – Modern DevSecOps Wisdom

---

## ✅ Criteria for v1.0.0 Production Tag

- [ ] All environment variables sourced from Secrets Manager or GitHub Actions secrets
- [ ] Auto-deploy from GitHub with full logging to CloudWatch
- [ ] At least one scheduled Lambda job managed via EventBridge
- [ ] Unified summarization + poster flow in < 2 seconds end-to-end (excluding LLM response)
- [ ] Tests: tweet preview, feed dry run, token usage monitoring

---

## 🛠️ Bonus Considerations (Possible Future Releases)

| Idea                        | Use Case                                                              |
|----------------------------|-----------------------------------------------------------------------|
| v1.1.0: Article ranking     | Only post top-N based on scoring (attention, novelty, tags)           |
| v1.2.0: Markdown exporter   | Export summaries to GitHub wiki / Notion / HTML newsletter            |
| v1.3.0: Web dashboard       | Visualize summaries and tweet statuses (React + API Gateway)          |
| v2.0.0: Feed Integrator     | Integrate HN, Reddit, Twitter Trends with a multimodal summarizer loop|

---

> This roadmap is living. It evolves with every breakthrough, bottleneck, and inspiration.

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

---

## 🚧 Current Release (in progress)

### v0.4.2 — Polish and UX Improvements
- [ ] CLI flags for dry run, variant choice, verbosity
- [ ] Auto-clean or archive output files after posting
- [ ] Enhanced preview and error handling in `post_to_twitter.py`
- [ ] Timestamped logging and unified logger utility
- [ ] Improved `.env` validation before posting

---

## 🧭 Upcoming Milestones

### v0.4.3 — Optional AWS Secrets Manager Integration
- Replace local `.env` credentials with AWS Secrets Manager (opt-in)
- Refactor Lambda handlers to check both env and secrets

### v0.5.0 — Lambda-Compatible Refactor
- Restructure code into deployable Lambda modules
- Finalize lambda handlers for scraper, summarizer, and poster
- Run end-to-end manually in AWS Console

### v0.6.0 — Scheduled Automation (EventBridge)
- Trigger Lambda on interval (e.g. every 4 hours)
- Monitor logs in CloudWatch
- Run full pipeline on AWS

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
