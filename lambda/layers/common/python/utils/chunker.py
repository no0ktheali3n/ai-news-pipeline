# utils/chunker.py
# Purpose: Callable chunker module for triggering summarizer Lambdas in parallel

import os
import re
import json
import boto3
import botocore.config
import random
import time
from uuid import uuid4
from typing import List
from datetime import datetime, timezone, timedelta

# Constants (can be overridden)
DEFAULT_INPUT_FILE = "test_output.json"
DEFAULT_CHUNK_SIZE = 2
DEFAULT_LAMBDA_NAME = "ai-research-summarizer"  # runs summarizer_lambda.py for each chuunk of articles
DEFAULT_OUTPUT_FILE = "/tmp/summarized_output.json"
DEFAULT_SUMMARIZER_OUTPUT_PREFIX = "ai-research-pipeline/output/summarizer/"

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET = os.getenv("S3_OUTPUT_BUCKET")
s3 = boto3.client("s3", region_name=AWS_REGION)

LAMBDA_CONFIG = botocore.config.Config(
    read_timeout=600,  # Wait up to 10 minutes for response
    connect_timeout=10,
    retries={"total_max_attempts": 1},  # a retried invoke = duplicate Bedrock spend
)

def split_into_chunks(data: List[dict], chunk_size: int) -> List[List[dict]]:
    return [data[i:i + chunk_size] for i in range(0, len(data), chunk_size)]

def invoke_lambda_for_chunk(lambda_client, chunk: List[dict], chunk_id: str, lambda_name: str):
    response = lambda_client.invoke(
        FunctionName=lambda_name,
        InvocationType='Event',  # async
        Payload=json.dumps({
            "chunk_id": chunk_id,
            "articles": chunk
        }).encode('utf-8')
    )
    print(f"[Lambda Invoke] Chunk {chunk_id} invoked with {len(chunk)} articles.")
    return response

MAX_SCRAPE_AGE_HOURS = float(os.getenv("MAX_SCRAPE_AGE_HOURS", "6"))

def get_latest_scraper_key(prefix: str = "ai-research-pipeline/output/scraper/") -> str:
    """Fallback only — the pipeline normally passes the exact scraper_key.
    Paginated (a single list_objects_v2 page caps at 1000 keys, and page one
    of a big prefix is the OLDEST keys) and freshness-guarded so a broken
    scraper can't silently feed a stale scrape downstream."""
    paginator = s3.get_paginator("list_objects_v2")
    json_files = []
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
        json_files.extend(obj for obj in page.get("Contents", []) if obj["Key"].endswith(".json"))

    if not json_files:
        raise FileNotFoundError(f"No scraper output .json files found under prefix: {prefix}")

    latest = max(json_files, key=lambda x: x["LastModified"])
    age = datetime.now(timezone.utc) - latest["LastModified"]
    if age > timedelta(hours=MAX_SCRAPE_AGE_HOURS):
        raise RuntimeError(
            f"Latest scrape {latest['Key']} is {age} old (limit {MAX_SCRAPE_AGE_HOURS}h) — "
            f"refusing to summarize stale input. Upstream scraper is likely broken."
        )
    print(f"[✅] Latest scraper output file selected: {latest['Key']}")
    return latest["Key"]

def orchestrate_chunks(chunk_size=DEFAULT_CHUNK_SIZE, lambda_name=DEFAULT_LAMBDA_NAME, scraper_key=None):
    run_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")  # Unique run ID

    # Prefer the exact file this pipeline run scraped
    scraper_key = scraper_key or get_latest_scraper_key()
    tmp_input_path = "/tmp/scraper_input.json"
    s3.download_file(S3_BUCKET, scraper_key, tmp_input_path)

    with open(tmp_input_path, "r", encoding="utf-8") as f:
        articles = json.load(f)

    chunks = split_into_chunks(articles, chunk_size)
    lambda_client = boto3.client("lambda", config=LAMBDA_CONFIG)

    # Synchronous, sequential invocation. The previous async 'Event' fan-out +
    # S3 polling meant a failing chunk was unobservable (its 500 went nowhere),
    # AWS's async retries duplicated Bedrock spend, and the orchestrator was
    # billed for 15s-interval polling. At scheduled scale (chunk_size=1) there
    # is no parallelism to lose.
    for idx, chunk in enumerate(chunks):
        chunk_id = f"chunk-{idx+1}-{uuid4()}"
        response = lambda_client.invoke(
            FunctionName=lambda_name,
            InvocationType='RequestResponse',
            Payload=json.dumps({
                "chunk_id": chunk_id,
                "articles": chunk,
                "run_id": run_id
            }).encode('utf-8')
        )
        payload = json.loads(response["Payload"].read().decode("utf-8"))
        if response.get("FunctionError") or not (
            isinstance(payload, dict) and payload.get("statusCode") == 200
        ):
            raise RuntimeError(
                f"Summarizer chunk {idx + 1}/{len(chunks)} ({chunk_id}) failed: {str(payload)[:400]}"
            )
        print(f"[✅] Chunk {idx + 1}/{len(chunks)} summarized.")

    return run_id, len(chunks)  # 🔁 return for reassembly

def extract_chunk_index(key):
    match = re.search(r'chunk-(\d+)', key)
    return int(match.group(1)) if match else float('inf')


def reassemble_chunks_from_s3(run_id, prefix=DEFAULT_SUMMARIZER_OUTPUT_PREFIX, output_file=DEFAULT_OUTPUT_FILE):
    if not S3_BUCKET:
        raise EnvironmentError("Missing required S3_OUTPUT_BUCKET environment variable.")

    print(f"[🔍] Scanning S3 with prefix: {prefix}summarized_{run_id}_")

    response = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=f"{prefix}summarized_{run_id}_")

    contents = response.get("Contents", [])
    print(f"[📂] Found {len(contents)} files for run_id '{run_id}'")

    if not contents:
        raise FileNotFoundError(f"No summarized output found for run_id: {run_id}")

    all_summaries = []
    for obj in sorted(contents, key=lambda x: extract_chunk_index(x["Key"])):
        key = obj["Key"]
        if key.endswith(".json"):
            s3_obj = s3.get_object(Bucket=S3_BUCKET, Key=key)
            chunk_data = json.loads(s3_obj["Body"].read().decode("utf-8"))
            all_summaries.extend(chunk_data)
            print(f"[📥] Loaded {len(chunk_data)} entries from {key}")

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_summaries, f, indent=2, ensure_ascii=False)

    final_key = f"{DEFAULT_SUMMARIZER_OUTPUT_PREFIX}final_summarized_{run_id}.json"
    s3.upload_file(output_file, S3_BUCKET, final_key)
    print(f"[📤] Uploaded reassembled file to: {final_key}")


    print(f"✅ Reassembled {len(all_summaries)} entries into {output_file}")
