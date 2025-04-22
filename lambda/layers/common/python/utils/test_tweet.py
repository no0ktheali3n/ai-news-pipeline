# utils/tweepy_client.py – Twitter Client Wrapper for v2 API Posting

import os
import tweepy
from dotenv import load_dotenv

load_dotenv()

def get_twitter_client():
    """
    Initializes and returns a Tweepy Client using Twitter API v2 with OAuth1.0a user context.
    Requires all relevant keys to be stored in a .env file.
    """
    return tweepy.Client(
        bearer_token=os.getenv("TWITTER_BEARER_TOKEN"),
        consumer_key=os.getenv("TWITTER_API_KEY"),
        consumer_secret=os.getenv("TWITTER_API_SECRET"),
        access_token=os.getenv("TWITTER_ACCESS_TOKEN"),
        access_token_secret=os.getenv("TWITTER_ACCESS_SECRET")
    )

def post_tweet(text):
    """
    Posts a tweet using Tweepy v2. Returns the tweet response or an error.
    """
    client = get_twitter_client()
    try:
        response = client.create_tweet(text=text)
        print(f"✅ Tweet posted: https://twitter.com/user/status/{response.data['id']}")
        return response
    except Exception as e:
        print("❌ Error posting tweet:", e)
        return None

# Optional direct CLI usage
if __name__ == "__main__":
    test_text = "👽 Hello world from the #AutoAlien poster pipeline!  First time Tweepy lfg 🚀."
    post_tweet(test_text)
