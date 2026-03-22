# News Digest

A local news digest tool that fetches NYT articles, tags and priority-scores them with Ollama (Llama 3), and presents them in a filterable web UI — sorted by significance, not just recency. Includes market data, tag-based filtering, and email delivery.

![Light mode](screenshots/digest-light.png)

<details>
<summary>Dark mode & article modal</summary>

![Dark mode](screenshots/digest-dark.png)
![Article modal](screenshots/modal.png)

</details>

## Setup

1. Install dependencies:
   ```bash
   git clone https://github.com/srimanokaran/news-digest.git
   cd news-digest
   python3 -m venv .venv
   source .venv/bin/activate
   pip install requests python-dotenv yfinance
   ```

2. Add your NYT API key:
   ```bash
   cp .env.example .env
   # Edit .env with your key from https://developer.nytimes.com
   ```

3. Install and run Ollama with Llama 3:
   ```bash
   ollama pull llama3
   ollama serve
   ```

## Usage

```bash
python digest.py
```

Each article is tagged (from a fixed set of 15 topics like AI, Markets, Conflict) and priority-scored 1-5 by Ollama. Articles are deduplicated against the previous day. Output goes to `output/YYYY-MM-DD.md` and `data/YYYY-MM-DD.json`.

### Web UI

```bash
pip install flask markdown
python app.py
# Open http://localhost:5050
```

Features: section filtering, tag filtering, priority sorting (P4-5 get accent borders), read tracking, bookmarks, search, dark mode, article modal.

### Email Digest

Set these in `.env` to receive a daily email:
```
EMAIL_ENABLED=true
GMAIL_ADDRESS=you@gmail.com
GMAIL_APP_PASSWORD=your-app-password
DIGEST_EMAIL_TO=recipient@example.com
```

## Configuration

Edit `config.py` to change:
- Sections to follow (default: technology, business, world, opinion)
- Keywords to filter articles per section
- Ollama model (`OLLAMA_MODEL`)
- Allowed tags (`ALLOWED_TAGS`) — the fixed set of tags the model can assign
- Market indices and sector ETFs
