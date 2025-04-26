# lambda/pipeline_lambda.py – Unified Pipeline Controller (Scraper → Summarizer → Poster)

import os
import sys
import json
import boto3
import time
import traceback

# Setup environment paths
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.logger import get_logger

# Initialize logger
logger = get_logger("pipeline")

# Environment setup
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET = os.getenv("S3_OUTPUT_BUCKET")
SCRAPER_FUNCTION_NAME = os.getenv("SCRAPER_FUNCTION_NAME")
SUMMARIZER_FUNCTION_NAME = os.getenv("ORCHESTRATOR_FUNCTION_NAME")
POSTER_FUNCTION_NAME = os.getenv("POSTER_FUNCTION_NAME")

# Initialize Lambda client
lambda_client = boto3.client("lambda", region_name=AWS_REGION)

# Define expected parameters per function
FUNCTION_PAYLOADS = {
    "scraper": ["scrape_limit"],
    "orchestrator": ["chunk_size"],
    "poster": ["dry_run", "post_limit", "start_index"]
}

# Build payloads dynamically with only keys relevant to each function

def build_payload(function_key, event_data):
    keys = FUNCTION_PAYLOADS.get(function_key, [])
    payload = {k: event_data[k] for k in keys if k in event_data}
    return payload

# Lambda invocation utility

def invoke_lambda(function_name, payload=None, wait=True):
    logger.info(f"Invoking {function_name}...")
    response = lambda_client.invoke(
        FunctionName=function_name,
        InvocationType="RequestResponse" if wait else "Event",
        Payload=json.dumps(payload or {}).encode('utf-8')
    )

    if wait:
        result = json.loads(response['Payload'].read().decode('utf-8'))
        logger.info(f"✅ {function_name} completed")
        return result
    return None

# Main Lambda handler

def handler(event, context):
    """
    Master controller to orchestrate the AI Research Pipeline.
    Stages: Scrape articles → Summarize articles → Post summaries
    Accepts configurable limits for scraping, chunking, posting, and dry_run flag.
    """
    try:
        logger.info("Starting AI Research Pipeline Run...")

        # --- Scraper Stage ---
        scraper_payload = build_payload("scraper", event)
        logger.info(f"Scraping new data (payload: {scraper_payload})")
        invoke_lambda(SCRAPER_FUNCTION_NAME, scraper_payload)
        logger.info("Waiting for scraper output to stabilize...")
        time.sleep(5)

        # --- Summarizer Stage (Orchestrator) ---
        orchestrator_payload = build_payload("orchestrator", event)
        logger.info(f"Summarizing articles (payload: {orchestrator_payload})")
        orchestrator_result = invoke_lambda(SUMMARIZER_FUNCTION_NAME, orchestrator_payload)
        logger.info("Waiting for summarizer output to stabilize...")
        time.sleep(5)

        # --- Poster Stage ---
        poster_payload = build_payload("poster", event)
        logger.info(f"Formatting and posting summaries (payload: {poster_payload})")
        invoke_lambda(POSTER_FUNCTION_NAME, poster_payload)

        logger.info("Unified pipeline run completed successfully!")

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Pipeline completed successfully",
                "orchestrator_summary": orchestrator_result
            })
        }

    except Exception as e:
        logger.exception("❌ Pipeline failed")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": str(e),
                "trace": traceback.format_exc()
            })
        }

# Local execution (for testing)
if __name__ == "__main__":
    test_event = {
        "scrape_limit": 1,
        "chunk_size": 2,
        "dry_run": True,
        "start_index": 0,
        "post_limit": 1
    }
    handler(test_event, None)
