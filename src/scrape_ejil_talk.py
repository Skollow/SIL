import requests
from bs4 import BeautifulSoup
import os
import time
from datetime import datetime
from src.database import init_db, insert_article, article_exists
from src.categories import assign_categories

BASE_URL     = "https://www.ejiltalk.org"
CATEGORY_URL = BASE_URL + "/category/armed-conflict/?pagenum={}"
MAX_PAGES    = 5

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
    title     = title_tag.get_text(strip=True) if title_tag else ""

    author_tag = soup.select_one("address.author a")
    author     = author_tag.get_text(strip=True) if author_tag else "Unknown"

    date_tag  = soup.select_one("time.blog-info-date")
    date_text = date_tag.get("datetime", "") if date_tag else ""
    date_obj  = parse_date(date_text)
    year      = date_obj.year  if date_obj else 0
    month     = date_obj.month if date_obj else 0

    content = soup.select_one(".pf-content")
    text    = "\n".join(p.get_text(strip=True) for p in content.find_all("p")) if content else ""

    article = {
        "source":     "EJIL Talk",
        "title":      title,
        "author":     author,
        "date":       date_text,
        "year":       year,
        "month":      month,
        "link":       url,
        "scraped_at": datetime.utcnow().isoformat(),
        "full_text":  text,
    }
    article["tags"] = assign_categories(article)
    return article


def run_scrape_ejil():
    init_db()
    new_total = 0

    for page in range(1, MAX_PAGES + 1):
        url = BASE_URL + "/category/armed-conflict/" if page == 1 else CATEGORY_URL.format(page)
        print(f"[EJIL Talk] Scraping page {page}: {url}")

        try:
            res = requests.get(url, headers=HEADERS, timeout=15)
        except requests.RequestException as e:
            print(f"[EJIL Talk] Request error: {e}")
            break

        if res.status_code == 404:
            print("[EJIL Talk] No more pages.")
            break
        if res.status_code != 200:
            print(f"[EJIL Talk] Status {res.status_code}, stopping.")
            break

        soup      = BeautifulSoup(res.text, "html.parser")
        link_tags = []
        for selector in ["a.article-link", "h2.entry-title a", "h3.entry-title a", "article a[rel='bookmark']"]:
            link_tags = soup.select(selector)
            if link_tags:
                break

        if not link_tags:
            print("[EJIL Talk] No links found, stopping.")
            break

        new_count = 0
        for a in link_tags:
            link = a.get("href", "")
            if not link:
                continue
            if link.startswith("/"):
                link = BASE_URL + link
            if not link.startswith(BASE_URL):
                continue
            if article_exists(link):
                continue

            print(f"  → {link}")
            try:
                insert_article(scrape_article(link))
                new_count += 1
                new_total += 1
                time.sleep(0.5)
            except Exception as e:
                print(f"  ✗ {link} — {e}")

        print(f"  ✓ Added {new_count} new articles from page {page}")
        time.sleep(1)

    return new_total