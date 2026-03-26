import logging
from datetime import datetime, timezone
from time import mktime

import feedparser

from config import RSS_FEEDS


def fetch_rss_articles():
    """Fetch articles from all configured RSS feeds."""
    articles = []
    for feed_url, default_section in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            if feed.bozo and not feed.entries:
                logging.warning(f"RSS feed failed: {feed_url} — {feed.bozo_exception}")
                continue
            count = 0
            for entry in feed.entries:
                published = ""
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    dt = datetime.fromtimestamp(mktime(entry.published_parsed), tz=timezone.utc)
                    published = dt.isoformat()
                elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    dt = datetime.fromtimestamp(mktime(entry.updated_parsed), tz=timezone.utc)
                    published = dt.isoformat()

                articles.append({
                    "title": entry.get("title", ""),
                    "abstract": entry.get("summary", ""),
                    "url": entry.get("link", ""),
                    "section": default_section,
                    "published": published,
                    "source": f"rss:{feed.feed.get('title', feed_url)[:40]}",
                })
                count += 1
            logging.info(f"  {count} articles from {feed_url}")
        except Exception as e:
            logging.error(f"RSS fetch failed for {feed_url}: {e}")
    return articles
