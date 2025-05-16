# utils/memcon.py memory controller for pipeline scraper duplicates and potentially poster in the future.
# Modified memcon.py

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
MEMORY_FILENAME = os.getenv("MEMORY_OUTPUT_FILE", "article_library.json")
MEMORY_KEY = f"{MEMORY_PREFIX}{MEMORY_FILENAME}"

s3 = boto3.client("s3", region_name=AWS_REGION)

def download_seen_articles():
    """
    Retrieves the article library from S3.
    Returns a dictionary with URLs as keys and article metadata as values.
    """
    try:
        response = s3.get_object(Bucket=MEMORY_BUCKET, Key=MEMORY_KEY)
        body = response['Body'].read()
        return json.loads(body)
    except ClientError as e:
        if e.response['Error']['Code'] == "NoSuchKey":
            logger.warning(f"No article library found at {MEMORY_KEY} - creating new library.")
            return {}  # Return empty dict for first run
        else:
            raise

def upload_seen_articles(seen_articles):
    """
    Uploads the updated article library to S3.
    """
    body = json.dumps(seen_articles, indent=2)
    
    # Debug logging
    logger.info(f"Attempting to upload to bucket: {MEMORY_BUCKET}")
    logger.info(f"Using key path: {MEMORY_KEY}")
    
    s3.put_object(Bucket=MEMORY_BUCKET, Key=MEMORY_KEY, Body=body.encode('utf-8'))
    logger.info(f"Updated memory with {len(seen_articles)} tracked articles at {MEMORY_KEY}.")
    
def filter_new_articles(scraped_articles):
    """
    Filters out articles that have already been seen.
    Updates the article library with new articles.
    Returns only new articles for processing.
    """
    # Get existing article library
    seen_articles = download_seen_articles()
    
    # Filter for new articles
    new_articles = []
    for article in scraped_articles:
        url = article["url"]
        if url not in seen_articles:
            new_articles.append(article)
        else:
            logger.info(f"Article already seen: {url} - skipping.")
    
    # Update library if we found new articles
    if new_articles:
        logger.info(f"Found {len(new_articles)} new articles out of {len(scraped_articles)} total. Adding to memory...")
        
        # Add new articles to library
        for article in new_articles:
            seen_articles[article["url"]] = article
        
        # Save updated library
        upload_seen_articles(seen_articles)
    else:
        logger.info(f"No new articles found. Memory currently contains {len(seen_articles)} articles.")
    
    return new_articles
