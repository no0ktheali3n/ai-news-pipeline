# utils/memcon.py — memory controller: filters scraped articles against the posted ledger.
#
# Dedup design (since 2026-07): the ONLY authoritative record is the posted
# ledger (posted_library.json), written by the poster after a confirmed tweet.
# Articles are no longer marked "seen" at scrape time — under that design, any
# downstream failure (summarizer/poster) permanently lost the article: the
# seen-library blocked re-scraping but nothing had been posted.

import os
import json
import boto3
from botocore.exceptions import ClientError
from utils.logger import get_logger

logger = get_logger("memcon")

# Environment variables
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
MEMORY_BUCKET = os.getenv("S3_OUTPUT_BUCKET")
MEMORY_PREFIX = os.getenv("MEMORY_OUTPUT_PREFIX", "")
POSTED_LEDGER_FILE = os.getenv("POSTED_LEDGER_FILE", "posted_library.json")
POSTED_LEDGER_KEY = f"{MEMORY_PREFIX}{POSTED_LEDGER_FILE}"

s3 = boto3.client("s3", region_name=AWS_REGION)


def load_posted_ledger():
    """Returns {url: metadata} of articles that have actually been posted."""
    try:
        response = s3.get_object(Bucket=MEMORY_BUCKET, Key=POSTED_LEDGER_KEY)
        return json.loads(response["Body"].read())
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            logger.warning(f"No posted ledger at {POSTED_LEDGER_KEY} — treating all articles as new.")
            return {}
        raise


def filter_new_articles(scraped_articles):
    """
    Returns only articles that have never been POSTED.

    Read-only: the poster records a URL in the ledger after its thread goes
    out, so an article that fails anywhere downstream stays eligible for the
    next run instead of being lost.
    """
    posted = load_posted_ledger()

    new_articles = []
    for article in scraped_articles:
        url = article["url"]
        if url in posted:
            logger.info(f"Article already posted: {url} - skipping.")
        else:
            new_articles.append(article)

    logger.info(
        f"{len(new_articles)} new article(s) out of {len(scraped_articles)} scraped "
        f"(posted ledger has {len(posted)} entries)."
    )
    return new_articles
