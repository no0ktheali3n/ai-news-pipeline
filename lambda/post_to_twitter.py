# utils/post_to_twitter.py – Posts full summary threads to Twitter using Tweepy

import sys
import os
import json
import time
from dotenv import load_dotenv

# Ensure project root is in path for utils import
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.twitter_threading import generate_tweet_thread
from utils.tweepy_client import post_tweet

load_dotenv()

# Constants
DEFAULT_HASHTAGS = ["#AI"]
SUMMARY_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "summarized_output.json"))

# Load summaries
try:
    with open(SUMMARY_PATH, "r", encoding="utf-8") as f:
        articles = json.load(f)
except FileNotFoundError:
    print(f"[ERROR] summarized_output.json not found at {SUMMARY_PATH}")
    articles = []

# Post full summary as a thread
def post_thread(article, variant="v1_summary"):
    summary = article.get(variant, "")
    title = article.get("title", "")
    url = article.get("url", "")
    hashtags = [tag for tag in article.get("hashtags", "").split() if tag.startswith("#")]
    tag_block = DEFAULT_HASHTAGS + hashtags[:2]

    thread = generate_tweet_thread(summary, title, url, tag_block)

    # Show preview
    print("\n=== Tweet Thread Preview ===")
    for i, tweet in enumerate(thread):
        print(f"\n--- Tweet {i+1} ---\n{tweet}\nCharacters: {len(tweet)}")

    confirm = input("\nPost this thread? (y/n): ").strip().lower()
    if confirm != 'y':
        print("❌ Cancelled.")
        return

    tweet_ids = []
    reply_to = None

    for tweet in thread:
        tweet_id = post_tweet(tweet, reply_to_id=reply_to)
        if tweet_id:
            tweet_ids.append(tweet_id)
            reply_to = tweet_id
            time.sleep(2)
        else:
            print("❌ Error posting one of the tweets. Aborting thread.")
            break

    return tweet_ids

# Manual trigger
if __name__ == "__main__":
    for i, article in enumerate(articles[:2]):
        print(f"\n=== Posting Article {i+1}: {article.get('title', '')[:60]} ===")
        post_thread(article, variant="v1_summary")
