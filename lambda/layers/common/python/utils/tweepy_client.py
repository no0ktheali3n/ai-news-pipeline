import io
import json
import boto3
import os
import logging
import requests
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from tweepy.errors import TooManyRequests
from datetime import datetime
from tweepy import Client
import tweepy as _tweepy_mod
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

# === v1.1 API (media upload) ===
def get_v1_api():
    """v1.1 API object for media upload — the v2 Client has no media methods."""
    _ensure_twitter_creds()
    auth = _tweepy_mod.OAuth1UserHandler(
        consumer_key=os.getenv("TWITTER_API_KEY"),
        consumer_secret=os.getenv("TWITTER_API_SECRET"),
        access_token=os.getenv("TWITTER_ACCESS_TOKEN"),
        access_token_secret=os.getenv("TWITTER_ACCESS_SECRET"),
    )
    return _tweepy_mod.API(auth)


def upload_media(image_bytes, filename, alt_text):
    """Returns media_id string or None. NEVER raises; alt text is best-effort."""
    try:
        api = get_v1_api()
        media = api.media_upload(filename=filename, file=io.BytesIO(image_bytes))
        media_id = str(media.media_id)
    except Exception as e:
        logger.warning(f"media upload failed: {e}")
        return None
    try:
        api.create_media_metadata(media_id, alt_text=(alt_text or "")[:1000])
    except Exception as e:
        logger.warning(f"media alt-text failed (non-fatal): {e}")
    return media_id


def _download_figure(url):
    """None unless 200 + image/* + 10KB..4.9MB."""
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200 or not r.headers.get("Content-Type", "").startswith("image/"):
            return None
        if not (10_000 <= len(r.content) <= 4_900_000):
            return None
        return r.content
    except Exception:
        return None


# Hard bound on the follower lookup: a hung Twitter call must never stall
# post_thread past the ledger write (posted-but-unledgered = repost risk).
# Module-level so tests can patch it down.
GET_ME_TIMEOUT_S = float(os.getenv("GET_ME_TIMEOUT_S", "10"))


def get_follower_count() -> "int | None":
    """Return the account's current follower count, or None on any error.

    Strictly non-blocking: every failure path is caught and logged at WARNING
    so a Twitter API hiccup can never fail or delay a post.
    Uses GET /2/users/me (free tier; ≤25 calls/day budget).
    """
    # NOTE: no `with` block — the context manager's __exit__ does
    # shutdown(wait=True), which would block on a hung thread and defeat the
    # timeout entirely. shutdown(wait=False) abandons the worker instead.
    ex = ThreadPoolExecutor(max_workers=1)
    try:
        _ensure_twitter_creds()
        client = get_twitter_client()
        resp = ex.submit(client.get_me, user_fields=["public_metrics"]).result(timeout=GET_ME_TIMEOUT_S)
        return resp.data.public_metrics["followers_count"]
    except (FuturesTimeout, Exception) as e:
        logger.warning("get_follower_count failed (non-blocking): %s", e)
        return None
    finally:
        ex.shutdown(wait=False, cancel_futures=True)


def post_tweet(text, reply_to_id=None, media_ids=None):
    client = get_twitter_client()
    try:
        extra = {}
        if media_ids is not None:
            extra["media_ids"] = media_ids
        tweet = (
            client.create_tweet(text=text, in_reply_to_tweet_id=reply_to_id, **extra)
            if reply_to_id else client.create_tweet(text=text, **extra)
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

