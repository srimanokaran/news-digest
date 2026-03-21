import json
import os
import re
import markdown
from flask import Flask, redirect, render_template, abort
from markupsafe import Markup

app = Flask(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")


def get_available_dates():
    """Scan data/ dir, return sorted list of date strings."""
    dates = []
    for f in os.listdir(DATA_DIR):
        if f.endswith(".json"):
            dates.append(f.removesuffix(".json"))
    dates.sort()
    return dates


def load_digest(date):
    """Read and return parsed JSON from data/<date>.json."""
    path = os.path.join(DATA_DIR, f"{date}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def get_prev_next(date):
    """Return (prev_date, next_date) or None for each."""
    dates = get_available_dates()
    if date not in dates:
        return None, None
    idx = dates.index(date)
    prev_date = dates[idx - 1] if idx > 0 else None
    next_date = dates[idx + 1] if idx < len(dates) - 1 else None
    return prev_date, next_date


def load_diff_section(date):
    """Extract the 'What's New Today' section from output/<date>.md and render as HTML."""
    path = os.path.join(OUTPUT_DIR, f"{date}.md")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        content = f.read()
    # Look for a "What's New" style section header (match only within the header line)
    pattern = r"(?:^|\n)(## [^\n]*(?:What.?s New|New Today|Diff)[^\n]*\n)(.*?)(?=\n## |\Z)"
    match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
    if not match:
        return None
    md_text = (match.group(1) + match.group(2)).strip()
    return Markup(markdown.markdown(md_text))


SECTION_ORDER = ["technology", "business", "world", "opinion", "science", "health", "sports", "arts"]


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
    articles = load_digest(date)
    if articles is None:
        abort(404)
    prev_date, next_date = get_prev_next(date)
    sections = group_by_section(articles)
    total_count = sum(len(arts) for _, arts in sections)
    return render_template(
        "digest.html",
        date=date,
        sections=sections,
        total_count=total_count,
        prev_date=prev_date,
        next_date=next_date,
        active_tab="digest",
    )


@app.route("/diff/<date>")
def diff(date):
    dates = get_available_dates()
    if date not in dates:
        abort(404)
    prev_date, next_date = get_prev_next(date)
    diff_content = load_diff_section(date)
    return render_template(
        "diff.html",
        date=date,
        diff_content=diff_content,
        prev_date=prev_date,
        next_date=next_date,
        active_tab="diff",
    )


if __name__ == "__main__":
    app.run(debug=True, port=5050)
