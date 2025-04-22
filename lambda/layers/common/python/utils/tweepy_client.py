import os
from tweepy import Client
from dotenv import load_dotenv

load_dotenv()

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

