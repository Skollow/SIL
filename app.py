from flask import Flask, render_template, request, jsonify
from whoosh.index import create_in, open_dir
from whoosh.qparser import MultifieldParser
from whoosh.fields import Schema, TEXT, NUMERIC, ID
from whoosh import query as whoosh_query
from src.scrape_ejil_talk import run_scrape_ejil
from src.scrape_just_security import run_scrape_just
from src.scrape_lieber_westpoint import run_scrape_lieber
from markupsafe import escape
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from src.categories import assign_categories, ALL_CATEGORY_NAMES
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(32))

# Rate limiting
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["300/day", "60/minute"]
)

# ------------------------
# 1. LOAD ARTICLES
# ------------------------

def load_articles():
    articles = []
    for scraper in [run_scrape_ejil, run_scrape_just, run_scrape_lieber]:
        try:
            articles += scraper()
        except Exception as e:
            print(f"Scraper error: {e}")

    # Assign tags to every article (in-memory, no file change needed)
    for article in articles:
        if "tags" not in article:
            article["tags"] = assign_categories(article)

    return articles

articles = load_articles()

# ------------------------
# 2. BUILD SEARCH INDEX
# ------------------------

schema = Schema(
    title=TEXT(stored=True),
    author=TEXT(stored=True),
    source=TEXT(stored=True),
    year=NUMERIC(stored=True),
    month=NUMERIC(stored=True),
    content=TEXT(stored=True),
    link=ID(stored=True)
)

def build_index(articles):
    """בונה את האינדקס מאפס."""
    import shutil
    if os.path.exists("indexdir"):
        shutil.rmtree("indexdir")
    os.mkdir("indexdir")
    ix = create_in("indexdir", schema)
    writer = ix.writer()
    for article in articles:
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

# בדוק אם האינדקס קיים ומעודכן לפי מספר המאמרים
ARTICLES_FILE = "configs/articles.json"

def index_is_stale():
    """מחזיר True אם האינדקס לא קיים או שה-JSON עודכן אחריו."""
    if not os.path.exists("indexdir"):
        return True
    if not os.path.exists(ARTICLES_FILE):
        return False
    index_mtime = os.path.getmtime("indexdir")
    json_mtime   = os.path.getmtime(ARTICLES_FILE)
    return json_mtime > index_mtime

if index_is_stale():
    print("Building search index...")
    ix = build_index(articles)
    print(f"Index built with {len(articles)} articles.")
else:
    ix = open_dir("indexdir")
    print(f"Index loaded ({len(articles)} articles in JSON).")

# Build a quick lookup: link → article (for tag retrieval after Whoosh search)
link_to_article = {a["link"]: a for a in articles}

# ------------------------
# 3. HELPERS
# ------------------------

def article_matches_filters(article, source, author, year, month, tags):
    """Check all active filters against a plain article dict."""
    if source and article.get("source") != source:
        return False
    if author and article.get("author") != author:
        return False
    if year and str(article.get("year", "")) != year:
        return False
    if month and str(article.get("month", "")) != month:
        return False
    if tags:
        article_tags = article.get("tags", [])
        if not any(t in article_tags for t in tags):
            return False
    return True

# ------------------------
# 4. ROUTES
# ------------------------

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
    tags      = request.args.getlist("tags")   # e.g. ?tags=Cyber&tags=IHL

    # If nothing is provided, return empty
    if not raw_query and not author and not year and not month and not source and not tags:
        return jsonify([])

    results_list = []

    with ix.searcher() as searcher:
        if raw_query:
            try:
                parser = MultifieldParser(["title", "content"], schema=ix.schema)
                safe_query = raw_query.replace("*", "").replace("?", "").replace("~", "")
                q = parser.parse(safe_query)
            except Exception:
                q = whoosh_query.Term("content", raw_query)
        else:
            q = whoosh_query.Every()

        results = searcher.search(q, limit=200)

        for r in results:
            article = link_to_article.get(r["link"], {})

            if not article_matches_filters(article, source, author, year, month, tags):
                continue

            snippet = r.highlights("content") if raw_query else ""

            results_list.append({
                "title":   str(escape(r["title"])),
                "author":  str(escape(r["author"])),
                "year":    r["year"],
                "month":   r["month"],
                "source":  str(escape(r["source"])),
                "link":    str(escape(r["link"])),
                "snippet": snippet,
                "tags":    article.get("tags", [])
            })

    return jsonify(results_list)


@app.route("/filters")
@limiter.limit("30/minute")
def filters():
    """
    Returns filter options consistent with the current selection.
    Each filter is computed excluding itself, so all its own options stay visible.
    """
    selected_source = request.args.get("source", "").strip()
    selected_author = request.args.get("author", "").strip()
    selected_year   = request.args.get("year", "").strip()
    selected_month  = request.args.get("month", "").strip()
    selected_tags   = request.args.getlist("tags")

    def base(exclude=None):
        """All articles filtered by every active filter EXCEPT the excluded one."""
        result = articles
        if exclude != "source" and selected_source:
            result = [a for a in result if a.get("source") == selected_source]
        if exclude != "author" and selected_author:
            result = [a for a in result if a.get("author") == selected_author]
        if exclude != "year" and selected_year:
            result = [a for a in result if str(a.get("year", "")) == selected_year]
        if exclude != "month" and selected_month:
            result = [a for a in result if str(a.get("month", "")) == selected_month]
        if exclude != "tags" and selected_tags:
            result = [a for a in result
                      if any(t in a.get("tags", []) for t in selected_tags)]
        return result

    sources = sorted(set(a["source"] for a in base(exclude="source")))
    authors = sorted(set(a["author"] for a in base(exclude="author")))
    years   = sorted(set(a["year"]   for a in base(exclude="year")))
    months  = sorted(set(a["month"]  for a in base(exclude="month")))

    # Tags: always show all defined categories; mark which have results
    available_tags = set(
        tag
        for a in base(exclude="tags")
        for tag in a.get("tags", [])
    )
    all_tags = [
        {"name": cat, "available": cat in available_tags}
        for cat in ALL_CATEGORY_NAMES
    ]

    return jsonify({
        "sources": sources,
        "authors": authors,
        "years":   years,
        "months":  months,
        "tags":    all_tags
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)