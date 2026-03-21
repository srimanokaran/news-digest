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

from email_digest import build_html, send_digest

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def main():
    date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y-%m-%d")
    data_path = os.path.join(DATA_DIR, f"{date_str}.json")

    if not os.path.exists(data_path):
        logging.error(f"No data for {date_str} at {data_path}")
        sys.exit(1)

    with open(data_path) as f:
        summaries = json.load(f)

    summaries_by_section = {}
    for s in summaries:
        summaries_by_section.setdefault(s["section"], []).append(s)

    html = build_html(summaries_by_section, None, date_str)
    send_digest(html, date_str)


if __name__ == "__main__":
    main()
