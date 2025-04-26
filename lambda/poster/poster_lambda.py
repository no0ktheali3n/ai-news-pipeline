#poster lambda - calls utils.post_to_twitter to authenticate twitter client via tweepy, format and post content threads to twitter

import os
import sys
import json
import boto3

import traceback
from dotenv import load_dotenv

# Setup path and environment
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
load_dotenv()

from utils.logger import logger
from utils.post_to_twitter import run_posting_pipeline

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET = os.getenv("S3_OUTPUT_BUCKET")
SUMMARY_PREFIX = os.getenv("SUMMARY_OUTPUT_PREFIX", "output/summarizer/")

s3 = boto3.client("s3", region_name=AWS_REGION)

def get_latest_summary_key():
    response = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=SUMMARY_PREFIX)
    objects = response.get("Contents", [])
    if not objects:
        raise FileNotFoundError("No summarized output found in S3")

    json_files = [obj for obj in objects if obj["Key"].endswith(".json")]
    sorted_files = sorted(json_files, key=lambda x: x["LastModified"], reverse=True)
    return sorted_files[0]["Key"]

def handler(event, context):
    """
    Lambda entry point for posting Twitter threads.
    Downloads the latest summary JSON from S3 and calls the posting pipeline.
    """
    post_limit = event.get("limit", 1) # limits how many summaries to post starting from the start_index
    dry_run = event.get("dry_run", False) # True = no post to twitter
    start_index = event.get("start_index", 0) #chooses where to start posting from the summary file

    try:
        latest_key = get_latest_summary_key()
        local_path = "/tmp/summarized_output.json"

        logger.info(f"📥 Downloading summarized file from S3: {latest_key}")
        s3.download_file(S3_BUCKET, latest_key, local_path)

        results = run_posting_pipeline(
            limit=post_limit, 
            variant="summary", 
            dry_run=dry_run, 
            confirm_post=True,
            start_index=start_index
            )

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": f"Posted {len(results)} threads successfully.",
                "results": results
            })
        }

    except Exception as e:
        logger.exception("❌ Poster Lambda error")
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
