import json
import os
import re
import time
from datetime import datetime

import markdown
from flask import Flask, redirect, render_template, abort
from markupsafe import Markup
from config import DATA_DIR, SECTION_ORDER
from markets import fetch_markets

app = Flask(__name__)


@app.template_filter("md")
def md_filter(text):
    """Render markdown string as HTML."""
    return Markup(markdown.markdown(text))


@app.template_filter("friendly_date")
def friendly_date_filter(text):
    """Convert '2026-03-25T...' or '2026-03-25' to '25 March 2026'."""
    try:
        dt = datetime.fromisoformat(text[:10])
        return f"{dt.day} {dt.strftime('%B %Y')}"
    except (ValueError, TypeError):
        return text



def get_available_dates():
    """Scan data/ dir, return sorted list of date strings."""
    dates = []
    for f in os.listdir(DATA_DIR):
        if f.endswith(".json"):
            dates.append(f.removesuffix(".json"))
    dates.sort()
    return dates


def load_digest(date):
    """Read and return (articles, markets) from data/<date>.json."""
    path = os.path.join(DATA_DIR, f"{date}.json")
    if not os.path.exists(path):
        return None, {}
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, dict) and "articles" in data:
        return data["articles"], data.get("markets", {})
    return data, {}


def get_prev_next(date):
    """Return (prev_date, next_date) or None for each."""
    dates = get_available_dates()
    if date not in dates:
        return None, None
    idx = dates.index(date)
    prev_date = dates[idx - 1] if idx > 0 else None
    next_date = dates[idx + 1] if idx < len(dates) - 1 else None
    return prev_date, next_date



MARKET_CACHE = {"data": {}, "ts": 0}
MARKET_CACHE_TTL = 300  # 5 minutes


def get_live_markets():
    """Fetch market data with a 5-minute cache."""
    now = time.time()
    if now - MARKET_CACHE["ts"] < MARKET_CACHE_TTL and MARKET_CACHE["data"]:
        return MARKET_CACHE["data"]
    try:
        data = fetch_markets()
        MARKET_CACHE["data"] = data
        MARKET_CACHE["ts"] = now
        return data
    except Exception:
        return MARKET_CACHE["data"]




def group_by_section(articles):
    """Group articles by section, preserving a sensible order."""
    groups = {}
    for article in articles:
        section = article.get("section", "other").lower()
        groups.setdefault(section, []).append(article)
    ordered = []
    for s in SECTION_ORDER:
        if s in groups:
            ordered.append((s, groups.pop(s)))
    for s in sorted(groups):
        ordered.append((s, groups[s]))
    return ordered


@app.route("/")
def index():
    dates = get_available_dates()
    if not dates:
        return "No digests available yet.", 404
    return redirect(f"/digest/{dates[-1]}")


@app.route("/digest/<date>")
def digest(date):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        abort(404)
    articles, _ = load_digest(date)
    if articles is None:
        abort(404)
    prev_date, next_date = get_prev_next(date)
    sections = group_by_section(articles)
    total_count = sum(len(arts) for _, arts in sections)
    markets = get_live_markets()
    # Collect unique tags across all articles
    all_tags = sorted({tag for a in articles for tag in a.get("tags", [])})
    # Collect unique sources, cleaned up for display
    def _clean_source(s):
        return s.replace("rss:", "").replace("top_stories", "NYT").replace("search", "NYT Search")
    all_sources = sorted({_clean_source(a.get("source", "")) for a in articles} - {""})
    return render_template(
        "digest.html",
        date=date,
        sections=sections,
        all_tags=all_tags,
        all_sources=all_sources,
        markets=markets,
        total_count=total_count,
        prev_date=prev_date,
        next_date=next_date,
        active_tab="digest",
    )


if __name__ == "__main__":
    app.run(debug=True, port=5050)
