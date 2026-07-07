#poster lambda - calls utils.post_to_twitter to authenticate twitter client via tweepy, format and post content threads to twitter

import os
import sys
import json
import boto3

import traceback
from dotenv import load_dotenv
from utils.automations import notify_make_pipeline_status

# Setup path and environment
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
load_dotenv()

from utils.logger import get_logger
logger = get_logger("poster")
from utils.post_to_twitter import run_posting_pipeline

from datetime import datetime, timedelta, timezone

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET = os.getenv("S3_OUTPUT_BUCKET")
SUMMARY_INPUT = os.getenv("SUMMARY_OUTPUT_PREFIX", "ai-research-pipeline/output/summarizer/") #poster gets its input to format
MEMORY_PREFIX = os.getenv("MEMORY_OUTPUT_PREFIX", "ai-research-pipeline/output/memory/")
POSTED_LEDGER_FILE = os.getenv("POSTED_LEDGER_FILE", "posted_library.json")
POSTED_LEDGER_KEY = f"{MEMORY_PREFIX}{POSTED_LEDGER_FILE}"
MAX_SUMMARY_AGE_HOURS = float(os.getenv("MAX_SUMMARY_AGE_HOURS", "6"))

s3 = boto3.client("s3", region_name=AWS_REGION)

def get_latest_summary_key():
    """Newest summary .json under the prefix — with a freshness guard.

    Fallback path only (the pipeline normally passes summary_key). Refusing
    stale files is what stops the poster from re-tweeting a months-old summary
    when upstream stages silently stop producing output.
    """
    paginator = s3.get_paginator("list_objects_v2")
    json_files = []
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=SUMMARY_INPUT):
        json_files.extend(obj for obj in page.get("Contents", []) if obj["Key"].endswith(".json"))
    if not json_files:
        raise FileNotFoundError("No summarized output found in S3")

    latest = max(json_files, key=lambda x: x["LastModified"])
    age = datetime.now(timezone.utc) - latest["LastModified"]
    if age > timedelta(hours=MAX_SUMMARY_AGE_HOURS):
        raise RuntimeError(
            f"Latest summary {latest['Key']} is {age} old (limit {MAX_SUMMARY_AGE_HOURS}h) — "
            f"refusing to post stale content. Upstream summarizer is likely broken."
        )
    return latest["Key"]

def load_posted_ledger():
    try:
        body = s3.get_object(Bucket=S3_BUCKET, Key=POSTED_LEDGER_KEY)["Body"].read()
        return json.loads(body)
    except s3.exceptions.NoSuchKey:
        logger.warning(f"No posted ledger at {POSTED_LEDGER_KEY} — starting a new one.")
        return {}

def save_posted_ledger(ledger):
    s3.put_object(Bucket=S3_BUCKET, Key=POSTED_LEDGER_KEY,
                  Body=json.dumps(ledger, indent=2).encode("utf-8"))
    logger.info(f"Posted ledger updated: {len(ledger)} articles tracked.")

def handler(event, context):
    """
    Lambda entry point for posting Twitter threads.
    Downloads the latest summary JSON from S3 and calls the posting pipeline.
    """
    # the pipeline sends "post_limit"; keep "limit" for backwards compatibility
    post_limit = event.get("post_limit", event.get("limit", 1))
    dry_run = event.get("dry_run", False) # True = no post to twitter
    start_index = event.get("start_index", 0) #chooses where to start posting from the summary file
    confirm_post = event.get("confirm_post", False) #True = prompt for confirmation before posting for local testing//mostly deprecated since dry_run is now used for this purpose

    try:
        # Prefer the exact key from this pipeline run; fall back to freshness-guarded latest.
        latest_key = event.get("summary_key") or get_latest_summary_key()
        local_path = "/tmp/summarized_output.json"

        logger.info(f"📥 Downloading summarized file from S3: {latest_key}")
        #downloads the latest summary file from S3 to local tmp path
        s3.download_file(S3_BUCKET, latest_key, local_path)

        # Drop anything already posted — the poster-side dedup the scraper's
        # seen-library can't provide (that one marks articles seen at scrape time).
        with open(local_path, "r", encoding="utf-8") as f:
            articles = json.load(f)
        ledger = load_posted_ledger()
        fresh_articles = [a for a in articles if a.get("url") not in ledger]
        skipped = len(articles) - len(fresh_articles)
        if skipped:
            logger.info(f"⏭️ Skipping {skipped} already-posted article(s).")
        if not fresh_articles:
            msg = f"Nothing new to post: all {len(articles)} article(s) in {latest_key} were already posted."
            logger.info(msg)
            notify_make_pipeline_status(message=f"ℹ️ AI research pipeline: {msg}")
            return {"statusCode": 200, "body": json.dumps({"message": msg, "results": []})}
        with open(local_path, "w", encoding="utf-8") as f:
            json.dump(fresh_articles, f, ensure_ascii=False)

        # Persist each URL to the ledger the moment its thread posts — a crash
        # later in the run must not allow an already-tweeted article to repost.
        def record_posted(metadata):
            scores = metadata.get("scores") or {}
            ledger[metadata["url"]] = {
                "title": metadata.get("article_title"),
                "thread_url": metadata.get("thread_url"),
                "posted_at": datetime.now(timezone.utc).isoformat(),
                "builder_relevance": scores.get("builder_relevance"),
                "novelty": scores.get("novelty"),
                "hook_potential": scores.get("hook_potential"),
                "composite": metadata.get("composite"),
                "query_source": metadata.get("query_source"),
                "buzz": metadata.get("buzz"),
                "buzz_raw": metadata.get("buzz_raw"),
                "status": metadata.get("status", "posted"),
                "tweet_count": metadata.get("tweet_count"),
                "follower_count": metadata.get("follower_count"),
                "media": metadata.get("media"),
            }
            save_posted_ledger(ledger)

        results = run_posting_pipeline(
            limit=post_limit,
            variant="summary",
            dry_run=dry_run,
            confirm_post=confirm_post,
            start_index=start_index,
            on_posted=record_posted
            )
        
        logger.info(f"Raw posting results: {results}")

        if not results:
            logger.warning("⚠️ Posting results are empty.")
        else:
            for i, r in enumerate(results):
                logger.info(f"📄 Article {i+1} result: {json.dumps(r, indent=2)}")



        # takes data from the returned results of the posting pipeline and formats it for the automations notification
        posted_metadata = [
            {
                "title": r["article_title"],
                "source_url": r["url"],
                "thread": r["thread_url"]
            }
            for r in results
        ]

        logger.info(f"📦 Posting metadata to Make: {json.dumps(posted_metadata, indent=2)}")
        
        #notifies Make webhook to post to Slack
        notify_make_pipeline_status(articles=posted_metadata)

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": f"Posted {len(results)} threads successfully.",
                "results": results
            })
        }

    except Exception as e:
        logger.exception("❌ Poster Lambda error")
        notify_make_pipeline_status(message=f"⚠️ AI research poster failed: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": str(e),
                "trace": traceback.format_exc()
            })
        }

# Optional local test
if __name__ == "__main__":
    response = handler({}, None)
    print(json.dumps(response, indent=2))
