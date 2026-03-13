from whoosh.index import create_in
from whoosh.fields import *
import json
import os

schema = Schema(
    title=TEXT(stored=True),
    author=TEXT(stored=True),
    source=TEXT(stored=True),
    year=NUMERIC(stored=True),
    month=NUMERIC(stored=True),
    content=TEXT(stored=True),
    link=ID(stored=True)
)

if not os.path.exists("indexdir"):
    os.mkdir("indexdir")

ix = create_in("indexdir", schema)
writer = ix.writer()

with open("configs/articles.json", "r", encoding="utf-8") as f:
    articles = json.load(f)

for article in articles:

    writer.add_document(
        title=article["title"],
        author=article["author"],
        source=article["source"],
        year=article["year"],
        month=article["month"],
        content=article["full_text"],
        link=article["link"]
    )

writer.commit()

print("index built")