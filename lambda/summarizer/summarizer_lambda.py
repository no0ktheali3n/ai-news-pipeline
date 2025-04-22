# lambda/summarizer_lambda.py – Summarizes a chunk of articles passed via event and saves results to S3

import os
import sys
import json
from datetime import datetime, timezone
import boto3
from dotenv import load_dotenv

# Add project root for local testing
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.summarizer import summarize_articles

# Load environment variables
load_dotenv()

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
S3_OUTPUT_BUCKET = os.getenv("S3_OUTPUT_BUCKET")
SUMMARIZER_OUTPUT_PREFIX = os.getenv("SUMMARIZER_OUTPUT_PREFIX", "output/summarizer/")

s3 = boto3.client("s3", region_name=AWS_REGION)

def handler(event, context):
    if not S3_OUTPUT_BUCKET:
        return {"statusCode": 500, "body": json.dumps({"error": "Missing S3 bucket env var."})}

    try:
        # Extract chunked articles from the event
        articles = event.get("articles")
        chunk_id = event.get("chunk_id", "chunk")
        run_id = event.get("run_id", "unknown_run")

        print(f"[ℹ️] Received run_id: {run_id}, chunk_id: {chunk_id}, article count: {len(articles)}")


        if not articles:
            return {"statusCode": 400, "body": json.dumps({"error": "No articles provided in event payload."})}

        tmp_input = "/tmp/scraper_input.json"
        tmp_output = "/tmp/summarized_output.json"

        # Save articles chunk to temp file
        with open(tmp_input, "w", encoding="utf-8") as f:
            json.dump(articles, f)

        # Set globals for summarizer module
        import utils.summarizer as summarizer_module
        summarizer_module.INPUT_FILE = tmp_input
        summarizer_module.OUTPUT_FILE = tmp_output

        summarized = summarize_articles()

        output_key = f"{SUMMARIZER_OUTPUT_PREFIX}summarized_{run_id}_{chunk_id}.json"
        
        # Upload chunk result to S3
        s3.upload_file(tmp_output, S3_OUTPUT_BUCKET, output_key)
        print(f"[💾] Uploaded chunk to: {output_key}")


        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Chunk summarized and saved to S3",
                "summary_key": output_key,
                "count": len(summarized)
            })
        }

    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
