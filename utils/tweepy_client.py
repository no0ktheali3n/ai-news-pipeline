import os
import tweepy
from dotenv import load_dotenv

load_dotenv()

# Auth
api_key = os.getenv("TWITTER_API_KEY")
api_secret = os.getenv("TWITTER_API_SECRET")
access_token = os.getenv("TWITTER_ACCESS_TOKEN")
access_secret = os.getenv("TWITTER_ACCESS_SECRET")

auth = tweepy.OAuth1UserHandler(api_key, api_secret, access_token, access_secret)
twitter_client = tweepy.API(auth)

def post_tweet(text, reply_to_id=None):
    """Post a tweet. If reply_to_id is provided, post as part of thread."""
    tweet = twitter_client.update_status(status=text, in_reply_to_status_id=reply_to_id, auto_populate_reply_metadata=True)
    print(f"✅ Tweeted: https://twitter.com/user/status/{tweet.id}")
    return tweet.id
