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
MAX_PAGES = 1

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
    """
    Lawfare format: "Friday, March 20, 2026, 10:00 AM"
    נסה להסיר את יום השבוע ואת השעה לפני הפרסור.
    """
    import re
    date_text = date_text.strip()

    # הסר יום שבוע מהתחלה: "Friday, March 20..." → "March 20..."
    date_text = re.sub(r"^[A-Za-z]+,\s*", "", date_text)
    # הסר שעה מהסוף: "March 20, 2026, 10:00 AM" → "March 20, 2026"
    date_text = re.sub(r",?\s*\d{1,2}:\d{2}\s*(AM|PM)$", "", date_text, flags=re.IGNORECASE)
    date_text = date_text.strip().rstrip(",").strip()

    for fmt in ["%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%Y-%m-%d"]:
        try:
            return datetime.strptime(date_text, fmt)
        except ValueError:
            continue
    return None


def clean_text(text):
    """
    מחליף תווים Unicode מיוחדים בתווים ASCII רגילים.
    """
    if not text:
        return ""
    replacements = {
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
        "…": "...",
        " ": " ",
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    return text.strip()

def clean_url(url):
    """
    תיקון 1: שומר על ה-URL המקורי ומונע שיבוש תווים מיוחדים.
    urllib.parse.quote מקודד רק תווים שאינם חלק מ-URL תקני.
    """
    from urllib.parse import urlparse, urlunparse, quote
    try:
        parsed = urlparse(url)
        # קודד רק את ה-path בלי לשנות תווים שכבר מקודדים
        safe_path = quote(parsed.path, safe="/-_.~!$&'()*+,;=:@%")
        return urlunparse(parsed._replace(path=safe_path))
    except Exception:
        return url


def extract_authors(soup):
    """
    מחלץ כותבים מרובים ומחזיר LIST של שמות.
    כל כותב יישמר בנפרד ב-DB.
    """
    import re

    # Lawfare: כל כותב הוא <a> בתוך .post-detail__authors
    author_links = (
        soup.select(".post-detail__authors a") or
        soup.select(".byline a") or
        soup.select("a[rel='author']") or
        soup.select(".author-name a")
    )

    if author_links:
        names = [a.get_text(strip=True) for a in author_links if a.get_text(strip=True)]
        if names:
            return names  # LIST

    # fallback — טקסט גולמי, פצל לפי and / |
    author_container = (
        soup.select_one(".post-detail__authors") or
        soup.select_one(".byline") or
        soup.select_one(".author-name")
    )
    if author_container:
        raw = author_container.get_text(separator=" ", strip=True)
        raw = re.sub(r"^[Bb]y\s+", "", raw)
        # פצל לפי and, &, |
        parts = re.split(r"\s+and\s+|\s*[&|]\s*", raw)
        names = [p.strip() for p in parts if p.strip()]
        if names:
            return names

    return ["Unknown"]


def scrape_article(url):
    # תיקון 1: שמור על URL תקני
    url = clean_url(url)

    res = requests.get(url, headers=HEADERS, timeout=15)
    res.raise_for_status()

    # תיקון 2: וודא encoding נכון
    res.encoding = res.apparent_encoding or "utf-8"
    soup = BeautifulSoup(res.text, "html.parser")

    # כותרת — תיקון 2
    title_tag = (
        soup.select_one("h1.node__title") or
        soup.select_one("h1.page-title") or
        soup.select_one("h1")
    )
    title = clean_text(title_tag.get_text(strip=True)) if title_tag else ""

    # Extract authors using extract_authors() which returns a list
    authors_list = extract_authors(soup)
    # Join for storage — scrape_category will split again per author
    author = ", ".join(authors_list)
    # תאריך — תיקון 3: נסה יותר selectors ו-datetime attribute
    date_text = ""
    date_obj  = None

    # Try specific selectors only — no broad class*=date to avoid wrong matches
    for selector in [
        ".post-detail__date",
        "div.post-detail__date",
        ".post-detail__date time",
        "time[datetime]",
        ".date-display-single",
        ".field--name-post-date",
        ".published-date",
        "span.date",
    ]:
        date_tag = soup.select_one(selector)
        if not date_tag:
            continue
        raw = date_tag.get("datetime", "") or date_tag.get_text(strip=True)
        raw = raw.strip()
        if not raw:
            continue
        if "T" in raw:
            raw = raw[:10]
        date_obj = parse_date(raw)
        if date_obj:
            date_text = raw
            break

    year  = date_obj.year  if date_obj else 0
    month = date_obj.month if date_obj else 0
    day   = date_obj.day   if date_obj else 0

    content = (
        soup.select_one(".post-detail__content.mt-5-md-0") or
        soup.select_one(".post-detail__content") or
        soup.select_one(".node__content") or
        soup.select_one("article .content") or
        soup.select_one(".entry-content")
    )
    text = "\n".join(p.get_text(strip=True) for p in content.find_all("p")) if content else ""

    article = {
        "source":      "Lawfare",
        "title":       title,
        "author":      author,
        "date":        date_text,
        "year":        year,
        "month":       month,
        "day":         day,
        "link":        url,
        "scraped_at":  datetime.utcnow().isoformat(),
        "full_text":   text,
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
            ".post__title a",
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
                scraped = scrape_article(link)
                # פצל כותבים לפי פסיק ושמור כל אחד בנפרד
                import re
                raw_author = scraped.get("author", "Unknown") or "Unknown"
                author_parts = [a.strip() for a in re.split(r",\s*", raw_author) if a.strip()]
                if not author_parts:
                    author_parts = ["Unknown"]
                for single_author in author_parts:
                    article_copy = dict(scraped)
                    article_copy["author"] = single_author
                    insert_article(article_copy)
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