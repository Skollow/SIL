import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime
from src.database import init_db, insert_article, article_exists
from src.categories import assign_categories

BASE_URL  = "https://opiniojuris.org"
MAX_PAGES = 1

# שתי קטגוריות לסריקה
CATEGORIES = [
    {
        "name":   "International Humanitarian Law",
        "page1":  BASE_URL + "/category/international-humanitarian-law/",
        "paged":  BASE_URL + "/category/international-humanitarian-law/page/{}/",
    },
    {
        "name":   "Use of Force",
        "page1":  BASE_URL + "/category/use-of-force/",
        "paged":  BASE_URL + "/category/use-of-force/page/{}/",
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
    "Referer": "https://www.google.com/",
}


def parse_date(date_text):
    import re
    date_text = date_text.strip()
    # Opinio Juris format: "18.03.26" → day=18, month=03, year=2026
    m = re.match(r"^(\d{1,2})\.(\d{2})\.(\d{2})$", date_text)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), 2000 + int(m.group(3))
        try:
            return datetime(year, month, day)
        except ValueError:
            pass
    for fmt in ["%B %d, %Y", "%d %B %Y", "%b %d, %Y", "%Y-%m-%d"]:
        try:
            return datetime.strptime(date_text, fmt)
        except ValueError:
            continue
    return None


def scrape_article(url):
    res = requests.get(url, headers=HEADERS, timeout=15)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")

    title_tag = (
        soup.select_one("h1.entry-title") or
        soup.select_one("h1.entry_title") or
        soup.select_one("h1")
    )
    title = title_tag.get_text(strip=True) if title_tag else ""

    # Date — Opinio Juris uses span.time with format "18.03.26"
    date_tag  = soup.select_one("span.time") or soup.select_one("time[datetime]")
    date_text = date_tag.get_text(strip=True) if date_tag else ""
    date_obj  = parse_date(date_text)
    year  = date_obj.year  if date_obj else 0
    month = date_obj.month if date_obj else 0
    day   = date_obj.day   if date_obj else 0

    # Content — inside div.pf-content
    content = (
        soup.select_one("div.pf-content") or
        soup.select_one(".entry-content") or
        soup.select_one(".post-content")
    )

    # Author — first bracketed [Name is...] paragraph inside content
    author = "Unknown"
    if content:
        first_em = content.select_one("p em")
        if first_em:
            import re
            raw = first_em.get_text(strip=True)
            # Extract name before "is" or "was" — e.g. "[Thomas Obel Hansen is..."
            raw = re.sub(r"^\[", "", raw)
            m = re.match(r"^([^,\[]+?)\s+(is|was|serves|currently)", raw, re.IGNORECASE)
            if m:
                author = m.group(1).strip()

    text = "\n".join(p.get_text(strip=True) for p in content.find_all("p")) if content else ""

    article = {
        "source":     "Opinio Juris",
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
    """סורק קטגוריה אחת ומחזיר כמות מאמרים חדשים."""
    new_total = 0

    for page in range(1, MAX_PAGES + 1):
        url = category["page1"] if page == 1 else category["paged"].format(page)
        print(f"[Opinio Juris / {category['name']}] Page {page}: {url}")

        try:
            res = requests.get(url, headers=HEADERS, timeout=15)
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
            "h2.entry_title a",
            "h2.entry-title a",
            "h3.entry-title a",
            "article a[rel='bookmark']",
            "a[rel='bookmark']",
            ".post-title a",
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
            if article_exists(link):
                continue

            print(f"  → {link}")
            try:
                scraped = scrape_article(link)
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


def run_scrape_opinio() -> int:
    init_db()
    total = 0
    for category in CATEGORIES:
        total += scrape_category(category)
    print(f"[Opinio Juris] Done — {total} new articles total.")
    return total