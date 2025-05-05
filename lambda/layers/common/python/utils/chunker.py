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
from datetime import datetime, timezone

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
    connect_timeout=10
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

def get_latest_scraper_key(prefix: str = "ai-research-pipeline/output/scraper/") -> str:
    response = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=prefix)

    contents = response.get("Contents", [])
    print(f"[📂] Found {len(contents)} objects under prefix '{prefix}'")

    if not contents:
        raise FileNotFoundError(f"No scraper output files found under prefix: {prefix}")

    # Filter only valid .json files
    json_files = [obj for obj in contents if obj["Key"].endswith(".json")]

    if not json_files:
        print(f"[⚠️] Found files, but none ended in .json. Keys: {[obj['Key'] for obj in contents]}")
        raise FileNotFoundError("No .json files found in scraper output.")

    # Sort to get the most recent .json
    sorted_objs = sorted(json_files, key=lambda x: x["LastModified"], reverse=True)
    latest_key = sorted_objs[0]["Key"]
    print(f"[✅] Latest scraper output file selected: {latest_key}")
    return latest_key

def orchestrate_chunks(chunk_size=DEFAULT_CHUNK_SIZE, lambda_name=DEFAULT_LAMBDA_NAME):
    run_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")  # Unique run ID

    # Download scraper input
    scraper_key = get_latest_scraper_key()
    tmp_input_path = "/tmp/scraper_input.json"
    s3.download_file(S3_BUCKET, scraper_key, tmp_input_path)

    with open(tmp_input_path, "r", encoding="utf-8") as f:
        articles = json.load(f)

    chunks = split_into_chunks(articles, chunk_size)
    lambda_client = boto3.client("lambda", config=LAMBDA_CONFIG)

    for idx, chunk in enumerate(chunks):
        chunk_id = f"chunk-{idx+1}-{uuid4()}"
        lambda_client.invoke(
            FunctionName=lambda_name,
            InvocationType='Event',
            Payload=json.dumps({
                "chunk_id": chunk_id,
                "articles": chunk,
                "run_id": run_id
            }).encode('utf-8')
        )
        time.sleep(3 + random.uniform(0.5, 2.5))  # throttle safety

    print(f"✅ Triggered {len(chunks)} Lambda invocations.")
    return run_id, len(chunks)  # 🔁 return for reassembly

    print(f"✅ Triggered {len(chunks)} Lambda invocations.")

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
