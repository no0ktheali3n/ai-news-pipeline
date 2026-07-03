# lambda/summarizer_main_lambda.py
import os
import json
import time
import boto3
import traceback

from utils.chunker import (
    orchestrate_chunks,
    reassemble_chunks_from_s3,
    S3_BUCKET,
    DEFAULT_SUMMARIZER_OUTPUT_PREFIX
)
from utils.logger import get_logger
logger = get_logger("summarizer_main")

# Initialize S3 client globally
s3 = boto3.client("s3")

def handler(event, context):
    try:
        chunk_size = event.get("chunk_size", 2)
        scraper_key = event.get("scraper_key")  # exact scrape file from this pipeline run

        # Run the summarizer chunks (synchronous — every chunk file is in S3,
        # verified successful, by the time this returns; failures raise).
        run_id, expected_chunk_count = orchestrate_chunks(chunk_size, scraper_key=scraper_key)
        logger.info(f"🧠 Run {run_id}: {expected_chunk_count} chunk(s) summarized.")

        prefix = f"{DEFAULT_SUMMARIZER_OUTPUT_PREFIX}summarized_{run_id}_"
        chunk_keys = []
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
            chunk_keys.extend(o["Key"] for o in page.get("Contents", []) if o["Key"].endswith(".json"))
        if len(chunk_keys) < expected_chunk_count:
            raise RuntimeError(f"Expected {expected_chunk_count} chunk files, found {len(chunk_keys)}.")

        final_key = f"{DEFAULT_SUMMARIZER_OUTPUT_PREFIX}final_summarized_{run_id}.json"
        logger.info(f"🔧 Reassembling {len(chunk_keys)} chunk(s) into {final_key}")
        reassemble_chunks_from_s3(run_id)

        #final output content check
        article_count = 0
        article_keys = []
        has_summaries = False

        try:
            logger.info(f"📊 Checking content of final output at: {final_key}")
            
            response = s3.get_object(Bucket=S3_BUCKET, Key=final_key)
            content_bytes = response['Body'].read()
            logger.info(f"📂 Retrieved {len(content_bytes)} bytes from final output file")
            
            content = json.loads(content_bytes)
            article_count = len(content) if isinstance(content, list) else 0
            
            logger.info(f"📈 Final output contains {article_count} articles")
            
            # Log more detail about content structure
            if article_count > 0:
                sample_article = content[0]
                article_keys = list(sample_article.keys() if isinstance(sample_article, dict) else [])
                logger.info(f"🔍 First article keys: {article_keys}")
                has_summaries = 'summary' in sample_article if isinstance(sample_article, dict) else False
                logger.info(f"📝 First article has summary: {has_summaries}")
                
                # Log a sample of the first article's content
                if isinstance(sample_article, dict):
                    for key in article_keys[:3]:  # Log first 3 keys only
                        value = sample_article.get(key)
                        logger.info(f"   - {key}: {str(value)[:50]}...")  # Truncate long values
            else:
                logger.info("⚠️ No articles found in final output - empty result set")
                
        except Exception as e:
            logger.error(f"❌ Error checking final output content: {str(e)}")
            logger.error(traceback.format_exc())

        # Extract article titles for reporting
        article_titles = []
        if article_count > 0 and isinstance(content, list):
            article_titles = [a.get("title", "Untitled") for a in content]
            logger.info(f"Article titles extracted: {article_titles}")

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Summarization pipeline complete and reassembled.",
                "final_key": final_key,
                "chunks": [os.path.basename(k) for k in chunk_keys],
                "chunk_size": chunk_size,
                "article_titles": article_titles,
                "article_count": article_count,
                "article_keys": [str(key) for key in article_keys],
                "has_summaries": has_summaries,
                "hashtags": [a.get("hashtags", []) for a in content] if isinstance(content, list) else []
            }, default=str)
        }
    
    except Exception as e:
        logger.warning(f"❌ Exception in summarizer: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
