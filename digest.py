import json
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import requests

from config import (
    EMAIL_ENABLED,
    NYT_API_KEY,
    OLLAMA_MODEL,
    OLLAMA_PARALLEL_WORKERS,
    OLLAMA_URL,
    SECTION_KEYWORDS,
    SECTIONS,
)
from email_digest import build_html, send_digest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")


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


def summarize(article):
    """Summarize a single article using Ollama."""
    prompt = (
        "Summarize the key facts in 1-2 sentences. "
        "Do NOT start with phrases like 'Here is a summary' or 'Here are the key facts'. "
        "Do NOT restate the headline. Add context or details beyond what the title already says. "
        "Jump straight into the substance.\n\n"
        f"Headline: {article['title']}\n"
        f"Abstract: {article['abstract']}"
    )
    url = f"{OLLAMA_URL}/api/generate"
    try:
        resp = requests.post(
            url,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except requests.ConnectionError:
        logging.error(f"Cannot connect to Ollama at {OLLAMA_URL} — is 'ollama serve' running?")
        raise
    except requests.Timeout:
        logging.error(f"Ollama request timed out for: {article['title'][:60]}")
        raise
    except Exception as e:
        logging.error(f"Ollama error: {e}")
        raise



def load_previous_day(today):
    """Load yesterday's summaries if they exist."""
    yesterday = today - timedelta(days=1)
    path = os.path.join(DATA_DIR, f"{yesterday.strftime('%Y-%m-%d')}.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


def diff_news(today_summaries, yesterday_summaries):
    """Ask Ollama what's genuinely new compared to yesterday."""
    yesterday_text = "\n".join(
        f"- [{s['section']}] {s['title']}: {s['summary']}"
        for s in yesterday_summaries
    )
    today_text = "\n".join(
        f"- [{s['section']}] {s['title']}: {s['summary']}"
        for s in today_summaries
    )

    prompt = (
        "Given yesterday's news and today's news, what is genuinely new information today? "
        "List only new facts, grouped by section. Be concise.\n\n"
        f"YESTERDAY:\n{yesterday_text}\n\n"
        f"TODAY:\n{today_text}"
    )

    resp = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
    )
    resp.raise_for_status()
    return resp.json().get("response", "").strip()


def write_markdown(today, summaries_by_section, diff_text):
    """Write the daily digest as a markdown file."""
    date_str = today.strftime("%Y-%m-%d")
    lines = [f"# News Digest — {date_str}\n"]

    if diff_text:
        lines.append("## What's New Today\n")
        lines.append(diff_text + "\n")

    lines.append("## Full Summaries\n")
    for section, articles in summaries_by_section.items():
        lines.append(f"### {section.title()}\n")
        for a in articles:
            lines.append(f"**[{a['title']}]({a['url']})**\n")
            lines.append(f"{a['summary']}\n")

    path = os.path.join(OUTPUT_DIR, f"{date_str}.md")
    with open(path, "w") as f:
        f.write("\n".join(lines))
    return path


def main():
    if not NYT_API_KEY or NYT_API_KEY == "your-key-here":
        logging.error("Set your NYT_API_KEY in .env first.")
        sys.exit(1)

    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")

    # Step A: Fetch articles
    all_articles = []
    for section in SECTIONS:
        logging.info(f"Fetching {section}...")
        try:
            articles = fetch_articles(section)
            logging.info(f"  {len(articles)} articles from {section}")
            all_articles.extend(articles)
        except Exception as e:
            logging.error(f"Failed to fetch {section}: {e}")
            continue

    if not all_articles:
        logging.error("No articles found.")
        sys.exit(1)

    # Deduplicate against yesterday
    yesterday_data = load_previous_day(today)
    if yesterday_data:
        yesterday_urls = {a["url"] for a in yesterday_data}
        before = len(all_articles)
        all_articles = [a for a in all_articles if a["url"] not in yesterday_urls]
        dupes = before - len(all_articles)
        if dupes:
            logging.info(f"Removed {dupes} articles already in yesterday's digest")

    # Step B: Summarize
    total = len(all_articles)
    summaries = []

    if total > 20:
        logging.info(f"Summarizing {total} articles with {OLLAMA_PARALLEL_WORKERS} workers...")
        results = [None] * total

        def _summarize(idx, article):
            logging.info(f"Summarizing [{idx+1}/{total}] {article['title'][:60]}...")
            summary = summarize(article)
            return idx, {**article, "summary": summary}

        with ThreadPoolExecutor(max_workers=OLLAMA_PARALLEL_WORKERS) as pool:
            futures = {pool.submit(_summarize, i, a): i for i, a in enumerate(all_articles)}
            for future in as_completed(futures):
                try:
                    idx, result = future.result()
                    results[idx] = result
                except Exception as e:
                    idx = futures[future]
                    logging.error(f"Skipping article: {all_articles[idx]['title'][:60]} — {e}")

        summaries = [s for s in results if s is not None]
    else:
        for i, article in enumerate(all_articles):
            logging.info(f"Summarizing [{i+1}/{total}] {article['title'][:60]}...")
            try:
                summary = summarize(article)
                summaries.append({**article, "summary": summary})
            except Exception as e:
                logging.error(f"Skipping article: {article['title'][:60]} — {e}")
                continue

    # Step C: Diff against yesterday
    diff_text = None
    if yesterday_data:
        logging.info("Diffing against yesterday...")
        diff_text = diff_news(summaries, yesterday_data)
    else:
        logging.info("No previous day data — showing all summaries.")

    # Step D: Output
    summaries_by_section = {}
    for s in summaries:
        summaries_by_section.setdefault(s["section"], []).append(s)

    path = write_markdown(today, summaries_by_section, diff_text)
    logging.info(f"Digest written to {path}")

    # Step E: Email digest
    if EMAIL_ENABLED:
        try:
            html = build_html(summaries_by_section, diff_text, date_str)
            send_digest(html, date_str)
        except Exception as e:
            logging.error(f"Failed to send digest email: {e}")

    # Save today's data for tomorrow's diff
    data_path = os.path.join(DATA_DIR, f"{date_str}.json")
    with open(data_path, "w") as f:
        json.dump(summaries, f, indent=2)
    logging.info(f"Data saved to {data_path}")


if __name__ == "__main__":
    main()
