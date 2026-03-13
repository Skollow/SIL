from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from whoosh.index import open_dir
from whoosh.qparser import MultifieldParser
from werkzeug.security import check_password_hash
import json

ix = open_dir("indexdir")

app = Flask(__name__)
app.secret_key = "secretkey123"

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

with open("configs/articles.json", "r", encoding="utf-8") as f:
    articles = json.load(f)

with open("configs/users.json","r",encoding="utf-8") as f:
    users=json.load(f)

class User(UserMixin):
    def __init__(self,id,username,password):
        self.id=id
        self.username=username
        self.password=password
        
@login_manager.user_loader
def load_user(user_id):
    for u in users:
        if str(u["id"]) == str(user_id):
            return User(u["id"],u["username"],u["password"])
    return None

@app.route("/login", methods=["GET","POST"])
def login():

    if request.method=="POST":

        username=request.form["username"]
        password=request.form["password"]

        for u in users:
            if u["username"] == username and check_password_hash(u["password"], password):  
                user=User(u["id"],u["username"],u["password"])
                login_user(user)

                return redirect("/")

    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():

    logout_user()
    return redirect("/login")

@app.route("/")
@login_required
def index():
    return render_template("index.html")

@app.route("/search")
@login_required
def search():

    query = request.args.get("q","")

    author = request.args.get("author")
    year = request.args.get("year")
    month = request.args.get("month")
    source = request.args.get("source")

    results_list = []

    with ix.searcher() as searcher:

        parser = MultifieldParser(["title","content"], schema=ix.schema)
        q = parser.parse(query)

        results = searcher.search(q, limit=50)

        for r in results:

            if author and r["author"] != author:
                continue

            if year and str(r["year"]) != year:
                continue

            if month and str(r["month"]) != month:
                continue

            if source and r["source"] != source:
                continue

            snippet = r.highlights("content")

            results_list.append({
                "title": r["title"],
                "author": r["author"],
                "year": r["year"],
                "month": r["month"],
                "source": r["source"],
                "link": r["link"],
                "snippet": snippet
            })

    return jsonify(results_list)

@app.route("/filters")
def filters():

    authors = sorted(set(a["author"] for a in articles))
    years = sorted(set(a["year"] for a in articles))
    months = sorted(set(a["month"] for a in articles))
    sources = sorted(set(a["source"] for a in articles))

    return jsonify({
        "authors": authors,
        "years": years,
        "months": months,
        "sources": sources
    })


if __name__ == "__main__":
    app.run(debug=True)