from flask import Flask, render_template, request, jsonify
from whoosh.index import create_in, open_dir
from whoosh.qparser import MultifieldParser
from whoosh.fields import Schema, TEXT, NUMERIC, ID
from whoosh import query as whoosh_query
from whoosh.sorting import FieldFacet
from markupsafe import escape
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from src.categories import assign_categories, ALL_CATEGORY_NAMES
from src.database import init_db, get_all_articles, get_filter_options
import os
import shutil
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(32))

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["300/day", "60/minute"]
)

# ── Scrapers (imported lazily to avoid circular issues) ──────────────────────
def run_all_scrapers():
    from src.scrape_ejil_talk        import run_scrape_ejil
    from src.scrape_just_security    import run_scrape_just
    from src.scrape_lieber_westpoint import run_scrape_lieber
    from src.scrape_opinio_juris     import run_scrape_opinio

    total = 0
    for scraper in [run_scrape_ejil, run_scrape_just, run_scrape_lieber, run_scrape_opinio]:
        try:
            total += scraper()
        except Exception as e:
            print(f"Scraper error ({scraper.__name__}): {e}")
    return total

# ── 1. INIT DATABASE & LOAD ARTICLES ────────────────────────────────────────
init_db()
run_all_scrapers()

articles = get_all_articles()
print(f"DEBUG: get_all_articles() returned {len(articles)} articles.")

# Assign tags in-memory for any article missing them
for a in articles:
    if not a.get("tags"):
        a["tags"] = assign_categories(a)

if not articles:
    print("WARNING: No articles loaded from database! Check configs/articles.db path.")
else:
    sources = {}
    for a in articles:
        sources[a.get("source","?")] = sources.get(a.get("source","?"), 0) + 1
    print(f"DEBUG: Articles by source: {sources}")

# ── 2. BUILD / REFRESH SEARCH INDEX ─────────────────────────────────────────
DB_PATH = "configs/articles.db"

schema = Schema(
    title=TEXT(stored=True),
    author=TEXT(stored=True),
    source=TEXT(stored=True),
    year=NUMERIC(stored=True),
    month=NUMERIC(stored=True),
    content=TEXT(stored=True),
    link=ID(stored=True)
)


def build_index(article_list):
    if os.path.exists("indexdir"):
        shutil.rmtree("indexdir")
    os.mkdir("indexdir")
    ix = create_in("indexdir", schema)
    writer = ix.writer()
    for article in article_list:
        writer.add_document(
            title=article.get("title", ""),
            author=article.get("author", ""),
            source=article.get("source", ""),
            year=article.get("year", 0),
            month=article.get("month", 0),
            content=article.get("full_text", ""),
            link=article.get("link", "")
        )
    writer.commit()
    return ix


def index_is_stale():
    if not os.path.exists("indexdir"):
        return True
    if not os.path.exists(DB_PATH):
        return False
    return os.path.getmtime(DB_PATH) > os.path.getmtime("indexdir")


if index_is_stale():
    print(f"DEBUG: Building search index with {len(articles)} articles...")
    ix = build_index(articles)
    print(f"DEBUG: Index built successfully.")
else:
    ix = open_dir("indexdir")
    with ix.searcher() as s:
        print(f"DEBUG: Index loaded from disk — {s.doc_count()} documents.")

# Fast lookup: link → article dict (for tags + first-sentence fallback)
link_to_article = {a["link"]: a for a in articles}

# ── 3. HELPERS ───────────────────────────────────────────────────────────────

def first_sentences(text: str, n: int = 2) -> str:
    """Return the first n sentences of text as a fallback snippet."""
    if not text:
        return ""
    sentences = []
    for part in text.replace("\n", " ").split(". "):
        part = part.strip()
        if part:
            sentences.append(part)
        if len(sentences) >= n:
            break
    return ". ".join(sentences) + ("." if sentences else "")


# ── 4. ROUTES ────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/search")
@limiter.limit("60/minute")
def search():
    raw_query = request.args.get("q", "").strip()
    author    = request.args.get("author", "").strip()
    year      = request.args.get("year", "").strip()
    month     = request.args.get("month", "").strip()
    source    = request.args.get("source", "").strip()
    tags      = request.args.getlist("tags")
    sort_by   = request.args.get("sort", "relevance")   # relevance | newest | oldest
    page      = max(1, int(request.args.get("page", 1)))
    per_page  = 20

    results_list = []

    with ix.searcher() as searcher:
        # Build Whoosh query
        if raw_query:
            try:
                parser = MultifieldParser(["title", "content"], schema=ix.schema)
                safe_q = raw_query.replace("*", "").replace("?", "").replace("~", "")
                q = parser.parse(safe_q)
            except Exception:
                q = whoosh_query.Term("content", raw_query)
        else:
            q = whoosh_query.Every()

        # Sorting
        if sort_by == "newest":
            sortedby = [FieldFacet("year", reverse=True), FieldFacet("month", reverse=True)]
        elif sort_by == "oldest":
            sortedby = [FieldFacet("year"), FieldFacet("month")]
        else:
            sortedby = None   # default: relevance

        results = searcher.search(q, limit=None, sortedby=sortedby)

        # Apply metadata filters
        filtered = []
        for r in results:
            article = link_to_article.get(r["link"], {})
            if source and article.get("source") != source:
                continue
            if author and article.get("author") != author:
                continue
            if year and str(article.get("year", "")) != year:
                continue
            if month and str(article.get("month", "")) != month:
                continue
            if tags and not any(t in article.get("tags", []) for t in tags):
                continue

            # Snippet: Whoosh highlight or first sentences
            snippet = r.highlights("content") if raw_query else ""
            if not snippet:
                snippet = first_sentences(article.get("full_text", ""), n=2)

            filtered.append({
                "title":   str(escape(r["title"])),
                "author":  str(escape(r["author"])),
                "year":    r["year"],
                "month":   r["month"],
                "day":     article.get("day", 0),
                "source":  str(escape(r["source"])),
                "link":    str(escape(r["link"])),
                "snippet": snippet,
                "tags":    article.get("tags", []),
            })

        total = len(filtered)
        start = (page - 1) * per_page
        results_list = filtered[start: start + per_page]

    return jsonify({
        "results":    results_list,
        "total":      total,
        "page":       page,
        "per_page":   per_page,
        "total_pages": max(1, -(-total // per_page)),   # ceil division
    })


@app.route("/filters")
@limiter.limit("30/minute")
def filters():
    selected_source = request.args.get("source", "").strip()
    selected_author = request.args.get("author", "").strip()
    selected_year   = request.args.get("year",   "").strip()
    selected_month  = request.args.get("month",  "").strip()
    selected_tags   = request.args.getlist("tags")

    opts = get_filter_options(
        selected_source, selected_author,
        selected_year, selected_month, selected_tags
    )

    tag_counts = opts["tag_counts"]
    all_tags = [
        {
            "name":      cat,
            "available": cat in tag_counts,
            "count":     tag_counts.get(cat, 0),
        }
        for cat in ALL_CATEGORY_NAMES
    ]

    return jsonify({
        "sources": opts["sources"],
        "authors": opts["authors"],
        "years":   opts["years"],
        "months":  opts["months"],
        "tags":    all_tags,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)