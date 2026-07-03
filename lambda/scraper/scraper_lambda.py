# lambda/scraper_lambda.py – AWS Lambda handler to scrape arXiv and upload results to S3
# Modified section of scraper_lambda.py

import os
import sys
import json
import boto3
from datetime import datetime, timezone
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.scraper import ScraperClient  # Scraper logic
from utils.memcon import filter_new_articles  # Memory controller
from utils.logger import get_logger
from utils.automations import notify_make_pipeline_status  # Automation notifications

load_dotenv()
logger = get_logger("scraper_lambda")

# Constants
DEFAULT_URL = "https://arxiv.org/search/?query=artificial+intelligence&searchtype=all&abstracts=show&order=-announced_date_first&size=25&classification-computer_science=y"
S3_BUCKET = os.getenv("S3_OUTPUT_BUCKET")
S3_PREFIX = os.getenv("SCRAPER_OUTPUT_PREFIX", "ai-research-pipeline/output/scraper/")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

s3 = boto3.client("s3", region_name=AWS_REGION)

def upload_to_s3(data, filename):
    try:
        key = f"{S3_PREFIX}{filename}"
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=json.dumps(data, indent=2, ensure_ascii=False),
            ContentType="application/json"
        )
        return key
    except Exception as e:
        raise RuntimeError(f"S3 upload failed: {e}")

def handler(event, context):
    """
    Lambda entry point to scrape articles from arXiv.
    Optional event keys:
    - "url": override the default ArXiv search
    - "prefix": override the S3 output prefix
    - "scrape_limit": limit the number of articles to scrape
    - "skip_memory": set to true to bypass memory check (for testing)
    """
    url = event.get("url", DEFAULT_URL)
    prefix_override = event.get("prefix")
    prefix = prefix_override or S3_PREFIX
    scrape_limit = event.get("scrape_limit", 1)
    skip_memory = event.get("skip_memory", False)
    start_scrape = event.get("start_scrape", 0)
    # How many unposted articles to pass downstream. Scraping wider than this
    # (scrape_limit > max_new_articles) lets a run walk down the newest-first
    # list to the next article the account hasn't posted yet, instead of
    # no-opping whenever the single newest one is already in the ledger.
    max_new_articles = event.get("max_new_articles", 1)


    # Scrape articles
    scraper = ScraperClient(url, scrape_limit, start_scrape)
    all_results = scraper.scrape()

    if not all_results:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Scraper returned no results."})
        }
    
    # Apply memory filtering unless explicitly skipped
    if skip_memory:
        logger.info("Memory check bypassed by request.")
        results = all_results
    else:
        # Filter against already-posted articles (newest-first order preserved)
        results = filter_new_articles(all_results)
        if max_new_articles and len(results) > max_new_articles:
            logger.info(f"Keeping {max_new_articles} of {len(results)} unposted article(s) for this run.")
            results = results[:max_new_articles]

        # terminates if no new articles found
        if not results:
            notify_make_pipeline_status(message="🚫 No articles scraped — pipeline aborted.")
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "message": "No new articles found after memory filtering",
                    "scraped_count": len(all_results),
                    "new_count": 0
                })
            }

    # If new article(s) found, upload filtered results to S3
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"scraped_articles_{timestamp}.json"

    try:
        s3_key = upload_to_s3(results, filename)
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Scraped, filtered and uploaded successfully",
            "url": url,
            "scraped_count": len(all_results),
            "new_count": len(results),
            "s3_key": s3_key,
            "bucket": S3_BUCKET
        })
    }
# Optional: test locally
if __name__ == "__main__":
    print(handler({}, {}))

