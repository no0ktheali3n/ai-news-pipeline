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

## 💡 Roadmap
- Migrate from `.env` to Secrets Manager for cloud usage
- Add Twitter/X Tweepy automation as optional Lambda trigger
- CI/CD automation via GitHub Actions + SAM deployment
- Add HuggingFace summarization fallback or multi-model support

---

_Last updated: 2025-04-11_
