# lambda/summarizer.py – AWS Bedrock + Claude 3.5 Sonnet

import json
import os
import time
import random
import boto3
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
aws_region = os.getenv("AWS_REGION", "us-east-1")
model_id = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-sonnet-20240229")

bedrock = boto3.client(
    service_name="bedrock-runtime",
    region_name=aws_region,
    aws_access_key_id=aws_access_key,
    aws_secret_access_key=aws_secret_key
)


def build_prompt_v1(article):
    return (
        f"Summarize the following AI research article in a fun and engaging way appropriate for social media using 3-4 sentences.\n"
        f"Title: {article['title']}\n"
        f"Authors: {', '.join(article['authors'])}\n"
        f"Abstract: {article['snippet']}"
    )

def build_prompt_v2(article):
    return (
        f"You are an expert technical writer. Provide a concise, informative summary of this research paper.\n"
        f"Focus on any novel methods, key findings, or real-world relevance.\n\n"
        f"Abstract: {article['snippet']}"
    )

def summarize_with_claude(prompt, variant_label="v1"):
    payload = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 300,
        "temperature": 0.7,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }
    response = bedrock.invoke_model(
        modelId=model_id,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(payload)
    )
    result = json.loads(response["body"].read())
    return result["content"][0]["text"].strip()

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
                print(f"[{datetime.utcnow().isoformat()}] Non-throttling error:", e)
                return "[Summary unavailable]"
    return "[Summary unavailable after max retry time]"

def lambda_handler(event=None, context=None):
    try:
        PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        fallback_path = os.path.join(PROJECT_ROOT, "test_output.json")
        save_path = os.path.join(PROJECT_ROOT, "summarized_output.json")

        if event and "articles" in event:
            articles = event["articles"]
        else:
            with open(fallback_path, "r", encoding="utf-8") as f:
                articles = json.load(f)

        summarized = []

        for article in articles:
            prompt_v1 = build_prompt_v1(article)
            prompt_v2 = build_prompt_v2(article)

            summary_v1 = retry_until_timeout(lambda: summarize_with_claude(prompt_v1, "v1"))
            summary_v2 = retry_until_timeout(lambda: summarize_with_claude(prompt_v2, "v2"))

            result = {
                **article,
                "v1_summary": summary_v1,
                "v2_summary": summary_v2
            }
            summarized.append(result)

            with open(save_path, "w", encoding="utf-8") as out:
                json.dump(summarized, out, indent=2, ensure_ascii=False)

        return {
            "statusCode": 200,
            "body": json.dumps(summarized, indent=2, ensure_ascii=False)
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }

if __name__ == "__main__":
    print(json.dumps(lambda_handler(), indent=2, ensure_ascii=False))
