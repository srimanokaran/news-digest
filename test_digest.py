import json
import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

from digest import dedupe_fuzzy, _save_json, score_articles
from app import group_by_section, friendly_date_filter


# ── dedupe_fuzzy ──

def _article(title, url=None):
    return {"title": title, "url": url or f"https://example.com/{title[:10]}"}


class TestDedupeFuzzy:
    def test_keeps_unique_articles(self):
        articles = [_article("Fed Raises Rates"), _article("Apple Launches New iPhone")]
        result = dedupe_fuzzy(articles)
        assert len(result) == 2

    def test_removes_exact_duplicate_titles(self):
        articles = [_article("Fed Raises Rates", "url1"), _article("Fed Raises Rates", "url2")]
        result = dedupe_fuzzy(articles)
        assert len(result) == 1
        assert result[0]["url"] == "url1"  # keeps first

    def test_removes_near_duplicate_titles(self):
        articles = [
            _article("OpenAI Raises $10 Billion in New Funding Round"),
            _article("OpenAI Raises $10 Billion in Latest Funding Round"),
        ]
        result = dedupe_fuzzy(articles)
        assert len(result) == 1

    def test_keeps_similar_but_different_articles(self):
        articles = [_article("Fed Raises Rates"), _article("Fed Cuts Rates")]
        result = dedupe_fuzzy(articles)
        assert len(result) == 2

    def test_empty_list(self):
        assert dedupe_fuzzy([]) == []

    def test_single_article(self):
        articles = [_article("Hello World")]
        assert dedupe_fuzzy(articles) == articles

    def test_custom_threshold(self):
        articles = [
            _article("Breaking: Major earthquake hits Japan"),
            _article("Breaking: Major earthquake strikes Japan"),
        ]
        # Low threshold merges them
        assert len(dedupe_fuzzy(articles, threshold=0.5)) == 1
        # Very high threshold keeps both
        assert len(dedupe_fuzzy(articles, threshold=0.99)) == 2


# ── group_by_section ──

class TestGroupBySection:
    def test_groups_articles(self):
        articles = [
            {"section": "technology", "title": "A"},
            {"section": "business", "title": "B"},
            {"section": "technology", "title": "C"},
        ]
        result = group_by_section(articles)
        sections = dict(result)
        assert len(sections["technology"]) == 2
        assert len(sections["business"]) == 1

    def test_section_ordering(self):
        articles = [
            {"section": "sports", "title": "A"},
            {"section": "technology", "title": "B"},
            {"section": "world", "title": "C"},
        ]
        result = group_by_section(articles)
        section_names = [s for s, _ in result]
        # technology and world should come before sports per SECTION_ORDER
        assert section_names.index("technology") < section_names.index("sports")
        assert section_names.index("world") < section_names.index("sports")

    def test_unknown_section_appended(self):
        articles = [
            {"section": "technology", "title": "A"},
            {"section": "gardening", "title": "B"},
        ]
        result = group_by_section(articles)
        section_names = [s for s, _ in result]
        assert "gardening" in section_names
        assert section_names.index("technology") < section_names.index("gardening")

    def test_missing_section_defaults_to_other(self):
        articles = [{"title": "A"}]
        result = group_by_section(articles)
        assert result[0][0] == "other"


# ── friendly_date_filter ──

class TestFriendlyDate:
    def test_basic_date(self):
        assert friendly_date_filter("2026-03-25") == "25 March 2026"

    def test_iso_datetime(self):
        assert friendly_date_filter("2026-03-25T08:01:27-04:00") == "25 March 2026"

    def test_first_day(self):
        assert friendly_date_filter("2026-01-01") == "1 January 2026"

    def test_invalid_returns_original(self):
        assert friendly_date_filter("not-a-date") == "not-a-date"

    def test_empty_string(self):
        assert friendly_date_filter("") == ""


# ── _save_json (atomic writes) ──

class TestSaveJson:
    def test_writes_valid_json(self, tmp_path):
        path = str(tmp_path / "test.json")
        data = {"articles": [{"title": "Hello"}]}
        _save_json(data, path)
        with open(path) as f:
            loaded = json.load(f)
        assert loaded == data

    def test_overwrites_existing(self, tmp_path):
        path = str(tmp_path / "test.json")
        _save_json({"v": 1}, path)
        _save_json({"v": 2}, path)
        with open(path) as f:
            assert json.load(f) == {"v": 2}

    def test_no_temp_file_left_on_success(self, tmp_path):
        path = str(tmp_path / "test.json")
        _save_json({}, path)
        files = os.listdir(tmp_path)
        assert files == ["test.json"]


# ── score_articles (unscored flag) ──

class TestScoreArticles:
    def test_unscored_flag_set_when_ollama_unavailable(self, monkeypatch):
        """When Ollama is down, articles should get unscored=True."""
        monkeypatch.setattr("digest._score_batch", lambda batch: (_ for _ in ()).throw(ConnectionError("offline")))
        articles = [
            {"url": "https://example.com/1", "title": "A", "abstract": "a", "tags": [], "priority": 3},
            {"url": "https://example.com/2", "title": "B", "abstract": "b", "tags": [], "priority": 3},
        ]
        score_articles(articles)
        assert all(a.get("unscored") is True for a in articles)

    def test_scored_articles_have_no_unscored_flag(self, monkeypatch):
        """When Ollama works, articles should not have unscored flag."""
        def mock_score(batch):
            return {
                a["url"]: {"url": a["url"], "tags": ["AI"], "priority": 5}
                for a in batch
            }
        monkeypatch.setattr("digest._score_batch", mock_score)
        articles = [
            {"url": "https://example.com/1", "title": "A", "abstract": "a"},
        ]
        score_articles(articles)
        assert articles[0].get("unscored") is None
        assert articles[0]["priority"] == 5
        assert articles[0]["tags"] == ["AI"]


# ── XSS escaping in email ──

class TestEmailEscaping:
    def test_title_escaped_in_email(self):
        from email_digest import build_html
        articles_by_section = {
            "technology": [{
                "title": '<script>alert("xss")</script>',
                "abstract": "safe abstract",
                "url": "https://example.com/1",
                "tags": [],
                "priority": 3,
                "source": "top_stories",
            }],
        }
        html = build_html(articles_by_section, "2026-03-26")
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_abstract_escaped_in_email(self):
        from email_digest import build_html
        articles_by_section = {
            "technology": [{
                "title": "Safe Title",
                "abstract": '<img src=x onerror=alert(1)>',
                "url": "https://example.com/1",
                "tags": [],
                "priority": 3,
                "source": "top_stories",
            }],
        }
        html = build_html(articles_by_section, "2026-03-26")
        # The <img tag should be escaped so it won't render
        assert "<img src=" not in html
        assert "&lt;img" in html


# ── Path validation ──

class TestPathValidation:
    @pytest.fixture
    def client(self):
        from app import app
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c

    def test_valid_date_format(self, client):
        resp = client.get("/digest/2026-03-26")
        # May be 200 or 404 (no data), but not rejected by validation
        assert resp.status_code in (200, 404)

    def test_path_traversal_rejected(self, client):
        resp = client.get("/digest/../../etc/passwd")
        assert resp.status_code == 404

    def test_invalid_date_format_rejected(self, client):
        resp = client.get("/digest/not-a-date")
        assert resp.status_code == 404

    def test_partial_date_rejected(self, client):
        resp = client.get("/digest/2026-03")
        assert resp.status_code == 404
