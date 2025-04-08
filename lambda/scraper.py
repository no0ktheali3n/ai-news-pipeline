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
    def __init__(self, target_url):
        self.target_url = target_url
        #randomizes user agent for each request
        self.headers = {"User-Agent": get_random_user_agent()}

    def scrape(self):
        try:
            response = requests.get(self.target_url, headers=self.headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            base_url = "https://arxiv.org"
            articles = []

            # pulls all articles in class arxiv-result from arxiv.org
            for result in soup.find_all("li", class_="arxiv-result"):
                random_delay() # random delay from 1-3 seconds to simulate human behavior
                title_tag = result.find("p", class_="title is-5 mathjax")
                summary_tag = result.find("span", class_="abstract-full has-text-grey-dark mathjax")
                authors_tag = result.find("p", class_="authors")
                link_tag = result.find("p", class_="list-title").find("a")
                # if title_tag and link_tag scraped, append to articles list
                if title_tag and link_tag:
                    articles.append({
                        "title": title_tag.get_text(strip=True),
                        "url": base_url + link_tag["href"],
                        "authors": [a.get_text(strip=True) for a in authors_tag.find_all("a")] if authors_tag else [],
                        "snippet": summary_tag.get_text(strip=True).replace("Abstract: ", "") if summary_tag else ""
                    })

            #append articles list to pandas DataFrame and convert to dict
            df = pd.DataFrame(articles)
            return df.to_dict(orient="records")

        except Exception as e:
            print(f"Error scraping {self.target_url}: {e}")
            return []

if __name__ == "__main__":
    print("Interpreter path:", sys.executable)
    import pandas
    print("Pandas version:", pandas.__version__)

    # Example: ArXiv AI & CS filtered search
    url = "https://arxiv.org/search/?query=artificial+intelligence&searchtype=all&abstracts=show&order=-announced_date_first&size=25&classification-computer_science=y"

    client = ScraperClient(url)
    results = client.scrape()
    for entry in results:
        print(entry)

    output_path = os.path.join(os.path.dirname(__file__), "../test_output.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nScraped {len(results)} articles. Output saved to test_output.json.")