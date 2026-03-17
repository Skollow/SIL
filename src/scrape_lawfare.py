import requests
try:
    import cloudscraper
    HAS_CLOUDSCRAPER = True
except ImportError:
    HAS_CLOUDSCRAPER = False
from bs4 import BeautifulSoup
import time
from datetime import datetime
from src.database import init_db, insert_article, article_exists
from src.categories import assign_categories

BASE_URL  = "https://www.lawfaremedia.org"
MAX_PAGES = 5

CATEGORIES = [
    {
        "name":  "Armed Conflict",
        "page1": BASE_URL + "/topics/armed-conflict",
        "paged": BASE_URL + "/topics/armed-conflict?page={}",
    },
    {
        "name":  "Cybersecurity & Tech",
        "page1": BASE_URL + "/topics/cybersecurity-tech",
        "paged": BASE_URL + "/topics/cybersecurity-tech?page={}",
    },
]

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
    "Referer": "https://www.lawfaremedia.org/",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}


def make_session():
    """Use cloudscraper if available, otherwise fall back to requests session."""
    if HAS_CLOUDSCRAPER:
        session = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False}
        )
        session.headers.update(HEADERS)
        print("  Using cloudscraper")
    else:
        session = requests.Session()
        session.headers.update(HEADERS)
        try:
            session.get(BASE_URL, timeout=15)
            time.sleep(1)
        except Exception:
            pass
        print("  WARNING: cloudscraper not installed. Run: pip install cloudscraper")
    return session


def parse_date(date_text):
    date_text = date_text.strip()
    for fmt in ["%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%Y-%m-%d"]:
        try:
            return datetime.strptime(date_text, fmt)
        except ValueError:
            continue
    return None


def scrape_article(url):
    res = requests.get(url, headers=HEADERS, timeout=15)  # individual articles use plain requests
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")

    title_tag = (
        soup.select_one("h1.node__title") or
        soup.select_one("h1.page-title") or
        soup.select_one("h1")
    )
    title = title_tag.get_text(strip=True) if title_tag else ""

    author_tag = (
        soup.select_one(".field--name-field-authors a") or
        soup.select_one(".author-name a") or
        soup.select_one("a[rel='author']") or
        soup.select_one(".byline a")
    )
    author = author_tag.get_text(strip=True) if author_tag else "Unknown"

    date_tag = (
        soup.select_one("time[datetime]") or
        soup.select_one(".date-display-single") or
        soup.select_one(".field--name-post-date") or
        soup.select_one(".published-date")
    )
    if date_tag:
        date_text = date_tag.get("datetime", "") or date_tag.get_text(strip=True)
    else:
        date_text = ""
    # datetime attr often "2024-03-15T..." — take date part only
    date_text = date_text[:10] if "T" in date_text else date_text
    date_obj  = parse_date(date_text)
    year      = date_obj.year  if date_obj else 0
    month     = date_obj.month if date_obj else 0
    day       = date_obj.day   if date_obj else 0

    content = (
        soup.select_one(".field--name-body") or
        soup.select_one(".node__content") or
        soup.select_one("article .content") or
        soup.select_one(".entry-content")
    )
    text = "\n".join(p.get_text(strip=True) for p in content.find_all("p")) if content else ""

    article = {
        "source":     "Lawfare",
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


def scrape_category(category: dict) -> int:
    new_total = 0
    session = make_session()

    for page in range(1, MAX_PAGES + 1):
        url = category["page1"] if page == 1 else category["paged"].format(page)
        print(f"[Lawfare / {category['name']}] Page {page}: {url}")

        try:
            res = session.get(url, timeout=15)
        except requests.RequestException as e:
            print(f"  Request error: {e}")
            break

        if res.status_code == 404:
            print("  No more pages.")
            break
        if res.status_code != 200:
            print(f"  Status {res.status_code}, stopping.")
            break

        soup      = BeautifulSoup(res.text, "html.parser")
        link_tags = []
        for selector in [
            "h3.post__link a",
            "h3.post__title a",
            "h3.node__title a",
            "h2.node__title a",
            "h3.article-title a",
            "h2.article-title a",
            "article h2 a",
            "article h3 a",
            ".views-row h3 a",
            ".views-row h2 a",
            "h3.views-field a",
        ]:
            link_tags = soup.select(selector)
            if link_tags:
                print(f"  ✓ Selector: {selector}")
                break

        if not link_tags:
            print("  No links found, stopping.")
            print(soup.find("body").get_text()[:300] if soup.find("body") else "no body")
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
            if any(x in link for x in ["/topic/", "/author/", "/tag/"]):
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


def run_scrape_lawfare() -> int:
    init_db()
    total = 0
    for category in CATEGORIES:
        total += scrape_category(category)
    print(f"[Lawfare] Done — {total} new articles total.")
    return total