import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime
from src.database import init_db, insert_article, article_exists
from src.categories import assign_categories

BASE_URL     = "https://www.justsecurity.org"
CATEGORY_URL = BASE_URL + "/recent-articles/page/{}/"
MAX_PAGES    = 1

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
    title     = title_tag.get_text(strip=True) if title_tag else ""

    author_tag = soup.select_one("div.post-authors a")
    author     = author_tag.get_text(strip=True) if author_tag else "Unknown"

    date_tag  = soup.select_one("div.post-date")
    date_text = date_tag.get_text(strip=True) if date_tag else ""
    date_obj  = parse_date(date_text)
    year      = date_obj.year  if date_obj else 0
    month     = date_obj.month if date_obj else 0
    day       = date_obj.day   if date_obj else 0

    content = soup.select_one(".post-primary")
    text    = "\n".join(p.get_text(strip=True) for p in content.find_all("p")) if content else ""

    article = {
        "source":     "Just Security",
        "title":      title,
        "author":     author,
        "date":       date_text,
        "year":       year,
        "month":      month,
        "day":        day,
        "link":       url,
        "scraped_at": datetime.utcnow().isoformat(),
        "full_text":  text,
    }
    article["tags"] = assign_categories(article)
    return article


# WordPress REST API endpoint — יותר אמין מ-HTML scraping
API_URL = BASE_URL + "/wp-json/wp/v2/posts"
PER_PAGE = 20


def run_scrape_just():
    init_db()
    new_total = 0

    for page in range(1, MAX_PAGES + 1):
        print(f"[Just Security] Fetching page {page} via REST API...")

        try:
            res = requests.get(
                API_URL,
                params={"per_page": PER_PAGE, "page": page, "orderby": "date", "order": "desc"},
                headers=HEADERS,
                timeout=15
            )
        except requests.RequestException as e:
            print(f"[Just Security] Request error: {e}")
            break

        if res.status_code == 400 or res.status_code == 404:
            print("[Just Security] No more pages.")
            break
        if res.status_code != 200:
            print(f"[Just Security] Status {res.status_code}, stopping.")
            break

        try:
            posts = res.json()
        except Exception as e:
            print(f"[Just Security] JSON parse error: {e}")
            break

        if not posts:
            print("[Just Security] Empty response, done.")
            break

        # בדוק כמה עמודים יש בסך הכל
        total_pages = int(res.headers.get("X-WP-TotalPages", 1))
        print(f"  Total pages available: {total_pages}")

        new_count = 0
        for post in posts:
            link = post.get("link", "")
            if not link or article_exists(link):
                continue

            print(f"  → {link}")
            try:
                article = scrape_article(link)
                insert_article(article)
                new_count += 1
                new_total += 1
                time.sleep(0.5)
            except Exception as e:
                print(f"  ✗ {link} — {e}")

        print(f"  ✓ Added {new_count} new articles from page {page}")

        if page >= total_pages:
            print("[Just Security] Reached last page.")
            break

        time.sleep(1)

    return new_total