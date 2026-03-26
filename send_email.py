"""Send the digest email for a given date using existing data."""
import json
import logging
import os
import sys
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)

from config import DATA_DIR
from email_digest import build_html, send_digest


def main():
    date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y-%m-%d")
    data_path = os.path.join(DATA_DIR, f"{date_str}.json")

    if not os.path.exists(data_path):
        logging.error(f"No data for {date_str} at {data_path}")
        sys.exit(1)

    with open(data_path) as f:
        data = json.load(f)

    if isinstance(data, dict) and "articles" in data:
        articles = data["articles"]
    else:
        articles = data

    articles_by_section = {}
    for a in articles:
        articles_by_section.setdefault(a["section"], []).append(a)

    html = build_html(articles_by_section, date_str)
    send_digest(html, date_str)


if __name__ == "__main__":
    main()
