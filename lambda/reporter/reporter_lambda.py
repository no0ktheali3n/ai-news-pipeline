"""reporter_lambda.py — weekly HTML report generator + digest publisher."""
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Layer path (mirrors other lambdas) ──────────────────────────────────────
_LAYER = Path(__file__).resolve().parent.parent / "layers" / "common" / "python"
if str(_LAYER) not in sys.path:
    sys.path.insert(0, str(_LAYER))

import boto3  # noqa: E402 — after path setup
from utils.analytics import (  # noqa: E402
    buzz_outcome,
    follower_series,
    lane_stats,
    load_entries,
    media_stats,
    post_deltas,
    run_stats,
)
from utils.report_html import render_report  # noqa: E402

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ── Env vars (read at module level — mirrors poster_lambda.py) ───────────────
S3_BUCKET = os.environ.get("S3_OUTPUT_BUCKET", "")
MEMORY_OUTPUT_PREFIX = os.environ.get("MEMORY_OUTPUT_PREFIX", "out/memory/")
POSTED_LEDGER_FILE = os.environ.get("POSTED_LEDGER_FILE", "posted_library.json")
SCORED_OUTPUT_PREFIX = os.environ.get("SCORED_OUTPUT_PREFIX", "out/scored/")
REPORTS_OUTPUT_PREFIX = os.environ.get("REPORTS_OUTPUT_PREFIX", "out/reports/")
REPORT_TOPIC_ARN = os.environ.get("REPORT_TOPIC_ARN", "")

POSTED_LEDGER_KEY = f"{MEMORY_OUTPUT_PREFIX}{POSTED_LEDGER_FILE}"

s3 = boto3.client("s3")
sns = boto3.client("sns")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _load_ledger() -> dict:
    """Return the posted ledger dict; returns {} on missing key."""
    try:
        body = s3.get_object(Bucket=S3_BUCKET, Key=POSTED_LEDGER_KEY)["Body"].read()
        return json.loads(body)
    except s3.exceptions.NoSuchKey:
        logger.warning("Ledger key %s not found — generating empty report.", POSTED_LEDGER_KEY)
        return {}
    except json.JSONDecodeError as e:
        logger.warning("Posted ledger unreadable (%s); reporting on empty ledger.", e)
        return {}


def _count_sidecars() -> int:
    """Paginate SCORED_OUTPUT_PREFIX and count keys matching scored_candidates_*.json."""
    paginator = s3.get_paginator("list_objects_v2")
    pattern = re.compile(r"scored_candidates_.*\.json$")
    count = 0
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=SCORED_OUTPUT_PREFIX):
        for obj in page.get("Contents", []):
            if pattern.search(obj["Key"]):
                count += 1
    return count


# ── Handler ──────────────────────────────────────────────────────────────────

def handler(event, context):
    # 1. Load ledger (missing key → {}, proceed)
    ledger = _load_ledger()

    # 2. Count sidecar runs
    n_sidecars = _count_sidecars()

    # 3. Build aggregate
    entries = load_entries(ledger)
    series = follower_series(entries)
    deltas = post_deltas(entries)
    lanes = lane_stats(entries)
    buzz = buzz_outcome(entries)
    runs = run_stats(n_sidecars, entries)
    media = media_stats(entries)
    milestone_current = series[-1][1] if series else None
    agg = {
        "series": series,
        "deltas": deltas,
        "lanes": lanes,
        "buzz": buzz,
        "runs": runs,
        "media": media,
        "milestone": {"target": 500, "current": milestone_current},
    }

    # 4. Render HTML and store
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    html = render_report(agg, today)
    report_key = f"{REPORTS_OUTPUT_PREFIX}report_{today}.html"
    s3.put_object(Bucket=S3_BUCKET, Key=report_key, Body=html.encode("utf-8"), ContentType="text/html")
    logger.info("Report written to s3://%s/%s", S3_BUCKET, report_key)

    # 5. Generate presigned URL (degrade gracefully)
    try:
        presigned_url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET, "Key": report_key},
            ExpiresIn=604800,
        )
        report_link = presigned_url
    except Exception as exc:
        logger.warning("Could not generate presigned URL: %s", exc)
        report_link = f"s3://{S3_BUCKET}/{report_key}"

    # 6. Build digest and publish to SNS
    n_posts = runs["posts"]
    n_partials = runs["partials"]
    followers_str = str(milestone_current) if milestone_current is not None else "not yet captured"

    # Best post: highest non-None delta
    best_title = None
    best_delta = None
    for d in deltas:
        if d.get("delta") is not None:
            if best_delta is None or d["delta"] > best_delta:
                best_delta = d["delta"]
                best_title = d["title"]

    lines = [
        f"Total posts: {n_posts} ({n_partials} partial).",
        f"Current followers: {followers_str}.",
    ]
    if best_title and best_delta is not None:
        lines.append(f"Best post: \"{best_title}\" ({best_delta:+d} followers).")
    lines.append(f"Milestone: {followers_str} / 500.")
    lines.append(
        f"Report link (may expire within hours): {report_link}\n"
        f"Durable location: s3://{S3_BUCKET}/{report_key}"
    )

    digest = "\n".join(lines)

    sns.publish(
        TopicArn=REPORT_TOPIC_ARN,
        Subject="[report] ai-research-pipeline weekly",
        Message=digest,
    )
    logger.info("Digest published to %s", REPORT_TOPIC_ARN)

    # 7. Return
    return {
        "statusCode": 200,
        "body": json.dumps({"report_key": report_key, "posts": n_posts, "runs": n_sidecars}),
    }
