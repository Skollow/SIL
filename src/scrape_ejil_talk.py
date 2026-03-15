import requests
from bs4 import BeautifulSoup
import json
import os
import time
from datetime import datetime

BASE_URL = "https://www.ejiltalk.org"
CATEGORY_URL = BASE_URL + "/category/armed-conflict/page/{}/"
FILE_NAME = "configs/articles.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
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
    for fmt in ["%B %d, %Y", "%d %B %Y", "%Y-%m-%d"]:
        try:
            return datetime.strptime(date_text.strip(), fmt)
        except ValueError:
            continue
    return None


def scrape_article(url):
    res = requests.get(url, headers=HEADERS, timeout=15)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")

    title_tag = soup.select_one("h1.blog-info-title")
    title = title_tag.get_text(strip=True) if title_tag else ""

    author_tag = soup.select_one("address.author a")
    author = author_tag.get_text(strip=True) if author_tag else "Unknown"

    date_tag = soup.select_one("time.blog-info-date")
    date_text = date_tag.get("datetime", "") if date_tag else ""
    date_obj = parse_date(date_text)

    year = date_obj.year if date_obj else 0
    month = date_obj.month if date_obj else 0

    content = soup.select_one(".pf-content")
    if content:
        paragraphs = content.find_all("p")
        text = "\n".join(p.get_text(strip=True) for p in paragraphs)
    else:
        text = ""

    return {
        "source": "EJIL Talk",
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


def run_scrape_ejil():
    articles = load_existing_articles()
    existing_links = {a["link"] for a in articles}

    page = 1
    consecutive_empty = 0

    while page <= MAX_PAGES:
        # עמוד 1 = URL בסיסי, עמוד 2+ = /page/N/
        if page == 1:
            url = BASE_URL + "/category/armed-conflict/"
        else:
            url = CATEGORY_URL.format(page)
        print(f"[EJIL Talk] Scraping page {page}: {url}")

        try:
            res = requests.get(url, headers=HEADERS, timeout=15)
        except requests.RequestException as e:
            print(f"[EJIL Talk] Request error on page {page}: {e}")
            break

        # 404 = no more pages
        if res.status_code == 404:
            print(f"[EJIL Talk] No more pages after page {page - 1}")
            break

        if res.status_code != 200:
            print(f"[EJIL Talk] Unexpected status {res.status_code}, stopping")
            break

        soup = BeautifulSoup(res.text, "html.parser")
        links = soup.select("a.article-link")

        if not links:
            consecutive_empty += 1
            if consecutive_empty >= 2:
                print("[EJIL Talk] No links found, stopping")
                break
        else:
            consecutive_empty = 0

        new_count = 0
        for a in links:
            link = a.get("href", "")
            if not link:
                continue
            if link.startswith("/"):
                link = BASE_URL + link
            if link in existing_links:
                continue

            print(f"  → Scraping: {link}")
            try:
                article = scrape_article(link)
                articles.append(article)
                existing_links.add(link)
                new_count += 1
                time.sleep(0.5)  # polite delay
            except Exception as e:
                print(f"  ✗ Error: {link} — {e}")

        print(f"  ✓ Added {new_count} new articles from page {page}")

        # Check if there's a next page link
        next_page = soup.select_one("a.next.page-numbers")
        if not next_page:
            print("[EJIL Talk] No next page found, done")
            break

        page += 1
        time.sleep(1)  # polite delay between pages

    save_articles(articles)
    return [a for a in articles if a["source"] == "EJIL Talk"]