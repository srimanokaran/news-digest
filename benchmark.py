"""Benchmark sequential vs parallel summarization using the same articles."""

import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import OLLAMA_PARALLEL_WORKERS
from digest import fetch_articles, summarize

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)

SECTIONS = ["technology", "business"]  # just 2 sections to keep it short


def run_sequential(articles):
    n = len(articles)
    for i, article in enumerate(articles):
        logging.info(f"  [{i+1}/{n}] {article['title'][:50]}...")
        summarize(article)


def run_parallel(articles, workers):
    n = len(articles)

    def _summarize(idx, article):
        logging.info(f"  [{idx+1}/{n}] {article['title'][:50]}...")
        return idx, summarize(article)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_summarize, i, a): i for i, a in enumerate(articles)}
        for future in as_completed(futures):
            future.result()


def main():
    # Fetch a batch of articles
    all_articles = []
    for section in SECTIONS:
        all_articles.extend(fetch_articles(section))

    n = len(all_articles)
    logging.info(f"Benchmarking with {n} articles\n")

    # Sequential
    logging.info("--- Sequential ---")
    start = time.time()
    run_sequential(all_articles)
    seq_time = time.time() - start
    logging.info(f"Sequential: {seq_time:.1f}s ({seq_time/n:.1f}s per article)\n")

    # Parallel
    workers = OLLAMA_PARALLEL_WORKERS
    logging.info(f"--- Parallel ({workers} workers) ---")
    start = time.time()
    run_parallel(all_articles, workers)
    par_time = time.time() - start
    logging.info(f"Parallel:   {par_time:.1f}s ({par_time/n:.1f}s per article)\n")

    # Results
    speedup = seq_time / par_time if par_time > 0 else 0
    logging.info(f"Speedup: {speedup:.2f}x")
    if speedup < 1.2:
        logging.warning(
            "Minimal speedup — make sure Ollama is started with "
            f"OLLAMA_NUM_PARALLEL={workers}"
        )


if __name__ == "__main__":
    main()
