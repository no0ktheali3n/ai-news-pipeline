# utils/post_to_twitter.py – Posts full summary threads to Twitter using Tweepy with polish improvements

import sys
import os
import json
import time
import argparse
from datetime import datetime
from dotenv import load_dotenv

# Ensure project root is in path for utils import
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.twitter_threading import generate_tweet_thread
from utils.tweepy_client import post_tweet
from utils.logger import get_logger

load_dotenv()

# Setup logger
logger = get_logger("poster")

import re

_URL_RE = re.compile(r"https?://\S+")
_MENTION_RE = re.compile(r"(?<!\w)@(\w+)")
MAX_SUMMARY_CHARS = 1200


def sanitize_summary(summary, allowed_url=""):
    """Model output goes to Twitter verbatim, and the model reads untrusted
    scraped text — strip links we didn't choose and @-mentions so a poisoned
    abstract can't make the account link out or ping people."""
    cleaned = summary
    for url in set(_URL_RE.findall(cleaned)):
        if allowed_url and url.rstrip(".,;)") == allowed_url:
            continue
        cleaned = cleaned.replace(url, "")
    cleaned = _MENTION_RE.sub(r"\1", cleaned)  # drop the @, keep the word
    return " ".join(cleaned.split())[:MAX_SUMMARY_CHARS]
SUMMARY_PATH = "/tmp/summarized_output.json"
#SUMMARY_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "summarized_output.json"))
ARCHIVE_DIR = "/tmp/archive"
#ARCHIVE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "archive"))

REQUIRED_ENV_VARS = [
    "TWITTER_BEARER_TOKEN", "TWITTER_API_KEY", "TWITTER_API_SECRET",
    "TWITTER_ACCESS_TOKEN", "TWITTER_ACCESS_SECRET"
]

# ENV validation
def validate_env_vars(skip_if_dry_run=False):
    if skip_if_dry_run:
        return
    # Secrets load lazily (Secrets Manager) — fetch before checking the env,
    # otherwise validation fails on every cold start that intends to post.
    from utils.tweepy_client import _ensure_twitter_creds
    _ensure_twitter_creds()
    missing = [key for key in REQUIRED_ENV_VARS if not os.getenv(key)]
    if missing:
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing)}")


# Load summaries
def load_articles():
    try:
        with open(SUMMARY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"[ERROR] summarized_output.json not found at {SUMMARY_PATH}")
        return []

# Archive summaries
def archive_output_file():
    if not os.path.exists(ARCHIVE_DIR):
        os.makedirs(ARCHIVE_DIR)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    archive_path = os.path.join(ARCHIVE_DIR, f"summarized_output_{timestamp}.json")
    os.rename(SUMMARY_PATH, archive_path)
    logger.info(f"Archived summarized_output.json to {archive_path}")

def run_posting_pipeline(variant="summary", limit=0, dry_run=False, confirm_post=False, start_index=0, on_posted=None):
    """Posts up to `limit` articles. `on_posted(metadata)` fires immediately
    after each successful thread so callers can persist state (e.g. the posted
    ledger) before the next article — a crash mid-run must not forget tweets
    that already went out."""
    validate_env_vars(skip_if_dry_run=dry_run)
    articles = load_articles()
    results = []

    for i, article in enumerate(articles[start_index : start_index + limit]):
        logger.info(f"Posting Article {start_index + i + 1}: {article.get('title', '')[:60]}")
        metadata = post_thread(article, variant=variant, dry_run=dry_run)
        if metadata and not dry_run:
            logger.info(f"Appending metadata: {metadata}")
            results.append(metadata)
            if on_posted:
                on_posted(metadata)

    # Archive once, after the loop — renaming inside the loop crashed the
    # second article of any multi-post run (the file was already moved).
    if results and not dry_run:
        archive_output_file()

    return results

# Post full summary as a thread
def post_thread(article, variant="summary", dry_run=False, confirm_post=False):
    title = article.get("title", "")
    url = article.get("url", "")
    summary = sanitize_summary(article.get(variant, ""), allowed_url=url)

    from utils.thread_contract import MIN_TWEETS, TWEET_MAX, HOOK_MAX, sanitize_tweet

    tweets = article.get("tweets")
    if isinstance(tweets, list) and tweets:
        thread = [sanitize_tweet(t, allowed_url=url) for t in tweets]
        thread[0] = sanitize_tweet(thread[0], allowed_url="")
        ok = (len(thread) >= MIN_TWEETS and all(thread)
              and len(thread[0]) <= HOOK_MAX
              and all(len(t) <= TWEET_MAX for t in thread) and url in thread[-1])
        if not ok:
            logger.warning("Contract tweets failed transit re-check; using summary fallback.")
            thread = generate_tweet_thread(summary, title, url, [])
    else:
        thread = generate_tweet_thread(summary, title, url, [])

    print("\n=== Tweet Thread Preview ===")
    for i, tweet in enumerate(thread):
        print(f"\n--- Tweet {i+1} ---\n{tweet}\nCharacters: {len(tweet)}")

    if dry_run:
        print("\n[DRY RUN] Skipping post...")
        return None
    if confirm_post:
        confirm = input("\nDo you want to post this thread to Twitter? (y/n): ").strip().lower()
        if confirm != 'y':
            print("❌ Cancelled.")
            return None

    tweet_ids = []
    reply_to = None
    first_tweet_url = None
    status = "posted"

    for i, tweet in enumerate(thread):
        print(f"\n🌀 Posting tweet {i+1} of {len(thread)}...")
        logger.info(f"Posting tweet {i+1} of {len(thread)}")
        tweet_id = post_tweet(tweet, reply_to_id=reply_to)
        if not tweet_id:
            logger.warning(f"Tweet {i+1} failed; retrying once.")
            time.sleep(3)
            tweet_id = post_tweet(tweet, reply_to_id=reply_to)
        if tweet_id:
            tweet_ids.append(tweet_id)
            reply_to = tweet_id
            time.sleep(2)
            continue
        if not tweet_ids:               # hook itself failed twice: nothing posted
            logger.error("First tweet failed twice; aborting (article stays unledgered).")
            return None
        # Mid-thread double failure: close the thread with the link so the
        # hook has its payoff, and mark partial so the article never reposts.
        status = "partial"
        logger.error(f"Tweet {i+1} failed twice; posting minimal closing reply.")
        # post_tweet swallows ALL errors (incl. 429 rate limits) and returns
        # None — that swallowing is what routes a mid-thread 429 into this
        # retry-once → partial-closing path. The try/except is cheap insurance
        # in case that contract ever changes.
        try:
            closing_id = post_tweet(f"Full paper: {url}", reply_to_id=reply_to)
            if closing_id:
                tweet_ids.append(closing_id)
        except Exception as e:
            logger.error(f"Closing reply also failed: {e}")
        break

    if tweet_ids:
        logger.info(f"Thread posted! View the first tweet: https://twitter.com/user/status/{tweet_ids[0]}")
        first_tweet_url = f"https://twitter.com/user/status/{tweet_ids[0]}"

    return {
        "article_title": title,
        "url": url,
        "variant": variant,
        "tweet_ids": tweet_ids,
        "thread_url": first_tweet_url,
        "scores": article.get("scores"),
        "composite": article.get("composite"),
        "query_source": article.get("query_source"),
        "buzz": article.get("buzz"),
        "buzz_raw": article.get("buzz_raw"),
        "status": status,
    }

# CLI Interface
def main():
    parser = argparse.ArgumentParser(description="Post AI summaries to Twitter as threads.")
    parser.add_argument("--variant", default="v1_summary", help="Summary variant to use (default: v1_summary)")
    parser.add_argument("--dry-run", action="store_true", help="Preview the thread without posting")
    parser.add_argument("--limit", type=int, default=2, help="Limit number of articles to post")
    args = parser.parse_args()

    if not args.dry_run:
        validate_env_vars()  # Only check secrets if we’re actually posting

    run_posting_pipeline(variant=args.variant, limit=args.limit, dry_run=args.dry_run)


