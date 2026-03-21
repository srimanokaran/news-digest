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

# Email digest settings
EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "false").lower() in ("true", "1", "yes")
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
DIGEST_EMAIL_TO = os.getenv("DIGEST_EMAIL_TO", "")
