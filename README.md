# ai-news-poster-pipeline/README.md

# AI News Poster Pipeline

A serverless automation tool that scrapes AI-related news, summarizes it using large language models (LLMs), and automatically posts it to Twitter/X. Designed with modular AWS Lambda functions and a GitHub CI/CD pipeline.

This project is open source for educational and non-commercial use.  For commercial licensing, please contact me directly.

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

## Architecture

```
EventBridge (Scheduled Trigger)
       |
       v
AWS Lambda [Scraper] --> OpenAI API / Bedrock [Summarizer] --> AWS Lambda [Poster] --> Twitter API

[CI/CD Pipeline]:
GitHub --> GitHub Actions --> SAM Deploy --> CloudWatch Logs
```

## IAM Configuration
This project uses Amazon Bedrock and other AWS services that require explicit permissions.

### IAM Role or Policy Requirements:
Attach the following policy to either your Lambda execution role or your IAM user:

```json
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

### If Using AWS Lambda:
- Create an **IAM Role** with the above policy.
- Assign it as the execution role for each Lambda function (e.g. summarizer).

### If Running Locally:
- Create an **IAM User** with programmatic access.
- Attach the same policy.
- Configure with `aws configure` or `.env`.

You may further restrict `"Resource"` to the specific Claude model ARN from Bedrock for tighter security.

## Project Structure
```
ai-news-poster-pipeline/
├── lambda/
│   ├── scraper.py             # Collects articles via RSS/web
│   ├── summarizer.py          # Uses LLM to compress to tweet-length
│   └── poster.py              # Publishes to Twitter via API
├── utils/
│   ├── formatters.py          # Hashtagging, text cleaning, link shortening
│   └── user_agents.py         # Rotating user-agent pool
├── notebooks/
│   ├── summarization-lab.ipynb # Prompt tuning for summaries
│   └── poster-lab.ipynb        # Formatting tweet-ready posts
├── config/
│   └── settings.json          # Source feed URLs, post frequency, etc.
├── test_output.json           # Raw output from scraper
├── summarized_output.json     # Enriched summaries before posting
├── requirements.txt           # Python packages
├── LICENSE
└── sam-template.yaml          # AWS SAM deployment template
```

## Notebooks
This repo includes experimentation notebooks for prompt tuning and prototyping:

- `notebooks/summarization-lab.ipynb`: Use Claude via Bedrock to test summarization prompts.
- `notebooks/poster-lab.ipynb`: Format summaries as tweet-style posts with hashtagging.

## How to Use
1. Clone the repo
2. Create an `.env` file or use AWS Secrets Manager for:
   - OPENAI_API_KEY or AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY
   - TWITTER_BEARER_TOKEN
   - AWS_REGION
   - BEDROCK_MODEL_ID (optional override)
3. Install dependencies:
```bash
pip install -r requirements.txt
```
4. Run locally:
```bash
python lambda/scraper.py
python lambda/summarizer.py
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

---

## License
MIT

## Citation Policy and Attribution
This project scrapes and summarizes publicly available scientific content from platforms such as [arXiv.org](https://arxiv.org/). The original research belongs to the respective authors and institutions. We do not claim ownership of this work and include full citations or backlinks to the original articles.

Every generated summary includes a reference URL to the source article to ensure attribution.

## Ethics & Usage Disclaimer
This project is open source and provided for educational, research, and informational purposes.

- **Do not use this tool to plagiarize or misrepresent academic work.**
- **Do not present AI-generated summaries as original research.**
- We strongly encourage citing original authors and linking back to the source in all published outputs.

For inquiries about commercial usage, please contact the project owner directly.

---
Want to contribute or suggest improvements? Submit an issue or open a pull request!
