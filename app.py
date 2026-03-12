from flask import Flask, render_template, request, jsonify
import json

app = Flask(__name__)

with open("configs/articles.json", "r", encoding="utf-8") as f:
    articles = json.load(f)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/search")
def search():

    query = request.args.get("q", "").lower()
    author = request.args.get("author")
    source = request.args.get("source")

    results = []

    for article in articles:

        if query:
            if query not in article["title"].lower() and query not in article["full_text"].lower():
                continue

        if author and article["author"] != author:
            continue

        if source and article["source"] != source:
            continue

        results.append({
            "title": article["title"],
            "author": article["author"],
            "source": article["source"],
            "link": article["link"],
            "full_text": article["full_text"][:200] + "..."
        })

    return jsonify(results)


@app.route("/filters")
def filters():

    authors = sorted(set(a["author"] for a in articles))
    sources = sorted(set(a["source"] for a in articles))

    return jsonify({
        "authors": authors,
        "sources": sources
    })


if __name__ == "__main__":
    app.run(debug=True)