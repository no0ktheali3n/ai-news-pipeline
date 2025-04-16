# AI News Poster Pipeline

A serverless automation tool that scrapes AI-related news, summarizes it using large language models (LLMs), and automatically posts it to Twitter/X. Designed with modular AWS Lambda functions, local notebooks, and a GitHub CI/CD pipeline.

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
ai-news-poster-pipeline/
├── lambda/
│   ├── scraper.py               # ArXiv article scraper (user-agent rotation, delay)
│   ├── summarizer.py            # LLM summarizer (Claude via Bedrock + hashtagging)
│   └── poster.py                # Formats and prepares summaries for posting
├── utils/
│   ├── user_agents.py           # Random user-agent pool
│   ├── request_helpers.py       # Simulates human behavior with delays
│   └── formatters.py            # Tweet formatter + hashtag filtering
├── notebooks/
│   ├── summarization-lab.ipynb  # Summarizer tuning, throttling handling, token logging
│   └── poster-lab.ipynb         # Tweet formatting previewer with length validator
├── docs/
│   ├── README.md                # Overview for contributors
│   ├── CHANGELOG.md             # All project changes & version tags
│   ├── SECURITY.md              # Incident reports, key protection, secret rotation
│   ├── requirements.txt         # All Python dependencies
│   └── TECHNICAL_DIARY.md       # Developer log, major decisions & rationale
├── .env.example                 # Safe template for AWS + model config
├── .gitignore                  # Prevents secrets and junk files from being tracked
├── summarized_output.json      # Output from Claude summarizer (v1/v2 + hashtags)
├── test_output.json            # Output from initial scraper run
└── sam-template.yaml           # AWS SAM deployment template
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
