# ai-news-poster-pipeline/README.md

# AI News Poster Pipeline

A serverless automation tool that scrapes AI-related news, summarizes it using large language models (LLMs), and automatically posts it to Twitter/X. Designed with modular AWS Lambda functions and a GitHub CI/CD pipeline.

## Tech Stack
- **AWS Lambda** – Serverless compute for scraper, summarizer, and poster
- **Amazon EventBridge** – Scheduled job triggering the pipeline
- **OpenAI API / AWS Bedrock** – LLM summarization
- **Twitter API** – Content posting via Tweepy
- **GitHub Actions** – CI/CD deployment pipeline
- **AWS SAM** – Infrastructure as Code (IaC) for packaging/deploying Lambda
- **CloudWatch** – Logging and monitoring
- **Pandas** – Tabular data formatting for downstream automation
- **Rotating User Agents** – Basic stealth and rate-limit avoidance for scraping
- **Randomized Request Delays** – Optional human-like browsing simulation

## Architecture

```
EventBridge (Scheduled Trigger)
       |
       v
AWS Lambda [Scraper] --> OpenAI API / Bedrock [Summarizer] --> AWS Lambda [Poster] --> Twitter API

[CI/CD Pipeline]:
GitHub --> GitHub Actions --> SAM Deploy --> CloudWatch Logs
```

## Project Structure
```
ai-news-poster-pipeline/
├── README.md
├── .github/
│   └── workflows/
│       └── deploy.yml         # GitHub Actions workflow
├── lambda/
│   ├── scraper.py             # Collects articles via RSS/web
│   ├── summarizer.py          # Uses LLM to compress to tweet-length
│   └── poster.py              # Publishes to Twitter via API
├── utils/
│   ├── formatters.py          # Hashtagging, text cleaning, link shortening
│   ├── request_helpers.py     # Randomized request timing, retry logic
│   └── user_agents.py         # Rotating user-agent pool
├── config/
│   └── settings.json          # Source feed URLs, post frequency, etc.
├── requirements.txt           # Python packages
└── sam-template.yaml          # AWS SAM deployment template
```

## How to Use
1. Clone the repo
2. Create an `.env` file or use AWS Secrets Manager for:
   - OPENAI_API_KEY
   - TWITTER_BEARER_TOKEN
   - AWS credentials (if deploying via CLI)
3. Install dependencies:
```bash
pip install -r requirements.txt
```
4. Run locally:
```bash
python lambda/scraper.py
```
5. Deploy to AWS:
```bash
sam build && sam deploy --guided
```

## GitHub Actions (CI/CD)
A sample GitHub Actions workflow (`.github/workflows/deploy.yml`) is included to:
- Lint Python code
- Build and deploy Lambda functions on push to `main`
- Notify of deployment success/failure

## License
MIT

---
Want to contribute or suggest improvements? Submit an issue or open a pull request!

---