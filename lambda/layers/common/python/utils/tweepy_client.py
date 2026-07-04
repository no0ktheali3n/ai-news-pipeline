import json
import boto3
import os
import logging
from tweepy.errors import TooManyRequests
from datetime import datetime
from tweepy import Client
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

# === Load Secrets from AWS Secrets Manager (lazily, on first client use) ===
# Fetching at import time added a Secrets Manager round-trip to every cold
# start of every function importing this module — even ones that never tweet.
def load_twitter_secrets():
    secret_name = "TwitterAPICreds"
    region_name = os.getenv("AWS_REGION", "us-east-1")
    session = boto3.session.Session()
    client = session.client(service_name='secretsmanager', region_name=region_name)

    secret_value = client.get_secret_value(SecretId=secret_name)
    creds = json.loads(secret_value["SecretString"])
    os.environ.update(creds)  # Inject into environment

def _ensure_twitter_creds():
    # Skip if already present (e.g. from .env locally or a previous call)
    if not os.getenv("TWITTER_BEARER_TOKEN"):
        load_twitter_secrets()

# === Twitter client ===
def get_twitter_client():
    _ensure_twitter_creds()
    return Client(
        bearer_token=os.getenv("TWITTER_BEARER_TOKEN"),
        consumer_key=os.getenv("TWITTER_API_KEY"),
        consumer_secret=os.getenv("TWITTER_API_SECRET"),
        access_token=os.getenv("TWITTER_ACCESS_TOKEN"),
        access_token_secret=os.getenv("TWITTER_ACCESS_SECRET")
    )

def get_follower_count() -> "int | None":
    """Return the account's current follower count, or None on any error.

    Strictly non-blocking: every failure path is caught and logged at WARNING
    so a Twitter API hiccup can never fail or delay a post.
    Uses GET /2/users/me (free tier; ≤25 calls/day budget).
    """
    try:
        _ensure_twitter_creds()
        client = get_twitter_client()
        resp = client.get_me(user_fields=["public_metrics"])
        return resp.data.public_metrics["followers_count"]
    except Exception as e:
        logger.warning("get_follower_count failed (non-blocking): %s", e)
        return None


def post_tweet(text, reply_to_id=None):
    client = get_twitter_client()
    try:
        tweet = (
            client.create_tweet(text=text, in_reply_to_tweet_id=reply_to_id)
            if reply_to_id else client.create_tweet(text=text)
        )
        tweet_id = tweet.data["id"]
        print(f"✅ Tweeted: https://twitter.com/user/status/{tweet_id}")
        return tweet_id
    
    except TooManyRequests as e:
        headers = e.response.headers
        limit = headers.get("x-rate-limit-limit")
        remaining = headers.get("x-rate-limit-remaining")
        reset_epoch = int(headers.get("x-rate-limit-reset", 0))
        reset_time = datetime.fromtimestamp(reset_epoch).strftime('%Y-%m-%d %H:%M:%S')
        print("Rate limit exceeded. Try again later.")
        print(f"Limit: {limit}, Remaining: {remaining}")
        print(f"Rate limit resets at: {reset_time} UTC")
        print(f"Full header response:\n{headers}")

    except Exception as e:
        print("❌ Error posting tweet:", e)
        return None

