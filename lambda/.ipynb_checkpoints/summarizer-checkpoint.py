# lambda/summarizer.py – AWS Bedrock + Claude 3.5 Sonnet

import json
import os
import boto3
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class SummarizerClient:
    def __init__(self, model_id=None):
        self.model_id = model_id or os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-sonnet-20240229")
        self.client = boto3.client(
            service_name="bedrock-runtime",
            region_name=os.getenv("AWS_REGION", "us-east-1"),
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
        )

    def summarize(self, article):
        prompt = self._build_prompt(article)

        try:
            response = self.client.invoke_model(
                modelId=self.model_id,
                contentType="application/json",
                accept="application/json",
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 300,
                    "temperature": 0.7,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ]
                })
            )

            result = json.loads(response["body"].read())
            return result["content"][0]["text"]

        except (BotoCoreError, ClientError, KeyError) as e:
            print(f"Error summarizing article: {e}")
            return "[Summary unavailable]"

    def _build_prompt(self, article):
        return (
            f"Please summarize the following AI research article in 2-3 sentences suitable for a professional tech audience. "
            f"Include key insights, findings, or novel contributions.\n\n"
            f"Title: {article['title']}\n"
            f"Authors: {', '.join(article['authors'])}\n"
            f"Abstract: {article['snippet']}\n"
        )

if __name__ == "__main__":
    # Load scraped results
    input_path = os.path.join(os.path.dirname(__file__), "../test_output.json")
    output_path = os.path.join(os.path.dirname(__file__), "../summarized_output.json")

    with open(input_path, "r", encoding="utf-8") as f:
        articles = json.load(f)

    summarizer = SummarizerClient()
    summarized_articles = []

    for article in articles:
        summary = summarizer.summarize(article)
        summarized_articles.append({
            **article,
            "summary": summary.strip()
        })

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(summarized_articles, f, indent=2, ensure_ascii=False)

    print(f"\nSummarized {len(summarized_articles)} articles. Output saved to summarized_output.json.")
