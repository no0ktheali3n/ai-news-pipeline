# lambda/summarizer.py – AWS Bedrock + Claude 3.5 Sonnet

import os
import re
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
    region_name=aws_region
)

# File paths
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
INPUT_FILE = os.path.join(PROJECT_ROOT, "test_output.json")
OUTPUT_FILE = os.path.join(PROJECT_ROOT, "summarized_output.json")

# Prompt builders
def build_summary_prompt(article):
    return (
        f"You are a social media manager summarizing AI research for a tech-savvy audience.\n\n"
        f"**Task**: Summarize the following research paper in 4-6 engaging sentences suitable for a tweet or thread intended to stimulate curious minds\n\n"
        f"**Title**: {article['title']}\n"
        f"**Authors**: {', '.join(article['authors'])}\n"
        f"**Abstract**: {article['snippet']}\n\n"
        f"Keep it concise, readable, and appealing to AI/ML enthusiasts. Avoid redundancy and excessive emojis.\n"
    )


def build_hashtag_prompt(article):
    return (
        f"Provide a list of 3-5 relevant and concise hashtags for the following AI paper. "
        f"Return only a JSON array of strings, no explanation.\n\n"
        f"Title: {article['title']}\n"
        f"Abstract: {article['snippet']}"
    )

#OMEGAPROMPT hashtag prompt engineering
def build_summary_and_hashtag_prompt(article):
    return (
        f"You are a social media assistant tasked with summarizing AI research and generating hashtags.\n\n"
        f"**Task**:\n"
        f"1. Summarize the research in 2–4 engaging sentences suitable for a tweet.\n"
        f"2. Generate 3–5 relevant and concise hashtags.\n\n"
        f"**Only return a valid JSON object. Do not include any explanation, markdown formatting, or commentary.**\n\n"
        f"Here is the required JSON format:\n"
        f"```\n"
        f"{{\n"
        f'  "summary": "your summary here",\n'
        f'  "hashtags": ["#tag1", "#tag2", ...]\n'
        f"}}\n"
        f"```\n\n"
        f"**Paper Information**:\n"
        f"Title: {article['title']}\n"
        f"Authors: {', '.join(article['authors'])}\n"
        f"Abstract: {article['snippet']}"
    )

def parse_hashtags(response_raw):
    if isinstance(response_raw, list):
        return [tag.strip() for tag in response_raw if isinstance(tag, str)]

    if isinstance(response_raw, str):
        try:
            parsed = json.loads(response_raw)
            if isinstance(parsed, list):
                return [tag.strip() for tag in parsed if isinstance(tag, str)]
        except Exception:
            pass

        # Fallback: extract using regex
        tags = re.findall(r"\"#?\w+\"", response_raw)
        if tags:
            return [tag.strip('"#') for tag in tags]

    raise ValueError("Failed to extract hashtags from response")



# Claude Bedrock API call
# Claude Bedrock API call with combined summary + hashtag prompt

def summarize_with_claude(prompt):
    payload = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 400,
        "temperature": 0.7,
        "messages": [{"role": "user", "content": prompt}]
    }

    try:
        response = bedrock.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(payload)
        )
        result = json.loads(response["body"].read())

        content = result.get("content")
        if isinstance(content, list):
            try:
                combined = " ".join(part["text"] for part in content if part["type"] == "text")
                print(f"[Claude Output Preview] {combined[:120]}...")
                return json.loads(combined), len(prompt)
            except Exception as e:
                print(f"[ERROR] Failed to extract structured output: {e}")
                return {"summary": "[Summary unavailable]", "hashtags": ["[Summary unavailable]"]}, 0

        elif isinstance(content, str):
            print(f"[Claude Output Preview] {content[:120]}...")
            try:
                return json.loads(content), len(prompt)
            except Exception as e:
                print(f"[ERROR] JSON parse error: {e}")
                return {"summary": "[Summary unavailable]", "hashtags": ["[Summary unavailable]"]}, 0

        else:
            print(f"[ERROR] Claude content unrecognized: {content}")
            return {"summary": "[Summary unavailable]", "hashtags": ["[Summary unavailable]"]}, 0

    except Exception as e:
        print(f"[Claude API ERROR] {str(e)}")
        return {"summary": "[Summary unavailable]", "hashtags": ["[Summary unavailable]"]}, 0
    

# Retry with backoff + token tracking
def retry_until_timeout(func, max_seconds=900, base_delay=10):
    start_time = time.time()
    attempt = 0
    while time.time() - start_time < max_seconds:
        try:
            return func()
        except Exception as e:
            if "ThrottlingException" in str(e):
                # Use exponential backoff + jitter
                delay = min(base_delay * (2 ** attempt), 60) + random.uniform(2, 4)
                print(f"[{datetime.utcnow().isoformat()}] Throttled. Sleeping {delay:.2f}s (attempt {attempt + 1})...")
                time.sleep(delay)
                attempt += 1
            else:
                print(f"[{datetime.utcnow().isoformat()}] Non-throttle error: {e}")
                return "[Summary unavailable]", 0
    return "[Summary unavailable after max retry time]", 0


# Main summarizer logic
def summarize_articles(limit=None, max_runtime=900):
    start_time = time.time()
    summarized = []
    total_tokens = 0

    try:
        with open(INPUT_FILE, "r", encoding="utf-8") as f:
            articles = json.load(f)
    except FileNotFoundError:
        print(f"[ERROR] Could not find {INPUT_FILE}")
        return []

    if limit is not None:
        articles = articles[:limit]

    idx = 0
    while idx < len(articles):
        elapsed = time.time() - start_time
        if max_runtime - elapsed < 45:
            print(f"[⏳] Stopping early at article {idx + 1} — time budget exceeded.")
            break

        article = articles[idx]
        print(f"[🔍] Attempting article {idx + 1}/{len(articles)}")

        def attempt_summary():
            return summarize_with_claude(build_summary_and_hashtag_prompt(article))

        result_obj, tokens_used = retry_until_timeout(attempt_summary, max_seconds=max_runtime - int(time.time() - start_time))

        summary = result_obj.get("summary", "")
        hashtags = result_obj.get("hashtags", [])

        # Only append if summary is valid
        if "[Summary unavailable" not in summary and summary.strip():
            summarized.append({
                **article,
                "summary": summary,
                "hashtags": hashtags
            })
            total_tokens += tokens_used
            idx += 1
            time.sleep(random.uniform(2.0, 4.0))  # throttle cooldown
        else:
            print(f"[⚠️] Failed to summarize article {idx + 1}. Retrying...")

    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(summarized, f, indent=2, ensure_ascii=False)
        print(f"[✅] Finalized {len(summarized)} summaries")
        print(f"[📊] Estimated total characters sent: {total_tokens}")
    except Exception as e:
        print(f"[ERROR] Failed to save output: {e}")

    return summarized
