import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime
import re
from collections import Counter

CATEGORY_URL = "https://lieber.westpoint.edu/articles-of-war/"
FILE_NAME = "configs/articles.json"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

if os.path.exists(FILE_NAME):
    with open(FILE_NAME, "r", encoding="utf-8") as f:
        articles = json.load(f)
else:
    articles = []

existing_links = {a["link"] for a in articles}


def scrape_article(url):

    res = requests.get(url, headers=headers)
    soup = BeautifulSoup(res.text, "html.parser")

    title_tag = soup.select_one("h1.entry-title")
    title = title_tag.get_text(strip=True) if title_tag else ""

    author_tag = soup.select_one("span.pp-author-boxes-name a")
    author = author_tag.get_text(strip=True) if author_tag else "Unknown"

    date_tag = soup.select_one("span.published")
    date_text = date_tag.get_text(strip=True) if date_tag else ""


    date_obj = datetime.strptime(date_text, "%b %d, %Y")


    year = date_obj.year
    month = date_obj.month

    content = soup.select_one(".et_pb_text_inner")

    if content:
        paragraphs = content.find_all("p")
        text = "\n".join(p.get_text(strip=True) for p in paragraphs)
    else:
        text = ""

    return {
        "source": "Lieber Westpoint",
        "title": title,
        "author": author,
        "date": date_text,
        "year": year,
        "month": month,
        "link": url,
        "scraped_at": datetime.utcnow().isoformat(),
        "full_text": text
    }

res = requests.get(CATEGORY_URL, headers=headers)
soup = BeautifulSoup(res.text, "html.parser")

def run_scrape_lieber():
    os.makedirs("configs", exist_ok=True)

    if os.path.exists(FILE_NAME):
        with open(FILE_NAME, "r", encoding="utf-8") as f:
            articles = json.load(f)
    else:
        articles = []

    existing_links = {a["link"] for a in articles}

    res = requests.get(CATEGORY_URL, headers=headers)
    soup = BeautifulSoup(res.text, "html.parser")
    for a in soup.select("h3.entry-title a"):

        link = a.get("href")

        if not link:
            continue

        if link.startswith("/"):
            link = "https://lieber.westpoint.edu" + link

        if "/author/" in link:
            continue

        if link in existing_links:
            continue

        print("Scraping", link)

        try:
            article = scrape_article(link)
            articles.append(article)
            existing_links.add(link)

        except Exception as e:
            print("error:", link, e)

    with open(FILE_NAME, "w", encoding="utf-8") as f:
        json.dump(articles, f, indent=2, ensure_ascii=False)

    return articles