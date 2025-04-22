# lambda/orchestrator_lambda.py
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
        # Step 1: Trigger summarization and get run context
        run_id, expected_chunk_count = orchestrate_chunks()

        # 🧠 DEBUG LOGGING
        print(f"[🆔] Using run_id: {run_id}")
        print(f"[🔍] Polling prefix: {DEFAULT_SUMMARIZER_OUTPUT_PREFIX}summarized_{run_id}_")

        # Step 2: Poll S3 until all summarization chunks are available
        print(f"[⏳] Waiting for all summarizer chunks to be uploaded to S3...")

        MAX_WAIT = 600  # seconds
        INTERVAL = 15   # seconds between checks
        waited = 0

        while waited < MAX_WAIT:
            response = s3.list_objects_v2(
                Bucket=S3_BUCKET,
                Prefix=f"{DEFAULT_SUMMARIZER_OUTPUT_PREFIX}summarized_{run_id}_"
            )

            contents = response.get("Contents", [])
            chunk_keys = [
                obj["Key"] for obj in contents if obj["Key"].endswith(".json")
            ]

            # 🧠 More visibility on what S3 actually returned
            print(f"[📂] S3 returned {len(contents)} objects. Matching JSON chunks: {len(chunk_keys)}")
            print(f"[📁] Keys: {[obj['Key'] for obj in contents]}")

            if len(chunk_keys) >= expected_chunk_count:
                print(f"[✅] Found all {len(chunk_keys)} chunks for run_id {run_id}. Proceeding to reassembly.")
                break

            print(f"[⏳] {len(chunk_keys)} chunks found so far. Waiting...")
            time.sleep(INTERVAL)
            waited += INTERVAL

        # Step 3: Reassemble all chunks into final output
        reassemble_chunks_from_s3(run_id)

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Summarization pipeline complete and reassembled."
            })
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
