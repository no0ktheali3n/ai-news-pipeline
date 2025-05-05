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
                
        # Trigger summarizer and get run ID + expected chunks
        run_id, expected_chunk_count = orchestrate_chunks(chunk_size) #gets run id and creates N summarizers based on chunk size
        FINAL_SUMMARIZED_FILE = os.getenv("FINAL_SUMMARIZED_FILE", f"final_summarized_{run_id}.json")

        if not run_id or expected_chunk_count is None:
            raise ValueError("Failed to initialize chunking: invalid run_id or chunk count.")

        logger.info(f"🧠 Using run_id: {run_id}")
        logger.info(f"📡 Polling prefix: {DEFAULT_SUMMARIZER_OUTPUT_PREFIX}summarized_{run_id}_")

        logger.info("⏳ Waiting for all summarizer chunks to be uploaded to S3...")
        MAX_WAIT = 600
        INTERVAL = 15
        waited = 0

        prefix = f"{DEFAULT_SUMMARIZER_OUTPUT_PREFIX}summarized_{run_id}_"

        paginator = s3.get_paginator("list_objects_v2")
        chunk_keys = []

        for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
            for obj in page.get("Contents", []):
                if obj["Key"].endswith(".json"):
                    chunk_keys.append(obj["Key"])


            logger.info(f"📦 S3 returned {len(chunk_keys)} objects. Matching JSON chunks: {len(chunk_keys)}")
            logger.info(f"🔑 Keys: {[obj['Key'] for obj in chunk_keys]}")

            if len(chunk_keys) >= expected_chunk_count:
                logger.info(f"✅ Found all {len(chunk_keys)} chunks. Proceeding to reassembly.")
                break

            if waited + INTERVAL > MAX_WAIT:
                raise TimeoutError("Timeout waiting for all chunks to be uploaded.")

            logger.info(f"⌛ {len(chunk_keys)} chunks found so far. Waiting...")
            time.sleep(INTERVAL)
            waited += INTERVAL

        final_key = f"{DEFAULT_SUMMARIZER_OUTPUT_PREFIX}{FINAL_SUMMARIZED_FILE}"

        # Edge case: only one chunk, copy it directly as final output
        if len(chunk_keys) == 1:
            source_key = chunk_keys[0]
            logger.info(f"📄 Only 1 chunk found. Copying {source_key} to {final_key}")
            s3.copy_object(
                Bucket=S3_BUCKET,
                CopySource={'Bucket': S3_BUCKET, 'Key': source_key},
                Key=final_key
            )
        else:
            logger.info(f"🔧 Reassembling {len(chunk_keys)} chunks...")
            reassemble_chunks_from_s3(run_id) #reassembles chunks of current run_id into json 

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
