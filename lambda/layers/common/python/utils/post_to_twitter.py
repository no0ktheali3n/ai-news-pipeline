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

# Constants
DEFAULT_HASHTAGS = ["#AI"]
SUMMARY_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "summarized_output.json"))
ARCHIVE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "archive"))

REQUIRED_ENV_VARS = [
    "TWITTER_BEARER_TOKEN", "TWITTER_API_KEY", "TWITTER_API_SECRET",
    "TWITTER_ACCESS_TOKEN", "TWITTER_ACCESS_SECRET"
]

# ENV validation
def validate_env_vars():
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

# Post full summary as a thread
def post_thread(article, variant="v1_summary", dry_run=False):
    summary = article.get(variant, "")
    title = article.get("title", "")
    url = article.get("url", "")
    hashtags = [tag for tag in article.get("hashtags", "").split() if tag.startswith("#")]
    tag_block = DEFAULT_HASHTAGS + hashtags[:2]

    thread = generate_tweet_thread(summary, title, url, tag_block)

    print("\n=== Tweet Thread Preview ===")
    for i, tweet in enumerate(thread):
        print(f"\n--- Tweet {i+1} ---\n{tweet}\nCharacters: {len(tweet)}")

    if dry_run:
        print("\n[DRY RUN] Skipping post...")
        return None

    confirm = input("\nPost this thread to Twitter? (y/n): ").strip().lower()
    if confirm != 'y':
        print("❌ Cancelled.")
        return None

    tweet_ids = []
    reply_to = None

    for i, tweet in enumerate(thread):
        print(f"\n🌀 Posting tweet {i+1} of {len(thread)}...")
        logger.info(f"Posting tweet {i+1} of {len(thread)}")
        tweet_id = post_tweet(tweet, reply_to_id=reply_to)
        if tweet_id:
            tweet_ids.append(tweet_id)
            reply_to = tweet_id
            time.sleep(2)
        else:
            print("❌ Error posting one of the tweets. Aborting thread.")
            logger.error("Error posting tweet. Aborting thread.")
            return None

    if tweet_ids:
        print(f"\n📣 Thread posted! View the first tweet: https://twitter.com/user/status/{tweet_ids[0]}")
        logger.info(f"Thread posted! First tweet: https://twitter.com/user/status/{tweet_ids[0]}")

    return {
        "article_title": title,
        "url": url,
        "variant": variant,
        "tweet_ids": tweet_ids
    }

# CLI Interface
def main():
    validate_env_vars()
    parser = argparse.ArgumentParser(description="Post AI summaries to Twitter as threads.")
    parser.add_argument("--variant", default="v1_summary", help="Summary variant to use (default: v1_summary)")
    parser.add_argument("--dry-run", action="store_true", help="Preview the thread without posting")
    parser.add_argument("--limit", type=int, default=2, help="Limit number of articles to post")
    args = parser.parse_args()

    articles = load_articles()

    for i, article in enumerate(articles[:args.limit]):
        print(f"\n=== Posting Article {i+1}: {article.get('title', '')[:60]} ===")
        metadata = post_thread(article, variant=args.variant, dry_run=args.dry_run)
        if metadata and not args.dry_run:
            archive_output_file()

if __name__ == "__main__":
    main()

