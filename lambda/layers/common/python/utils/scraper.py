## `lambda/scraper.py` – ArXiv-Specific Scraper Implementation
import sys, os
#add project root (where .git, README.md, and utils/ live) to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

print("Working dir:", os.getcwd())
print("sys.path includes:", sys.path)

import requests
import pandas as pd
from bs4 import BeautifulSoup
from utils.user_agents import get_random_user_agent
from utils.request_helpers import random_delay
import json

class ScraperClient:
    def __init__(self, target_url, limit=None, start_scrape=0):
        self.target_url = target_url
        self.limit = limit
        self.start_scrape = start_scrape
        self.headers = {"User-Agent": get_random_user_agent()}  #randomizes user agent for each request

    def scrape(self):
        try:
            response = requests.get(self.target_url, headers=self.headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            base_url = "https://arxiv.org"
            articles = []

            # pulls all articles in class arxiv-result from arxiv.org starting from start_scrape and ending at limit
            for i, result in enumerate(soup.find_all("li", class_="arxiv-result")):
                if i < self.start_scrape:
                    continue  # Skip this article

                random_delay()

                link_tag = result.find("p", class_="list-title").find("a")
                title_tag = result.find("p", class_="title is-5 mathjax")
                authors_tag = result.find("p", class_="authors")
                summary_tag = result.find("span", class_="abstract-full has-text-grey-dark mathjax")
                date_tag = result.find("p", class_="is-size-7")

                if title_tag and link_tag:
                    href = link_tag.get("href", "")
                    full_url = href if href.startswith("http") else base_url + href
                    articles.append({
                        "title": title_tag.get_text(strip=True),
                        "url": full_url,
                        "authors": [a.get_text(strip=True) for a in authors_tag.find_all("a")] if authors_tag else [],
                        "snippet": summary_tag.get_text(strip=True).replace("Abstract: ", "") if summary_tag else "",
                        "published": date_tag.get_text(strip=True).split(": ")[-1] if date_tag else ""
                    })

                if self.limit and len(articles) >= self.limit:
                    break

            #append articles list to pandas DataFrame and convert to dict
            df = pd.DataFrame(articles)
            return df.to_dict(orient="records")

        except Exception as e:
            print(f"Error scraping {self.target_url}: {e}")
            return []

if __name__ == "__main__":
    print("Interpreter path:", sys.executable)
    print("Pandas version:", pd.__version__)

    # Example: ArXiv AI & CS filtered search
    url = "https://arxiv.org/search/?query=artificial+intelligence&searchtype=all&abstracts=show&order=-announced_date_first&size=200&classification-computer_science=y" #overwrites default url

    client = ScraperClient(url)
    results = client.scrape()
    for entry in results:
        print(entry)

    output_path = os.path.join(os.path.dirname(__file__), "../test_output.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nScraped {len(results)} articles. Output saved to test_output.json.")