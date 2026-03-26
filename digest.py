import json
import logging
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

import requests

from config import (
    ALLOWED_TAGS,
    DATA_DIR,
    EMAIL_ENABLED,
    FRESHNESS_CUTOFF_HOURS,
    MARKET_INDICES,
    NYT_API_KEY,
    OLLAMA_MODEL,
    OLLAMA_URL,
    OUTPUT_DIR,
    SEARCH_PAGES,
    SEARCH_QUERIES,
    SECTION_ETFS,
    SECTION_KEYWORDS,
    SECTIONS,
)
from email_digest import build_html, send_digest
from rss import fetch_rss_articles

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)



def fetch_articles(section):
    """Fetch top stories from NYT for a given section."""
    url = f"https://api.nytimes.com/svc/topstories/v2/{section}.json"
    logging.info(f"GET {url}")
    resp = requests.get(url, params={"api-key": NYT_API_KEY}, timeout=30)
    logging.info(f"NYT response: {resp.status_code}")
    if resp.status_code != 200:
        logging.error(f"NYT API error: {resp.status_code} — {resp.text[:500]}")
    resp.raise_for_status()

    articles = []
    keywords = SECTION_KEYWORDS.get(section, [])

    for item in resp.json().get("results", []):
        title = item.get("title", "")
        abstract = item.get("abstract", "")
        article = {
            "title": title,
            "abstract": abstract,
            "url": item.get("url", ""),
            "section": section,
            "published": item.get("published_date", ""),
        }

        if keywords:
            text = f"{title} {abstract}".lower()
            if any(kw in text for kw in keywords):
                articles.append(article)
        else:
            articles.append(article)

    return articles


def fetch_search_articles(section, today):
    """Fetch articles from NYT Article Search API for a given section."""
    search_query = SEARCH_QUERIES.get(section)
    if not search_query:
        logging.warning(f"No Article Search query for section: {section}")
        return []

    base_url = "https://api.nytimes.com/svc/search/v2/articlesearch.json"
    begin_date = (today - timedelta(days=1)).strftime("%Y%m%d")
    keywords = SECTION_KEYWORDS.get(section, [])
    articles = []

    for page in range(SEARCH_PAGES):
        params = {
            "api-key": NYT_API_KEY,
            "q": search_query,
            "begin_date": begin_date,
            "sort": "newest",
            "page": page,
        }
        logging.info(f"GET Article Search: {section} page {page}")
        try:
            resp = requests.get(base_url, params=params, timeout=30)
            logging.info(f"Article Search response: {resp.status_code}")
            if resp.status_code != 200:
                logging.error(f"Article Search API error: {resp.status_code} — {resp.text[:500]}")
                break
            resp.raise_for_status()
        except Exception as e:
            logging.error(f"Article Search request failed: {e}")
            break

        docs = resp.json().get("response", {}).get("docs", [])
        if not docs:
            break

        for doc in docs:
            title = doc.get("headline", {}).get("main", "")
            abstract = doc.get("abstract", "")
            article = {
                "title": title,
                "abstract": abstract,
                "url": doc.get("web_url", ""),
                "section": section,
                "published": doc.get("pub_date", ""),
                "source": "search",
            }

            if keywords:
                text = f"{title} {abstract}".lower()
                if any(kw in text for kw in keywords):
                    articles.append(article)
            else:
                articles.append(article)

        # Rate limit: NYT allows ~5 req/min on free tier
        time.sleep(6)

    return articles


SCORE_BATCH_SIZE = 15


def _score_batch(batch):
    """Score a single batch of articles via Ollama. Returns {url: {tags, priority}}."""
    article_list = [
        {"url": a["url"], "title": a["title"], "abstract": a["abstract"]}
        for a in batch
    ]
    tags_str = ", ".join(ALLOWED_TAGS)
    prompt = (
        "You are a news analyst. For each article below, assign:\n"
        f"- tags: 1-3 tags from this list ONLY: [{tags_str}]\n"
        "- priority: 1-5 (1=routine, 5=breaking/high-impact)\n\n"
        "Return ONLY a JSON array, one object per article, with keys: url, tags, priority.\n"
        "No markdown fences. No commentary before or after the JSON.\n\n"
        f"{json.dumps(article_list)}"
    )
    resp = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
        timeout=180,
    )
    resp.raise_for_status()
    raw = resp.json().get("response", "").strip()
    if not raw:
        logging.warning("Ollama returned empty response for batch")
        return {}
    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()
    # Try to extract JSON array if there's text around it
    start = raw.find("[")
    end = raw.rfind("]")
    if start != -1 and end != -1:
        raw = raw[start:end + 1]
    scored = json.loads(raw)
    return {item["url"]: item for item in scored}


def score_articles(articles):
    """Tag and priority-score all articles via Ollama in batches."""
    score_map = {}
    for i in range(0, len(articles), SCORE_BATCH_SIZE):
        batch = articles[i:i + SCORE_BATCH_SIZE]
        batch_num = i // SCORE_BATCH_SIZE + 1
        total_batches = (len(articles) + SCORE_BATCH_SIZE - 1) // SCORE_BATCH_SIZE
        logging.info(f"  Scoring batch {batch_num}/{total_batches} ({len(batch)} articles)...")
        try:
            score_map.update(_score_batch(batch))
        except Exception as e:
            logging.error(f"  Batch {batch_num} failed: {e}")

    allowed_set = set(ALLOWED_TAGS)
    applied = 0
    for a in articles:
        match = score_map.get(a["url"])
        if match:
            a["tags"] = [t for t in match.get("tags", []) if t in allowed_set]
            a["priority"] = match.get("priority", 3)
            applied += 1
        else:
            a.setdefault("tags", [])
            a.setdefault("priority", 3)
            a["unscored"] = True
    logging.info(f"  Scored {applied}/{len(articles)} articles")



def load_previous_day(today):
    """Load yesterday's data if it exists. Handles both old and new formats."""
    yesterday = today - timedelta(days=1)
    path = os.path.join(DATA_DIR, f"{yesterday.strftime('%Y-%m-%d')}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, dict) and "articles" in data:
        return data
    return {"articles": data}


def dedupe_fuzzy(articles, threshold=0.8):
    """Remove near-duplicate articles by fuzzy title matching.

    When two articles have similar titles, keep the one that appeared first
    (earlier in the list = higher-priority source).
    """
    keep = []
    kept_titles = []
    for a in articles:
        title = a["title"].lower().strip()
        is_dupe = False
        for kt in kept_titles:
            if SequenceMatcher(None, title, kt).ratio() >= threshold:
                is_dupe = True
                break
        if not is_dupe:
            keep.append(a)
            kept_titles.append(title)
    removed = len(articles) - len(keep)
    if removed:
        logging.info(f"Fuzzy dedup removed {removed} near-duplicate articles")
    return keep


def write_markdown(today, articles_by_section):
    """Write the daily digest as a markdown file."""
    date_str = today.strftime("%Y-%m-%d")
    lines = [f"# News Digest — {date_str}\n"]

    for section, articles in articles_by_section.items():
        lines.append(f"### {section.title()}\n")
        for a in sorted(articles, key=lambda x: x.get("priority", 3), reverse=True):
            tags = ", ".join(a.get("tags", []))
            tag_str = f" [{tags}]" if tags else ""
            lines.append(f"- [{a['title']}]({a['url']}){tag_str} (P{a.get('priority', 3)})")
        lines.append("")

    path = os.path.join(OUTPUT_DIR, f"{date_str}.md")
    with open(path, "w") as f:
        f.write("\n".join(lines))
    return path


def fetch_markets():
    """Fetch daily % change for market indices and sector ETFs."""
    import yfinance as yf

    results = {"indices": {}, "sectors": {}}

    all_tickers = {**{name: ticker for name, ticker in MARKET_INDICES.items()},
                   **{section: ticker for section, ticker in SECTION_ETFS.items()}}

    for name, ticker in all_tickers.items():
        try:
            hist = yf.Ticker(ticker).history(period="2d")
            if len(hist) >= 2:
                prev_close = float(hist["Close"].iloc[-2])
                last_close = float(hist["Close"].iloc[-1])
                change_pct = round((last_close - prev_close) / prev_close * 100, 2)
                entry = {
                    "ticker": ticker,
                    "close": round(last_close, 2),
                    "change_pct": change_pct,
                }
                if name in MARKET_INDICES:
                    results["indices"][name] = entry
                else:
                    results["sectors"][name] = entry
        except Exception as e:
            logging.error(f"Failed to fetch market data for {name} ({ticker}): {e}")

    return results


def _fetch_all_articles(today):
    """Fetch articles from all sources: NYT top stories, article search, RSS."""
    all_articles = []

    for section in SECTIONS:
        logging.info(f"Fetching top stories: {section}...")
        try:
            articles = fetch_articles(section)
            for a in articles:
                a["source"] = "top_stories"
            logging.info(f"  {len(articles)} articles from top stories/{section}")
            all_articles.extend(articles)
        except Exception as e:
            logging.error(f"Failed to fetch {section}: {e}")

    for section in SECTIONS:
        logging.info(f"Fetching article search: {section}...")
        try:
            search_arts = fetch_search_articles(section, today)
            logging.info(f"  {len(search_arts)} articles from search/{section}")
            all_articles.extend(search_arts)
        except Exception as e:
            logging.error(f"Failed to fetch search articles for {section}: {e}")

    logging.info("Fetching RSS feeds...")
    try:
        rss_articles = fetch_rss_articles()
        logging.info(f"Got {len(rss_articles)} articles from RSS feeds")
        all_articles.extend(rss_articles)
    except Exception as e:
        logging.error(f"Failed to fetch RSS articles: {e}")

    return all_articles


def _filter_articles(all_articles, today):
    """Apply freshness filter, URL dedup, fuzzy dedup, and yesterday dedup."""
    # Freshness
    cutoff = datetime.now(timezone.utc) - timedelta(hours=FRESHNESS_CUTOFF_HOURS)
    fresh = []
    for a in all_articles:
        pub = a.get("published", "")
        if not pub:
            fresh.append(a)
            continue
        try:
            dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt >= cutoff:
                fresh.append(a)
        except (ValueError, TypeError):
            fresh.append(a)
    stale = len(all_articles) - len(fresh)
    if stale:
        logging.info(f"Filtered {stale} stale articles (older than {FRESHNESS_CUTOFF_HOURS}h)")

    # URL dedup
    seen_urls = set()
    unique = []
    for a in fresh:
        if a["url"] not in seen_urls:
            seen_urls.add(a["url"])
            unique.append(a)
    url_dupes = len(fresh) - len(unique)
    if url_dupes:
        logging.info(f"Removed {url_dupes} duplicate articles across sources")

    if not unique:
        logging.error("No articles found.")
        sys.exit(1)

    # Fuzzy dedup
    unique = dedupe_fuzzy(unique)

    # Yesterday dedup
    yesterday_data = load_previous_day(today)
    if yesterday_data:
        yesterday_urls = {a["url"] for a in yesterday_data["articles"]}
        before = len(unique)
        unique = [a for a in unique if a["url"] not in yesterday_urls]
        dupes = before - len(unique)
        if dupes:
            logging.info(f"Removed {dupes} articles already in yesterday's digest")

    return unique


def _save_json(data, path):
    """Write JSON atomically: write to temp file, then rename."""
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def main():
    if not NYT_API_KEY or NYT_API_KEY == "your-key-here":
        logging.error("Set your NYT_API_KEY in .env first.")
        sys.exit(1)

    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")

    # Fetch
    logging.info("Fetching market data...")
    try:
        markets = fetch_markets()
        logging.info(f"Got {len(markets['indices'])} indices, {len(markets['sectors'])} sector ETFs")
    except Exception as e:
        logging.error(f"Failed to fetch market data: {e}")
        markets = {}

    all_articles = _fetch_all_articles(today)

    # Filter
    all_articles = _filter_articles(all_articles, today)

    # Score
    logging.info(f"Scoring {len(all_articles)} articles with Ollama...")
    score_articles(all_articles)
    all_articles.sort(key=lambda a: a.get("priority", 3), reverse=True)

    # Group + output
    articles_by_section = {}
    for a in all_articles:
        articles_by_section.setdefault(a["section"], []).append(a)

    path = write_markdown(today, articles_by_section)
    logging.info(f"Digest written to {path}")

    if EMAIL_ENABLED:
        try:
            html = build_html(articles_by_section, date_str)
            send_digest(html, date_str)
        except Exception as e:
            logging.error(f"Failed to send digest email: {e}")

    # Save (atomic write)
    payload = {"articles": all_articles}
    if markets:
        payload["markets"] = markets
    data_path = os.path.join(DATA_DIR, f"{date_str}.json")
    _save_json(payload, data_path)
    logging.info(f"Data saved to {data_path}")


if __name__ == "__main__":
    main()
