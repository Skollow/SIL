import requests
from bs4 import BeautifulSoup
import json
import os
import time
from datetime import datetime

BASE_URL = "https://lieber.westpoint.edu"
CATEGORY_URL = BASE_URL + "/articles-of-war/page/{}/"
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
    for fmt in ["%b %d, %Y", "%B %d, %Y", "%d %B %Y"]:
        try:
            return datetime.strptime(date_text.strip(), fmt)
        except ValueError:
            continue
    return None


def scrape_article(url):
    res = requests.get(url, headers=HEADERS, timeout=15)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")

    title_tag = soup.select_one("h1.entry-title")
    title = title_tag.get_text(strip=True) if title_tag else ""

    author_tag = soup.select_one("span.pp-author-boxes-name a")
    if not author_tag:
        author_tag = soup.select_one(".author-name a")
    author = author_tag.get_text(strip=True) if author_tag else "Unknown"

    date_tag = soup.select_one("span.published")
    if not date_tag:
        date_tag = soup.select_one("time.entry-date")
    date_text = date_tag.get_text(strip=True) if date_tag else ""
    date_obj = parse_date(date_text)

    year = date_obj.year if date_obj else 0
    month = date_obj.month if date_obj else 0

    content = soup.select_one(".et_pb_text_inner")
    if not content:
        content = soup.select_one(".entry-content")
    if content:
        paragraphs = content.find_all("p")
        text = "\n".join(p.get_text(strip=True) for p in paragraphs)
    else:
        text = ""

    return {
        "source": "Lieber Institute",
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


def run_scrape_lieber():
    articles = load_existing_articles()
    existing_links = {a["link"] for a in articles}

    page = 1

    while page <= MAX_PAGES:
        # First page has no /page/N/ suffix
        if page == 1:
            url = BASE_URL + "/articles-of-war/"
        else:
            url = CATEGORY_URL.format(page)

        print(f"[Lieber] Scraping page {page}: {url}")

        try:
            res = requests.get(url, headers=HEADERS, timeout=15)
        except requests.RequestException as e:
            print(f"[Lieber] Request error on page {page}: {e}")
            break

        if res.status_code == 404:
            print(f"[Lieber] No more pages after page {page - 1}")
            break

        if res.status_code != 200:
            print(f"[Lieber] Unexpected status {res.status_code}, stopping")
            break

        soup = BeautifulSoup(res.text, "html.parser")

        # נסה כמה selectors — המבנה של Lieber משתנה בין עמודים
        link_tags = []
        for selector in [
            "h3.entry-title a",
            "h2.entry-title a",
            "h1.entry-title a",
            "article a[rel='bookmark']",
            ".post-title a",
            ".entry-header a",
            "a[rel='bookmark']",
            ".et_pb_post h2 a",
            ".et_pb_post h3 a",
            ".et_pb_post a",
        ]:
            link_tags = soup.select(selector)
            if link_tags:
                print(f"  ✓ Found links with selector: {selector}")
                break

        if not link_tags:
            print("[Lieber] No article links found — printing HTML snippet for debug:")
            body = soup.find("body")
            print(body.get_text()[:500] if body else "no body")
            break

        new_count = 0
        for a in link_tags:
            link = a.get("href", "")
            if not link:
                continue
            if link.startswith("/"):
                link = BASE_URL + link
            if "/author/" in link or "/category/" in link:
                continue
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
            print("[Lieber] No next page found, done")
            break

        page += 1
        time.sleep(1)

    save_articles(articles)
    return [a for a in articles if a["source"] == "Lieber Institute"]