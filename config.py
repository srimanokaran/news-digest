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

MARKET_INDICES = {
    "S&P 500": "^GSPC",
    "Nasdaq": "^IXIC",
    "Dow": "^DJI",
}

SECTION_ETFS = {
    "technology": "XLK",
    "business": "SPY",
    "world": "EFA",
}

SEARCH_QUERIES = {
    "technology": "technology AI artificial intelligence",
    "business": "business",
    "world": "world",
    "opinion": "opinion",
}
SEARCH_PAGES = 3  # pages per section (10 articles each)

OLLAMA_MODEL = "llama3"
OLLAMA_URL = "http://localhost:11434"

ALLOWED_TAGS = [
    "AI", "Big Tech", "Startups", "Markets", "Economy",
    "Trade", "US Politics", "World", "Conflict", "Climate",
    "Energy", "Health", "Culture", "Media", "Opinion",
]

# Email digest settings
EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "false").lower() in ("true", "1", "yes")
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
DIGEST_EMAIL_TO = os.getenv("DIGEST_EMAIL_TO", "")
