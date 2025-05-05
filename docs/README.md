# AI News Poster Pipeline

A serverless automation tool that scrapes AI-related news, summarizes it using large language models (LLMs), and automatically posts it to Twitter/X. Designed with modular AWS Lambda functions, local notebooks, and will eventually integrate scheduled events (v0.6.0) and GitHub CI/CD pipeline (0.7.0+).

This project is open source for educational and non-commercial use.  
For commercial licensing, please contact me directly.

---

## Tech Stack

- **AWS Lambda** – Serverless compute for scraper, summarizer, and poster
- **Amazon Bedrock** – LLM summarization (Claude 3.5 Sonnet)
- **Pandas** – Tabular data transformation for summarizer output
- **Jupyter Notebooks** – Local testing + LLM prompt tuning
- **Tweepy** – Social media automation (future)
- **GitHub Actions** – CI/CD deployment (planned)
- **AWS SAM** – Infrastructure as Code for packaging/deploying Lambda
- **CloudWatch** – Logging and monitoring
- **Rotating User Agents** – Basic stealth and rate-limit avoidance for scraping

---

## Architecture

```
EventBridge (Scheduled Trigger)
       |
       v
AWS Lambda [Scraper] --> Bedrock Claude [Summarizer] --> AWS Lambda [Poster] --> Twitter API

[CI/CD Pipeline]:
GitHub --> GitHub Actions --> SAM Deploy --> CloudWatch Logs
```

---

## IAM Configuration

This project uses Amazon Bedrock and other AWS services that require explicit permissions.

### IAM Policy Example

```
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:ListFoundationModels"
      ],
      "Resource": "*"
    }
  ]
}
```

### Usage
- **For AWS Lambda**: Attach policy to your function’s execution role.
- **For local testing**: Create an IAM User with programmatic access and configure using `.env`.

---

## Project Structure

```
(requirements loaded per each specific function to avoid dependency bloat and lambda size limitations - 262mb)
ai-news-poster-pipeline/
├── lambda/
│   ├── pipeline/
│   │   ├── pipeline_lambda.py         # Lambda entrypoint – runs full scrape, summary, post process
│   ├── scraper/
│   │   ├── scraper_lambda.py          # Lambda entrypoint – pulls articles from ArXiv
│   │   ├── requirements.txt           # Local deps if needed (e.g., bs4, pandas)
│   ├── summarizer/
│   │   ├── summarizer_lambda.py       # summarizes via Claude
|   |   ├── summarizer_main_lambda.py  # Lambda entrypoint - chunks data and summarizes via summarizer_lambda
│   │   ├── requirements.txt           # summarizer requirements
│   ├── poster/
│   │   ├── poster_lambda.py           # Lambda entrypoint – posts tweet threads
│   │   ├── requirements.txt           # Only tweepy + formatters
│
│   └── layers/
│       └── common/
│           └── python/
│               └── utils/
│                   ├── __init__.py               # Required for Python to treat as a package
                    ├── chunker.py                # chunks scraped articles for summary according to chunk_size
                    ├── logger.py                 # Standardized logger for all Lambda functions
                    ├── memcon.py                 # memory controller for scraper and future poster functionality
                    ├── post_to_twitter.py        # Main orchestrator for tweet threading
                    ├── request_helpers.py        # Delays, header modifiers, request pacing
                    ├── scraper.py                # ArXiv-specific scrape logic
                    ├── summarizer.py             # Claude summarization + hashtag prompt logic
                    ├── test_tweet.py             # Standalone testing for tweet formatting
                    ├── tweepy_client.py          # Twitter API client with auth
                    ├── twitter_threading.py      # Splits summary into threaded tweets
                    └── user_agents.py            # Randomized browser headers
│
├── utils/                           # [Legacy] local utils or notebooks support
│
├── notebooks/
│   ├── summarization-lab.ipynb      # Claude tuning, rate limit handling, retries
│   ├── poster-lab.ipynb             # Thread preview tool with validator
│
├── docs/
│   ├── README.md                    # Full pipeline overview, goals, and usage
│   ├── CHANGELOG.md                 # Incremental feature tracking (e.g. v0.4.3 → v0.5.0)
│   ├── TECHNICAL_DIARY.md          # Live journal of issues, fixes, decisions
│   └── SECURITY.md                 # Secret mgmt + IAM handling practices
│
├── iam/
│   ├── admin-policy.json            # Custom admin IAM policy for full access
│   └── user-policy.json             # Constrained IAM policy for Lambda runners
│
├── test_output.json                # Cached scraper test run (manual / local test)
├── summarized_output.json          # Local summarizer output (Claude v1 + hashtags)
├── poster_event.json               # Sample event to test Twitter poster logic
│
├── .env.example                    # Safe reference for AWS + Claude vars
├── .gitignore                      # Prevents .env, .aws-sam, outputs from leaking
├── requirements.txt                # Dev-wide package list (env-agnostic)
├── sam-template.yaml               # SAM template w/ layer ref and env injection
├── samconfig.toml                  # SAM CLI config (region, stack, param overrides)
└── venv/                           # Python virtualenv (ignored by git)
```

---

## Notebooks

| Notebook | Purpose |
|----------|---------|
| `summarization-lab.ipynb` | Claude (via Bedrock) summarization previewer with token usage and retry logic |
| `poster-lab.ipynb` | Auto-formats tweet-ready summaries with hashtags, character limit enforcement |

---

## How to Use

### 1. Clone the repo

```
git clone https://github.com/no0ktheali3n/scraper-alpha.git
cd scraper-alpha
```

### 2. Set up your environment

```
cp .env.example .env
# Fill in AWS keys, model ID, region, etc.
```

### 3. Install dependencies

```
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r docs\requirements.txt
```

### 4. Run locally

```
python lambda/scraper.py
jupyter notebook notebooks/summarization-lab.ipynb
```

### 5. (Optional) Deploy to AWS Lambda

```
sam build && sam deploy --guided
```

---

## GitHub Actions (CI/CD)

A sample workflow is under development to:
- Lint and test code
- Package and deploy functions using SAM
- Notify on success/failure

---

## Licensing & Attribution

### License
**MIT License**

### Citation Policy
This project summarizes publicly available research, primarily from [arXiv.org](https://arxiv.org/).  
We do not claim ownership. All posts contain backlink attribution to the original article.

### Ethics Disclaimer
- 🔍 Cite original authors when sharing AI summaries  
- 🚫 Do not present auto-generated outputs as original research  
- ✅ Use for learning, journalism, outreach, and educational content

---

## Contributor Note

Check the `/docs/` folder for:
- ✅ Full `CHANGELOG.md` with version history
- ✅ `SECURITY.md` with key management and Git history scrub
- ✅ `TECHNICAL_DIARY.md` — a log of decisions, ideas, and debugging sessions

---

**Want to contribute or fork this?**  
Submit an issue or open a pull request — improvements are welcome!
