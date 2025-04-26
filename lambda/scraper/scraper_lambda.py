# lambda/scraper_lambda.py – AWS Lambda handler to scrape arXiv and upload results to S3

import os
import sys
import json
import boto3
from datetime import datetime, timezone
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.scraper import ScraperClient  # Scraper logic

load_dotenv()

# Constants
DEFAULT_URL = "https://arxiv.org/search/?query=artificial+intelligence&searchtype=all&abstracts=show&order=-announced_date_first&size=25&classification-computer_science=y"
S3_BUCKET = os.getenv("S3_OUTPUT_BUCKET")
S3_PREFIX = os.getenv("SCRAPER_OUTPUT_PREFIX", "scraper/")
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
    """
    url = event.get("url", DEFAULT_URL)
    prefix_override = event.get("prefix")
    prefix = prefix_override or S3_PREFIX
    scrape_limit = event.get("scrape_limit", 8)

    scraper = ScraperClient(url, scrape_limit)
    results = scraper.scrape()

    if not results:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Scraper returned no results."})
        }

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
            "message": "Scraped and uploaded successfully",
            "url": url,
            "count": len(results),
            "s3_key": s3_key,
            "bucket": S3_BUCKET
        })
    }

# Optional: test locally
if __name__ == "__main__":
    print(handler({}, {}))

