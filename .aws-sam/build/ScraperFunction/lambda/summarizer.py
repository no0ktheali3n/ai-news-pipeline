# lambda/summarizer.py – AWS Bedrock + Claude 3.5 Sonnet

# summarizer.py – Final version for production

import os
import json
import time
import random
import boto3
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# AWS setup
aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
aws_region = os.getenv("AWS_REGION", "us-east-1")
model_id = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20240620-v1:0")

bedrock = boto3.client(
    service_name="bedrock-runtime",
    region_name=aws_region,
    aws_access_key_id=aws_access_key,
    aws_secret_access_key=aws_secret_key
)

# File paths
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
INPUT_FILE = os.path.join(PROJECT_ROOT, "test_output.json")
OUTPUT_FILE = os.path.join(PROJECT_ROOT, "summarized_output.json")

# Prompt builders
def build_summary_prompt(article):
    return (
        f"Summarize the following AI research article in a fun and engaging way appropriate for social media using 3-4 sentences.\n"
        f"Title: {article['title']}\n"
        f"Authors: {', '.join(article['authors'])}\n"
        f"Abstract: {article['snippet']}"
    )

def build_hashtag_prompt(article):
    return (
        f"Suggest 3-5 short and relevant hashtags for this AI paper.\n"
        f"Title: {article['title']}\n"
        f"Abstract: {article['snippet']}"
    )

# Claude Bedrock API call
def summarize_with_claude(prompt):
    payload = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 300,
        "temperature": 0.7,
        "messages": [{"role": "user", "content": prompt}]
    }
    response = bedrock.invoke_model(
        modelId=model_id,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(payload)
    )
    result = json.loads(response["body"].read())
    return result["content"][0]["text"].strip(), len(prompt)

# Retry with backoff + token tracking
def retry_until_timeout(func, max_seconds=600, base_delay=3):
    start_time = time.time()
    attempt = 0
    while time.time() - start_time < max_seconds:
        try:
            return func()
        except Exception as e:
            if "ThrottlingException" in str(e):
                delay = min(base_delay * (2 ** attempt), 60) + random.uniform(1, 3)
                print(f"[{datetime.utcnow().isoformat()}] Throttled. Retrying in {delay:.2f}s...")
                time.sleep(delay)
                attempt += 1
            else:
                print(f"[{datetime.utcnow().isoformat()}] Error:", e)
                return "[Summary unavailable]", 0
    return "[Summary unavailable after max retry time]", 0

# Main summarizer logic
def summarize_articles():
    total_tokens = 0
    summarized = []

    try:
        with open(INPUT_FILE, "r", encoding="utf-8") as f:
            articles = json.load(f)
    except FileNotFoundError:
        print(f"[ERROR] Could not find {INPUT_FILE}")
        return []

    for article in articles:
        sum_prompt = build_summary_prompt(article)
        tag_prompt = build_hashtag_prompt(article)

        summary, tokens_s = retry_until_timeout(lambda: summarize_with_claude(sum_prompt))
        hashtags, tokens_h = retry_until_timeout(lambda: summarize_with_claude(tag_prompt))

        result = {
            **article,
            "summary": summary,
            "hashtags": hashtags
        }
        summarized.append(result)
        total_tokens += tokens_s + tokens_h

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(summarized, f, indent=2, ensure_ascii=False)

    print(f"[✔] Summarized {len(summarized)} articles.")
    print(f"[📊] Estimated total characters sent: {total_tokens}")
    return summarized
