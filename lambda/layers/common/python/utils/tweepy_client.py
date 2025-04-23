import json
import boto3
import os
from tweepy import Client
from dotenv import load_dotenv

load_dotenv()

# === Load Secrets from AWS Secrets Manager at import time ===
def load_twitter_secrets():
    secret_name = "TwitterAPICreds"
    region_name = os.getenv("AWS_REGION", "us-east-1")
    session = boto3.session.Session()
    client = session.client(service_name='secretsmanager', region_name=region_name)

    secret_value = client.get_secret_value(SecretId=secret_name)
    creds = json.loads(secret_value["SecretString"])
    os.environ.update(creds)  # Inject into environment

# Only inject if not already loaded (e.g. from .env locally)
if not os.getenv("TWITTER_BEARER_TOKEN"):
    load_twitter_secrets()

# === Twitter client ===
def get_twitter_client():
    return Client(
        bearer_token=os.getenv("TWITTER_BEARER_TOKEN"),
        consumer_key=os.getenv("TWITTER_API_KEY"),
        consumer_secret=os.getenv("TWITTER_API_SECRET"),
        access_token=os.getenv("TWITTER_ACCESS_TOKEN"),
        access_token_secret=os.getenv("TWITTER_ACCESS_SECRET")
    )

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
    except Exception as e:
        print("❌ Error posting tweet:", e)
        return None

