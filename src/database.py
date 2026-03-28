"""
database.py — SQLite layer replacing articles.json
All article data is stored in configs/articles.db
"""

import sqlite3
import os

DB_PATH = "configs/articles.db"


def get_conn():
    os.makedirs("configs", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            source      TEXT    NOT NULL,
            title       TEXT    NOT NULL,
            author      TEXT    NOT NULL DEFAULT 'Unknown',
            date        TEXT,
            year        INTEGER NOT NULL DEFAULT 0,
            month       INTEGER NOT NULL DEFAULT 0,
            day         INTEGER NOT NULL DEFAULT 0,
            link        TEXT    NOT NULL UNIQUE,
            full_text   TEXT,
            scraped_at  TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS article_tags (
            article_id  INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
            tag         TEXT    NOT NULL,
            PRIMARY KEY (article_id, tag)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_source ON articles(source)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_year   ON articles(year)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_author ON articles(author)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tags   ON article_tags(tag)")
    # Migrate existing DBs that were created before the day column was added
    existing_cols = [r[1] for r in conn.execute("PRAGMA table_info(articles)").fetchall()]
    if "day" not in existing_cols:
        conn.execute("ALTER TABLE articles ADD COLUMN day INTEGER NOT NULL DEFAULT 0")
    conn.commit()
    conn.close()


def insert_article(article: dict) -> int | None:
    """
    Insert a single article. Skips duplicates (same link).
    Returns the new row id, or None if already existed.
    """
    conn = get_conn()
    try:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO articles
                (source, title, author, date, year, month, day, link, full_text, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                article.get("source", ""),
                article.get("title", ""),
                article.get("author", "Unknown"),
                article.get("date", ""),
                article.get("year", 0),
                article.get("month", 0),
                article.get("day", 0),
                article.get("link", ""),
                article.get("full_text", ""),
                article.get("scraped_at", ""),
            )
        )
        conn.commit()
        row_id = cur.lastrowid if cur.rowcount else None

        # Insert tags if new row was created
        if row_id and article.get("tags"):
            conn.executemany(
                "INSERT OR IGNORE INTO article_tags (article_id, tag) VALUES (?, ?)",
                [(row_id, tag) for tag in article["tags"]]
            )
            conn.commit()

        return row_id
    except Exception as e:
        print(f"DB insert error: {e}")
        return None
    finally:
        conn.close()


def get_all_articles() -> list[dict]:
    """Return all articles as a list of dicts, with tags included."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM articles ORDER BY year DESC, month DESC"
    ).fetchall()

    article_ids = [r["id"] for r in rows]
    tags_map = {}
    if article_ids:
        placeholders = ",".join("?" * len(article_ids))
        tag_rows = conn.execute(
            f"SELECT article_id, tag FROM article_tags WHERE article_id IN ({placeholders})",
            article_ids
        ).fetchall()
        for tr in tag_rows:
            tags_map.setdefault(tr["article_id"], []).append(tr["tag"])

    conn.close()

    result = []
    for r in rows:
        d = dict(r)
        d["tags"] = tags_map.get(r["id"], [])
        result.append(d)
    return result


def article_exists(link: str) -> bool:
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM articles WHERE link = ?", (link,)
    ).fetchone()
    conn.close()
    return row is not None


def get_filter_options(selected_source="", selected_author="",
                       selected_year="", selected_month="", selected_tags=None):
    """
    Return available filter values consistent with current selections.
    Each filter is computed excluding itself (faceted filtering).
    """
    selected_tags = selected_tags or []
    conn = get_conn()

    def query_with_filters(exclude=None):
        conditions = []
        params = []

        if exclude != "source" and selected_source:
            conditions.append("a.source = ?")
            params.append(selected_source)
        if exclude != "author" and selected_author:
            conditions.append("a.author = ?")
            params.append(selected_author)
        if exclude != "year" and selected_year:
            conditions.append("a.year = ?")
            params.append(int(selected_year))
        if exclude != "month" and selected_month:
            conditions.append("a.month = ?")
            params.append(int(selected_month))
        if exclude != "tags" and selected_tags:
            placeholders = ",".join("?" * len(selected_tags))
            conditions.append(
                f"a.id IN (SELECT article_id FROM article_tags WHERE tag IN ({placeholders}))"
            )
            params.extend(selected_tags)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        return where, params

    # Sources
    w, p = query_with_filters(exclude="source")
    sources = [r[0] for r in conn.execute(
        f"SELECT DISTINCT source FROM articles a {w} ORDER BY source", p
    ).fetchall()]

    # Authors
    w, p = query_with_filters(exclude="author")
    authors = [r[0] for r in conn.execute(
        f"SELECT DISTINCT author FROM articles a {w} ORDER BY author", p
    ).fetchall()]

    # Years
    w, p = query_with_filters(exclude="year")
    years = [r[0] for r in conn.execute(
        f"SELECT DISTINCT year FROM articles a {w} ORDER BY year DESC", p
    ).fetchall()]

    # Months
    w, p = query_with_filters(exclude="month")
    months = [r[0] for r in conn.execute(
        f"SELECT DISTINCT month FROM articles a {w} ORDER BY month", p
    ).fetchall()]

    # Tag counts
    w, p = query_with_filters(exclude="tags")
    tag_counts = {}
    tag_rows = conn.execute(
        f"""
        SELECT t.tag, COUNT(*) as cnt
        FROM article_tags t
        JOIN articles a ON a.id = t.article_id
        {w}
        GROUP BY t.tag
        """, p
    ).fetchall()
    for row in tag_rows:
        tag_counts[row[0]] = row[1]

    conn.close()
    return {
        "sources": sources,
        "authors": authors,
        "years":   years,
        "months":  months,
        "tag_counts": tag_counts,
    }