# lambda/scraper_lambda.py – AWS Lambda handler to scrape arXiv and upload results to S3
# Modified section of scraper_lambda.py

import os
import random
import sys
import json
import boto3
import time
from datetime import datetime, timezone
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.scraper import ScraperClient  # Scraper logic
from utils.memcon import filter_new_articles  # Memory controller
from utils.logger import get_logger
from utils.automations import notify_make_pipeline_status  # Automation notifications
from utils.scoring import arxiv_id, score_candidates, ScoringError
import utils.buzz as buzz_mod

load_dotenv()
logger = get_logger("scraper_lambda")

# Constants
ARXIV_SEARCH = ("https://arxiv.org/search/?searchtype=all&abstracts=show"
                "&order=-announced_date_first&size=25&classification-computer_science=y&query=")

# Fixed, documented lane order (spec §1). Query strings are tunable — but must
# stay broad enough to NEVER legitimately match zero papers: _fetch_lane treats
# an empty result as a transient fetch failure and retries on that assumption.
LANES = [
    ("ai-security", ARXIV_SEARCH + "%22prompt+injection%22+OR+%22jailbreak%22+OR+%22LLM+security%22+OR+%22agent+safety%22+OR+%22AI+control%22"),
    ("agents", ARXIV_SEARCH + "%22LLM+agent%22+OR+%22multi-agent%22+OR+%22tool+use%22+OR+%22agentic%22"),
    ("llm-systems", ARXIV_SEARCH + "%22LLM+serving%22+OR+%22retrieval+augmented%22+OR+%22LLM+evaluation%22+OR+%22inference+optimization%22"),
]
LANE_FETCH_DELAY_S = 3.0
# Backoff before lane retry attempts 2 and 3 (+0-3s jitter). 2026-07-09: arXiv
# throttled all lanes (read timeouts + a 429) and one failed fetch per lane
# meant a silently skipped daily post; these queries never legitimately return
# zero results, so an empty scrape is treated as transient and retried.
LANE_RETRY_DELAYS_S = (15, 30)  # first retry >= arXiv's 15s crawl-delay ask
# Deadline for retry SCHEDULING (not a hard wall: an in-flight attempt of up
# to SCRAPE_TIMEOUT_S may finish past it, so worst case ~= budget + one
# backoff + one attempt). Real ceilings this must stay well under: the
# ScraperFunction's own Timeout (300, template.yaml) and the pipeline's
# boto3 read_timeout=780 on the synchronous invoke. When the budget is
# spent, remaining lanes get one attempt each and no retries.
SCRAPE_WALL_BUDGET_S = 150

DEFAULT_URL = "https://arxiv.org/search/?query=artificial+intelligence&searchtype=all&abstracts=show&order=-announced_date_first&size=25&classification-computer_science=y"
S3_BUCKET = os.getenv("S3_OUTPUT_BUCKET")
S3_PREFIX = os.getenv("SCRAPER_OUTPUT_PREFIX", "ai-research-pipeline/output/scraper/")
SCORED_PREFIX = os.getenv("SCORED_OUTPUT_PREFIX", "ai-research-pipeline/output/scored/")
ALERT_TOPIC_ARN = os.getenv("ALERT_TOPIC_ARN", "")
STREAK_KEY = f"{SCORED_PREFIX}scoring_failure_streak.json"
ESCALATE_AFTER = 3
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

s3 = boto3.client("s3", region_name=AWS_REGION)


def _id_sort_key(candidate):
    ident = arxiv_id(candidate["url"])
    try:
        month, num = ident.split(".")
        return (int(month), int(num))
    except ValueError:
        return (0, 0)


def _fetch_lane(lane, lane_url, scrape_limit, start_scrape, deadline):
    """One lane with bounded retries. ScraperClient returns [] on ANY failure
    (timeout/429/parse) — and these lane queries never legitimately match zero
    papers — so [] is treated as transient and retried with backoff + jitter.
    Retries stop once `deadline` (epoch seconds) has passed; the first attempt
    always runs."""
    for attempt, delay in enumerate((0,) + LANE_RETRY_DELAYS_S, start=1):
        if delay:
            if time.time() + delay >= deadline:
                logger.warning(f"Lane '{lane}': scrape wall budget spent; not retrying.")
                return []
            time.sleep(delay + random.uniform(0, 3))
        articles = ScraperClient(lane_url, scrape_limit, start_scrape).scrape()
        if articles:
            return articles
        logger.warning(f"Lane '{lane}' attempt {attempt} returned nothing"
                       f"{'; retrying' if attempt <= len(LANE_RETRY_DELAYS_S) else '; giving up'}.")
    return []


def scrape_lanes(scrape_limit, start_scrape):
    """Scrape every lane, merge by URL (recording each contributing lane in
    query_source), newest-first by numeric arXiv id."""
    merged = {}
    deadline = time.time() + SCRAPE_WALL_BUDGET_S
    lanes_alive = 0
    for i, (lane, lane_url) in enumerate(LANES):
        if i:
            time.sleep(LANE_FETCH_DELAY_S)  # be polite between lane fetches
        articles = _fetch_lane(lane, lane_url, scrape_limit, start_scrape, deadline)
        lanes_alive += bool(articles)
        for article in articles:
            entry = merged.setdefault(article["url"], {**article, "query_source": []})
            entry["query_source"].append(lane)
    if 0 < lanes_alive < len(LANES):
        logger.warning(f"Partial lane degradation: only {lanes_alive}/{len(LANES)} "
                       "lanes returned articles — candidate pool is narrower than usual.")
    ordered = sorted(merged.values(), key=_id_sort_key, reverse=True)
    logger.info(f"Lanes produced {len(ordered)} unique candidates.")
    return ordered


def _write_sidecar(scored):
    ts = datetime.now(timezone.utc)
    key = f"{SCORED_PREFIX}scored_candidates_{ts.strftime('%Y%m%d_%H%M%S')}.json"
    s3.put_object(Bucket=S3_BUCKET, Key=key, Body=json.dumps(
        {"generated_at": ts.isoformat(), "candidates": scored},
        ensure_ascii=False).encode("utf-8"))
    logger.info(f"Sidecar written: {key} ({len(scored)} candidates)")


def _read_streak():
    try:
        return json.loads(s3.get_object(Bucket=S3_BUCKET, Key=STREAK_KEY)["Body"].read())["streak"]
    except Exception:
        return 0


def _reset_failure_streak():
    s3.put_object(Bucket=S3_BUCKET, Key=STREAK_KEY,
                  Body=json.dumps({"streak": 0}).encode())


def _bump_failure_streak():
    streak = _read_streak() + 1
    s3.put_object(Bucket=S3_BUCKET, Key=STREAK_KEY,
                  Body=json.dumps({"streak": streak}).encode())
    if streak == ESCALATE_AFTER and ALERT_TOPIC_ARN:
        try:
            boto3.client("sns", region_name=AWS_REGION).publish(
                TopicArn=ALERT_TOPIC_ARN,
                Subject="AI research pipeline: scoring failing repeatedly",
                Message=f"Scoring has fallen back {streak} consecutive runs — "
                        "selection quality is degraded.")
        except Exception as e:
            logger.error(f"SNS publish failed: {e}")


def upload_to_s3(data, filename):
    try:
        key = f"{S3_PREFIX}{filename}"
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=json.dumps(data, indent=2, ensure_ascii=False),
            ContentType="application/json"
        )
        return key
    except Exception as e:
        raise RuntimeError(f"S3 upload failed: {e}")

def handler(event, context):
    """
    Lambda entry point to scrape articles from arXiv.
    Optional event keys:
    - "url": override the default ArXiv search (single-query legacy path)
    - "scrape_limit": limit the number of articles to scrape per lane
    - "skip_memory": set to true to bypass memory check (for testing)
    - "start_scrape": offset into results
    - "max_new_articles": how many articles to pass downstream (default 1)
    - "min_score": minimum composite score for selection; 0 = noon slot (fallback allowed)
    """
    scrape_limit = event.get("scrape_limit", 1)
    skip_memory = event.get("skip_memory", False)
    start_scrape = event.get("start_scrape", 0)
    # How many unposted articles to pass downstream. Scraping wider than this
    # (scrape_limit > max_new_articles) lets a run walk down the newest-first
    # list to the next article the account hasn't posted yet, instead of
    # no-opping whenever the single newest one is already in the ledger.
    max_new_articles = event.get("max_new_articles", 1)
    min_score = float(event.get("min_score", 0))
    logger.info(f"Applied min_score threshold: {min_score}")

    # --- Scrape all lanes (event 'url' override keeps the legacy single-query path) ---
    if event.get("url"):
        all_results = ScraperClient(event["url"], scrape_limit, start_scrape).scrape()
        for a in all_results:
            a.setdefault("query_source", ["custom"])
    else:
        all_results = scrape_lanes(scrape_limit, start_scrape)

    if not all_results:
        # A fully-empty scrape is a fetch failure (throttle/outage), never a
        # quiet day — 2026-07-09 this skipped a post with no alert. Be loud.
        logger.error("All lanes returned zero articles after retries — "
                     "likely arXiv rate-limiting or outage.")
        if ALERT_TOPIC_ARN:
            try:
                boto3.client("sns", region_name=AWS_REGION).publish(
                    TopicArn=ALERT_TOPIC_ARN,
                    Subject="AI research pipeline: scrape returned ZERO articles",
                    Message="All arXiv lanes returned zero articles after retries "
                            "(likely rate-limiting or an arXiv outage). Today's post "
                            "was skipped. Check /aws/lambda/ai-research-scraper logs.")
            except Exception as e:
                logger.error(f"SNS publish failed: {e}")
        return {"statusCode": 500,
                "body": json.dumps({"error": "Scraper returned no results."})}

    # --- Ledger filter ---
    candidates = all_results if skip_memory else filter_new_articles(all_results)
    if skip_memory:
        logger.info("Memory check bypassed by request.")
    if not candidates:
        notify_make_pipeline_status(message="🚫 No unposted articles — pipeline aborted.")
        return {"statusCode": 200, "body": json.dumps({
            "message": "No new articles found after memory filtering",
            "scraped_count": len(all_results), "new_count": 0})}

    # --- Score + select (fallback rules per spec §1) ---
    scoring_used, max_composite = False, None
    try:
        scored = score_candidates(candidates)
        scoring_used = True
        _reset_failure_streak()
        if buzz_mod.BUZZ_ENABLED:
            try:
                buzz_map = buzz_mod.fetch_buzz(scored)
                scored = buzz_mod.apply_buzz(scored, buzz_map)
                logger.info("Buzz blended for %d/%d candidates.",
                            sum(1 for c in scored if c.get("buzz") is not None),
                            len(scored))
            except Exception as e:
                logger.warning(f"Buzz enrichment failed; LLM-only order kept: {e}")
        max_composite = scored[0]["composite"]
        _write_sidecar(scored)
        if scored[0]["composite"] >= min_score:
            results = [c for c in scored[:max_new_articles] if c["composite"] >= min_score]
        else:
            logger.info(f"GATE no-op: max composite {max_composite} < min_score {min_score} "
                        f"({len(scored)} candidates)")
            return {"statusCode": 200, "body": json.dumps({
                "message": "No candidate cleared min_score", "gated": True,
                "max_composite": max_composite,
                "scraped_count": len(all_results), "new_count": 0})}
    except ScoringError as e:
        logger.error(f"Scoring failed: {e}")
        if min_score > 0:
            notify_make_pipeline_status(
                message=f"⚠️ Gated slot: scoring unavailable, gate unevaluable — no-op. ({e})")
            return {"statusCode": 200, "body": json.dumps({
                "message": "Scoring unavailable; gated slot no-op",
                "gate_unevaluable": True,
                "scraped_count": len(all_results), "new_count": 0})}
        # Noon slot: never miss the daily post — newest-unposted fallback.
        notify_make_pipeline_status(
            message=f"⚠️ Scoring failed; noon fallback to newest-unposted. ({e})")
        _bump_failure_streak()
        results = candidates[:max_new_articles]

    # --- Upload pipeline file (exactly the selected article(s)) ---
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    try:
        s3_key = upload_to_s3(results, f"scraped_articles_{timestamp}.json")
    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}

    return {"statusCode": 200, "body": json.dumps({
        "message": "Scraped, scored and uploaded successfully",
        "scraped_count": len(all_results), "new_count": len(results),
        "scoring_used": scoring_used, "max_composite": max_composite,
        "s3_key": s3_key, "bucket": S3_BUCKET})}
# Optional: test locally
if __name__ == "__main__":
    print(handler({}, {}))

