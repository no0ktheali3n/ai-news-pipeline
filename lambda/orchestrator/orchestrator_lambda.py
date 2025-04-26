# lambda/orchestrator_lambda.py
import os
import json
import time
import boto3

from utils.orchestrator import (
    orchestrate_chunks,
    reassemble_chunks_from_s3,
    S3_BUCKET,
    DEFAULT_SUMMARIZER_OUTPUT_PREFIX
)

# Initialize S3 client globally
s3 = boto3.client("s3")

def handler(event, context):
    try:
        chunk_size = event.get("chunk_size", 2)
                
        # Trigger summarizer and get run ID + expected chunks
        run_id, expected_chunk_count = orchestrate_chunks(chunk_size)
        FINAL_SUMMARIZED_FILE = os.getenv("FINAL_SUMMARIZED_FILE", f"final_summarized_{run_id}.json")

        if not run_id or expected_chunk_count is None:
            raise ValueError("Failed to initialize chunking: invalid run_id or chunk count.")

        print(f"🧠 Using run_id: {run_id}")
        print(f"📡 Polling prefix: {DEFAULT_SUMMARIZER_OUTPUT_PREFIX}summarized_{run_id}_")

        print("⏳ Waiting for all summarizer chunks to be uploaded to S3...")
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


            print(f"📦 S3 returned {len(chunk_keys)} objects. Matching JSON chunks: {len(chunk_keys)}")
            print(f"🔑 Keys: {[obj['Key'] for obj in chunk_keys]}")

            if len(chunk_keys) >= expected_chunk_count:
                print(f"✅ Found all {len(chunk_keys)} chunks. Proceeding to reassembly.")
                break

            if waited + INTERVAL > MAX_WAIT:
                raise TimeoutError("Timeout waiting for all chunks to be uploaded.")

            print(f"⌛ {len(chunk_keys)} chunks found so far. Waiting...")
            time.sleep(INTERVAL)
            waited += INTERVAL

        # Edge case: only one chunk, copy it directly as final output
        if len(chunk_keys) == 1:
            source_key = chunk_keys[0]
            final_key = f"{DEFAULT_SUMMARIZER_OUTPUT_PREFIX}{FINAL_SUMMARIZED_FILE}"
            print(f"📄 Only 1 chunk found. Copying {source_key} to {final_key}")
            s3.copy_object(
                Bucket=S3_BUCKET,
                CopySource={'Bucket': S3_BUCKET, 'Key': source_key},
                Key=final_key
            )
        else:
            print(f"🔧 Reassembling {len(chunk_keys)} chunks...")
            reassemble_chunks_from_s3(run_id)

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Summarization pipeline complete and reassembled.",
                "chunks": chunk_keys
            })
        }

    except Exception as e:
        print(f"❌ Exception in orchestrator: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
