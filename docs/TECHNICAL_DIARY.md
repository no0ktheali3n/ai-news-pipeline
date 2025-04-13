# Technical Diary

This file documents major technical decisions, fixes, lessons learned, and recurring patterns.

---

## 🌱 Phase 1 – Scraper Foundation
- Created initial `scraper-alpha` using BeautifulSoup
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

---

_Last updated: 2025-04-11_
