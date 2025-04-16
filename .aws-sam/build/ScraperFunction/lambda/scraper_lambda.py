# lambda/scraper_lambda.py – Lambda handler for scraping AI articles from arXiv

import os, sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from scraper import ScraperClient  # Reuse your existing logic

DEFAULT_URL = "https://arxiv.org/search/?query=artificial+intelligence&searchtype=all&abstracts=show&order=-announced_date_first&size=25&classification-computer_science=y"

def handler(event, context):
    """
    Lambda entry point to scrape articles from arXiv.
    Optionally takes an `event["url"]` to override the default search.
    """
    url = event.get("url", DEFAULT_URL)
    scraper = ScraperClient(url)
    results = scraper.scrape()

    return {
        "statusCode": 200,
        "body": results
    }
