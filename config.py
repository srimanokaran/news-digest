import os
from dotenv import load_dotenv

load_dotenv()

NYT_API_KEY = os.getenv("NYT_API_KEY")

SECTIONS = ["technology", "business", "world", "opinion"]

# Keywords to prioritize within sections (empty list = include all)
SECTION_KEYWORDS = {
    "technology": ["ai", "artificial intelligence", "machine learning", "openai", "google", "apple", "microsoft"],
    "world": ["politics", "election", "war", "conflict", "diplomacy", "summit", "sanctions"],
    "business": [],
    "opinion": [],
}

OLLAMA_MODEL = "llama3"
OLLAMA_URL = "http://localhost:11434"
OLLAMA_PARALLEL_WORKERS = 4
