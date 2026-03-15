import requests
from bs4 import BeautifulSoup
import json
import os
import time
from datetime import datetime

BASE_URL = "https://www.justsecurity.org"
CATEGORY_URL = BASE_URL + "/recent-articles/page/{}/"
FILE_NAME = "configs/articles.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Referer": "https://www.google.com/",
}


def load_existing_articles():
    os.makedirs("configs", exist_ok=True)
    if os.path.exists(FILE_NAME):
        with open(FILE_NAME, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_articles(articles):
    with open(FILE_NAME, "w", encoding="utf-8") as f:
        json.dump(articles, f, indent=2, ensure_ascii=False)


def parse_date(date_text):
    cleaned = date_text.replace("Published on ", "").strip()
    for fmt in ["%B %d, %Y", "%d %B %Y", "%Y-%m-%d"]:
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    return None


def scrape_article(url):
    res = requests.get(url, headers=HEADERS, timeout=15)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")

    title_tag = soup.select_one("div.post-title h1")
    title = title_tag.get_text(strip=True) if title_tag else ""

    author_tag = soup.select_one("div.post-authors a")
    author = author_tag.get_text(strip=True) if author_tag else "Unknown"

    date_tag = soup.select_one("div.post-date")
    date_text = date_tag.get_text(strip=True) if date_tag else ""
    date_obj = parse_date(date_text)

    year = date_obj.year if date_obj else 0
    month = date_obj.month if date_obj else 0

    content = soup.select_one(".post-primary")
    if content:
        paragraphs = content.find_all("p")
        text = "\n".join(p.get_text(strip=True) for p in paragraphs)
    else:
        text = ""

    return {
        "source": "Just Security",
        "title": title,
        "author": author,
        "date": date_text,
        "year": year,
        "month": month,
        "link": url,
        "scraped_at": datetime.utcnow().isoformat(),
        "full_text": text
    }


MAX_PAGES = 5


def run_scrape_just():
    articles = load_existing_articles()
    existing_links = {a["link"] for a in articles}

    page = 1

    while page <= MAX_PAGES:
        # עמוד 1 = URL בסיסי, עמוד 2+ = /page/N/
        if page == 1:
            url = BASE_URL + "/recent-articles/"
        else:
            url = CATEGORY_URL.format(page)
        print(f"[Just Security] Scraping page {page}: {url}")

        try:
            res = requests.get(url, headers=HEADERS, timeout=15)
        except requests.RequestException as e:
            print(f"[Just Security] Request error on page {page}: {e}")
            break

        if res.status_code == 404:
            print(f"[Just Security] No more pages after page {page - 1}")
            break

        if res.status_code != 200:
            print(f"[Just Security] Unexpected status {res.status_code}, stopping")
            break

        soup = BeautifulSoup(res.text, "html.parser")

        # נסה כמה selectors - המבנה של Just Security עשוי להשתנות
        raw_links = []
        for selector in [
            "div.article-block a"
            "h2.entry-title a",
            "h3.entry-title a",
            "article a[rel='bookmark']",
            "div.content-wrap a",
            "a.entry-title-link",
        ]:
            raw_links = soup.select(selector)
            if raw_links:
                print(f"  ✓ Found links with selector: {selector}")
                break

        article_links = []
        for a in raw_links:
            href = a.get("href", "")
            if not href:
                continue
            if href.startswith("/"):
                href = BASE_URL + href
            if "/author/" in href or "/category/" in href or "/tag/" in href:
                continue
            if "/page/" in href:
                continue
            if not href.startswith(BASE_URL):
                continue
            article_links.append(href)

        # Deduplicate while preserving order
        seen = set()
        unique_links = []
        for l in article_links:
            if l not in seen:
                seen.add(l)
                unique_links.append(l)

        if not unique_links:
            print("[Just Security] No article links found, stopping")
            print("  Debug - page HTML snippet:")
            print(soup.find("body").get_text()[:300] if soup.find("body") else "no body")
            break

        new_count = 0
        for link in unique_links:
            if link in existing_links:
                continue

            print(f"  → Scraping: {link}")
            try:
                article = scrape_article(link)
                articles.append(article)
                existing_links.add(link)
                new_count += 1
                time.sleep(0.5)
            except Exception as e:
                print(f"  ✗ Error: {link} — {e}")

        print(f"  ✓ Added {new_count} new articles from page {page}")

        # Check for next page
        next_page = soup.select_one("a.next.page-numbers")
        if not next_page:
            print("[Just Security] No next page found, done")
            break

        page += 1
        time.sleep(1)

    save_articles(articles)
    return [a for a in articles if a["source"] == "Just Security"]