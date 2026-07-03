# lambda/pipeline_lambda.py – Unified Pipeline Controller (Scraper → Summarizer → Poster)

import os
import sys
import json
import boto3
import botocore.config
import time
import traceback

# Setup environment paths
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.logger import get_logger
from utils.automations import notify_make_pipeline_status

# Initialize logger
logger = get_logger("pipeline")

# Environment setup
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET = os.getenv("S3_OUTPUT_BUCKET")
SCRAPER_FUNCTION_NAME = os.getenv("SCRAPER_FUNCTION_NAME")
SUMMARIZER_FUNCTION_NAME = os.getenv("SUMMARIZER_MAIN_FUNCTION_NAME")
POSTER_FUNCTION_NAME = os.getenv("POSTER_FUNCTION_NAME")

# Initialize Lambda client.
# Default boto3 read timeout is 60s; summarizer-main legitimately runs for
# minutes now that it actually waits for chunks. No retries: stage invokes
# are not idempotent (a retried summarizer spawns duplicate Bedrock runs).
LAMBDA_CONFIG = botocore.config.Config(
    read_timeout=780,
    connect_timeout=10,
    retries={"total_max_attempts": 1},
)
lambda_client = boto3.client("lambda", region_name=AWS_REGION, config=LAMBDA_CONFIG)

# Define expected parameters per function
FUNCTION_PAYLOADS = {
    "scraper": ["scrape_limit", "url", "skip_memory", "start_scrape"],
    "chunker": ["chunk_size"],
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
        scraper_result = invoke_lambda(SCRAPER_FUNCTION_NAME, scraper_payload)
        logger.info("Waiting for scraper output to stabilize...")

        # Parse the scraper result: exact S3 key for the summarizer + new-article gate.
        skip_memory = event.get("skip_memory", False)
        scraper_key = None
        if scraper_result and isinstance(scraper_result, dict) and 'body' in scraper_result:
            try:
                scraper_body = json.loads(scraper_result['body'])
            except (json.JSONDecodeError, TypeError) as e:
                logger.error(f"Failed to parse scraper result body: {e}")
                notify_make_pipeline_status(message=f"⚠️ AI research pipeline aborted: unparsable scraper result ({e})")
                return {
                    "statusCode": 500,
                    "body": json.dumps({"error": f"Failed to parse scraper result body: {e}"})
                }

            scraper_key = scraper_body.get('s3_key')

            if not skip_memory:
                new_count = scraper_body.get('new_count', 0)
                if new_count == 0:
                    logger.info("No new articles found after memory check, aborting pipeline.")
                    return {
                        "statusCode": 200,
                        "body": json.dumps({
                            "message": "No new articles found, pipeline aborted",
                            "scraped_count": scraper_body.get('scraped_count', 0),
                            "new_count": 0
                        })
                    }
                logger.info(f"Found {new_count} new articles to process")
            else:
                logger.info("Article checking bypassed with skip_memory, continuing pipeline...")

        # --- Summarizer Stage (Chunker) ---
        # Hand the summarizer the exact file this run scraped (fallback:
        # freshness-guarded newest-file lookup inside the chunker).
        chunker_payload = build_payload("chunker", event)
        if scraper_key:
            chunker_payload["scraper_key"] = scraper_key
        logger.info(f"Summarizing articles (payload: {chunker_payload})")
        chunker_result = invoke_lambda(SUMMARIZER_FUNCTION_NAME, chunker_payload)
        logger.info("Waiting for summarizer output to stabilize...")

        # The poster only runs on a verified-fresh summary. Anything else aborts
        # loudly — silently posting the most recent S3 object is how the same
        # article got tweeted for months after the summarizer broke.
        def abort_pipeline(reason):
            logger.error(f"❌ Aborting pipeline before poster stage: {reason}")
            notify_make_pipeline_status(message=f"⚠️ AI research pipeline aborted: {reason}")
            return {
                "statusCode": 500,
                "body": json.dumps({"error": reason})
            }

        if not (chunker_result and isinstance(chunker_result, dict) and 'body' in chunker_result):
            return abort_pipeline(f"Summarizer returned no parsable result: {chunker_result}")

        if chunker_result.get('statusCode') != 200:
            return abort_pipeline(f"Summarizer failed: {chunker_result.get('body')}")

        try:
            parsed_body = json.loads(chunker_result['body'])
            logger.info(f"Successfully parsed summarizer result body with keys: {list(parsed_body.keys())}")
            chunker_result = parsed_body
        except (json.JSONDecodeError, TypeError) as e:
            return abort_pipeline(f"Failed to parse summarizer result body: {e}")

        if not chunker_result.get('article_count') or not chunker_result.get('has_summaries'):
            return abort_pipeline(
                f"Summarizer produced no usable summaries "
                f"(article_count={chunker_result.get('article_count')}, "
                f"has_summaries={chunker_result.get('has_summaries')})"
            )

        # --- Poster Stage ---
        poster_payload = build_payload("poster", event)
        if chunker_result.get('final_key'):
            poster_payload["summary_key"] = chunker_result["final_key"]
        logger.info(f"Formatting and posting summaries (payload: {poster_payload})")
        invoke_lambda(POSTER_FUNCTION_NAME, poster_payload)

        logger.info("Unified pipeline run completed successfully!")

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Pipeline completed successfully",
                "chunk_size": chunker_result.get('chunk_size', 0) if isinstance(chunker_result, dict) else 0,
                "article_count": chunker_result.get('article_count', 0) if isinstance(chunker_result, dict) else 0,
                "article_titles": chunker_result.get('article_titles', []) if isinstance(chunker_result, dict) else [],
                "hashtags": chunker_result.get('hashtags', []) if isinstance(chunker_result, dict) else [],
                "has_summaries": chunker_result.get('has_summaries', False) if isinstance(chunker_result, dict) else False
            }, default=str)
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
        "post_limit": 1,
        "skip_memory": True,
    }
    handler(test_event, None)
