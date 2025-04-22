# lambda/poster_handler.py – AWS Lambda handler for posting summary threads

import os
import sys
import json
import traceback
from dotenv import load_dotenv

# Ensure project root is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.post_to_twitter import post_thread
from utils.logger import logger, validate_env_vars

# Load environment and validate keys
load_dotenv()
validate_env_vars()

def handler(event, context):
    """
    Lambda entry point for posting a tweet thread.
    Expects event to contain:
    {
        "article": {
            "title": "...",
            "url": "...",
            "v1_summary": "...",
            "hashtags": "#AI #ML"
        },
        "variant": "v1_summary"
    }
    """
    try:
        article = event.get("article")
        variant = event.get("variant", "v1_summary")

        if not article:
            logger.error("Missing 'article' in event payload")
            raise ValueError("Missing 'article' in event payload")

        required_keys = ["title", "url", variant]
        missing = [key for key in required_keys if key not in article]
        if missing:
            logger.error(f"Article payload is missing required fields: {missing}")
            raise ValueError(f"Missing article fields: {', '.join(missing)}")

        logger.info(f"🧵 Posting Twitter thread for: {article['title'][:60]}")

        result = post_thread(article, variant=variant, dry_run=False)

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Thread posted successfully",
                "tweet_ids": result.get("tweet_ids", []),
                "first_tweet": f"https://twitter.com/user/status/{result['tweet_ids'][0]}" if result.get("tweet_ids") else None
            })
        }

    except Exception as e:
        logger.exception("❌ Error occurred in Twitter thread posting")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": str(e),
                "trace": traceback.format_exc()
            })
        }

# Optional local trigger
if __name__ == "__main__":
    test_event = {
        "article": {
            "title": "Example Paper Title",
            "url": "https://arxiv.org/abs/2504.12345",
            "v1_summary": "This is an example summary of the research paper to demonstrate thread posting.",
            "hashtags": "#AI #ML"
        },
        "variant": "v1_summary"
    }

    response = handler(test_event, None)
    print("\n🔁 Lambda Response:")
    print(json.dumps(response, indent=2))
