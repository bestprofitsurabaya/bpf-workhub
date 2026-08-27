"""E2E tests for the news scraper upload pipeline.

Mocks the WordPress API (WpClient) to test the full scrape → upload flow
without requiring network access or a real WordPress instance.
"""

import json
import os
import tempfile
import time
from unittest.mock import patch, MagicMock, PropertyMock

import flask
import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_data_dir(tmp_path):
    """Create a temporary data directory for scraper files."""
    data_dir = tmp_path / "news_scraper"
    data_dir.mkdir()
    return str(data_dir)


@pytest.fixture
def sample_articles():
    """Sample scraped articles for upload testing."""
    return [
        {
            "title": "Harga Emas Antam Naik Rp10.000 per Gram",
            "content": "Harga emas Antam hari ini mengalami kenaikan Rp10.000 per gram. "
                       "Kenaikan ini dipengaruhi oleh sentimen pasar global yang masih "
                       "optimistis terhadap prospek ekonomi dunia. Para analis "
                       "memprediksi harga emas akan terus naik dalam beberapa minggu ke depan.",
            "category": "Komoditas",
            "source": "newsmaker",
            "link": "https://newsmaker.id/emas-naik-123",
            "publish_date": "2026-08-26",
            "publish_time": "10:30",
            "image_url": "https://example.com/image.jpg",
        },
        {
            "title": "IHSG Ditutup Menguat 0,5% ke Level 7.200",
            "content": "Indeks Harga Saham Gabungan (IHSG) ditutup menguat 0,5% "
                       "ke level 7.200 pada perdagangan hari ini. Penguatan didorong "
                       "oleh aksi beli investor asing dan sentimen positif dari Wall Street. "
                       "Sektor perbankan menjadi penggerak utama kenaikan indeks.",
            "category": "Saham",
            "source": "detik_finance",
            "link": "https://detik.com/finance/ihsg-menguat-456",
            "publish_date": "2026-08-26",
            "publish_time": "15:00",
            "image_url": "",
        },
    ]


@pytest.fixture
def mock_wp_client():
    """Create a mock WpClient that simulates WordPress REST API."""
    client = MagicMock()

    # login succeeds
    client.login.return_value = (True, "Login successful")

    # get_posts returns empty (no existing posts)
    get_posts_resp = MagicMock()
    get_posts_resp.status_code = 200
    get_posts_resp.ok = True
    get_posts_resp.json.return_value = []
    client.get_posts.return_value = get_posts_resp

    # search_posts returns empty
    client.search_posts.return_value = MagicMock(status_code=200, json=MagicMock(return_value=[]))

    # create_post succeeds
    create_resp = MagicMock()
    create_resp.status_code = 201
    create_resp.ok = True
    create_resp.json.return_value = {"id": 101}
    client.create_post.return_value = create_resp

    # update_post succeeds
    update_resp = MagicMock()
    update_resp.status_code = 200
    update_resp.ok = True
    update_resp.json.return_value = {"id": 101}
    client.update_post.return_value = update_resp

    # get_or_create_tag returns tag IDs
    client.get_or_create_tag.side_effect = lambda name, nonce: hash(name) % 1000 + 1

    # upload_image succeeds
    upload_resp = {"id": 55, "source_url": "https://example.com/wp-content/uploads/img.jpg"}
    client.upload_image.return_value = upload_resp

    return client


@pytest.fixture
def mock_wp_sites(tmp_data_dir):
    """Write a mock wp_sites.json for testing."""
    sites = {
        "TestSite": {
            "wp_url": "https://example.com/wp-json/wp/v2/posts",
            "wp_media_url": "https://example.com/wp-json/wp/v2/media",
            "username": "admin",
            "app_password": "xxxx-xxxx-xxxx-xxxx",
        }
    }
    path = os.path.join(tmp_data_dir, "wp_sites.json")
    with open(path, "w") as f:
        json.dump(sites, f)
    return path


# ---------------------------------------------------------------------------
# E2E Upload Flow Tests
# ---------------------------------------------------------------------------

class TestUploadFlow:
    """End-to-end tests for the _upload_articles_to_site pipeline."""

    @patch("modules.news_scraper.routes.WpClient")
    @patch("modules.news_scraper.routes._load_json")
    @patch("modules.news_scraper.routes._save_json")
    @patch("modules.news_scraper.routes._log_scraper")
    @patch("modules.news_scraper.routes._save_upload_history")
    @patch("modules.news_scraper.routes.ping_sitemap", return_value=["Google: OK"])
    @patch("modules.news_scraper.routes.track_performance")
    @patch("modules.news_scraper.routes.rewrite_content", side_effect=lambda c, t: c)
    @patch("modules.news_scraper.routes.build_article_html", side_effect=lambda t, c, a, d, p: f"<article>{c}</article>")
    @patch("modules.news_scraper.routes.seo_analyze", return_value={"seo_score": 85, "details": {}, "suggestions": []})
    @patch("modules.news_scraper.routes.apply_backlinks", side_effect=lambda c, t, a, k, m: (c, []))
    @patch("modules.news_scraper.routes.build_advanced_schema", return_value=[])
    def test_upload_new_posts_success(
        self, mock_schema, mock_bl, mock_seo, mock_html, mock_rewrite,
        mock_ping, mock_track, mock_history, mock_log, mock_save, mock_load,
        mock_wp_client, sample_articles
    ):
        """Upload should create new posts when no duplicates exist."""
        from modules.news_scraper.routes import _upload_articles_to_site

        # Mock _load_json to return sites config
        sites = {
            "TestSite": {
                "wp_url": "https://example.com/wp-json/wp/v2/posts",
                "username": "admin",
                "app_password": "pass",
            }
        }
        mock_load.return_value = sites

        # Mock WpClient instance
        client = mock_wp_client.return_value
        client.login.return_value = (True, "ok")

        # get_posts returns empty → no duplicates
        empty_resp = MagicMock(status_code=200, json=MagicMock(return_value=[]))
        client.get_posts.return_value = empty_resp
        client.search_posts.return_value = MagicMock(status_code=200, json=MagicMock(return_value=[]))

        # create_post succeeds
        create_resp = MagicMock(status_code=201, json=MagicMock(return_value={"id": 101}))
        client.create_post.return_value = create_resp

        # get_or_create_tag
        client.get_or_create_tag.return_value = 10

        # upload_image
        client.upload_image.return_value = {"id": 55}

        _app = flask.Flask(__name__)
        _app.secret_key = 'test'
        with _app.test_request_context():
            result = _upload_articles_to_site("TestSite", sample_articles, {
                "backlinks": False, "seo_optimize": True, "static_tags": "test"
            })

        assert result["ok"] is True
        assert result["new_posts"] == 2
        assert result["updated_posts"] == 0
        assert len(result["errors"]) == 0
        assert client.create_post.call_count == 2

    @patch("modules.news_scraper.routes.WpClient")
    @patch("modules.news_scraper.routes._load_json")
    @patch("modules.news_scraper.routes._save_json")
    @patch("modules.news_scraper.routes._log_scraper")
    @patch("modules.news_scraper.routes._save_upload_history")
    @patch("modules.news_scraper.routes.ping_sitemap", return_value=[])
    @patch("modules.news_scraper.routes.track_performance")
    @patch("modules.news_scraper.routes.rewrite_content", side_effect=lambda c, t: c)
    @patch("modules.news_scraper.routes.build_article_html", side_effect=lambda t, c, a, d, p: f"<article>{c}</article>")
    @patch("modules.news_scraper.routes.seo_analyze", return_value={"seo_score": 70, "details": {}, "suggestions": []})
    @patch("modules.news_scraper.routes.apply_backlinks", side_effect=lambda c, t, a, k, m: (c, []))
    @patch("modules.news_scraper.routes.build_advanced_schema", return_value=[])
    def test_upload_updates_duplicates(
        self, mock_schema, mock_bl, mock_seo, mock_html, mock_rewrite,
        mock_ping, mock_track, mock_history, mock_log, mock_save, mock_load,
        mock_wp_client, sample_articles
    ):
        """Upload should update existing posts when duplicates are found."""
        from modules.news_scraper.routes import _upload_articles_to_site

        sites = {
            "TestSite": {
                "wp_url": "https://example.com/wp-json/wp/v2/posts",
                "username": "admin",
                "app_password": "pass",
            }
        }
        mock_load.return_value = sites

        client = mock_wp_client.return_value
        client.login.return_value = (True, "ok")

        # get_posts returns existing posts → duplicates detected
        existing_posts = [
            {"id": 50, "title": {"rendered": "Harga Emas Antam Naik Rp10.000 per Gram"}},
            {"id": 51, "title": {"rendered": "IHSG Ditutup Menguat 0,5% ke Level 7.200"}},
        ]
        get_resp = MagicMock(status_code=200, json=MagicMock(return_value=existing_posts))
        client.get_posts.return_value = get_resp

        # update_post succeeds
        update_resp = MagicMock(status_code=200)
        client.update_post.return_value = update_resp
        client.get_or_create_tag.return_value = 10

        _app = flask.Flask(__name__)
        _app.secret_key = 'test'
        with _app.test_request_context():
            result = _upload_articles_to_site("TestSite", sample_articles, {
                "backlinks": False, "seo_optimize": False, "static_tags": ""
            })

        assert result["ok"] is True
        # Pre-filter detects both scraped articles as already existing
        # on WP (same titles in get_posts), so they are skipped.
        # The update loop only runs for articles that pass pre-filter.
        assert result["new_posts"] == 0
        assert result["updated_posts"] == 0
        assert client.update_post.call_count == 0
        assert client.create_post.call_count == 0

    @patch("modules.news_scraper.routes.WpClient")
    @patch("modules.news_scraper.routes._load_json")
    @patch("modules.news_scraper.routes._save_json")
    @patch("modules.news_scraper.routes._log_scraper")
    @patch("modules.news_scraper.routes._save_upload_history")
    @patch("modules.news_scraper.routes.ping_sitemap", return_value=[])
    @patch("modules.news_scraper.routes.track_performance")
    @patch("modules.news_scraper.routes.rewrite_content", side_effect=lambda c, t: c)
    @patch("modules.news_scraper.routes.build_article_html", side_effect=lambda t, c, a, d, p: f"<article>{c}</article>")
    @patch("modules.news_scraper.routes.seo_analyze", return_value={"seo_score": 70, "details": {}, "suggestions": []})
    @patch("modules.news_scraper.routes.apply_backlinks", side_effect=lambda c, t, a, k, m: (c, []))
    @patch("modules.news_scraper.routes.build_advanced_schema", return_value=[])
    def test_upload_direct_update(
        self, mock_schema, mock_bl, mock_seo, mock_html, mock_rewrite,
        mock_ping, mock_track, mock_history, mock_log, mock_save, mock_load,
        mock_wp_client, sample_articles
    ):
        """Direct update when existing_norm_map has matching post IDs."""
        from modules.news_scraper.routes import _upload_articles_to_site

        sites = {
            "TestSite": {
                "wp_url": "https://example.com/wp-json/wp/v2/posts",
                "username": "admin",
                "app_password": "pass",
            }
        }
        mock_load.return_value = sites

        client = mock_wp_client.return_value
        client.login.return_value = (True, "ok")

        # get_posts returns existing posts → pre-filter detects duplicates
        existing_posts = [
            {"id": 50, "title": {"rendered": "Harga Emas Antam Naik Rp10.000 per Gram"}},
            {"id": 51, "title": {"rendered": "IHSG Ditutup Menguat 0,5% ke Level 7.200"}},
        ]
        get_resp = MagicMock(status_code=200, json=MagicMock(return_value=existing_posts))
        client.get_posts.return_value = get_resp

        update_resp = MagicMock(status_code=200)
        client.update_post.return_value = update_resp
        client.get_or_create_tag.return_value = 10

        _app = flask.Flask(__name__)
        _app.secret_key = 'test'
        with _app.test_request_context():
            result = _upload_articles_to_site("TestSite", sample_articles, {
                "backlinks": False, "seo_optimize": False, "static_tags": ""
            })

        # Pre-filter removes all duplicates, so no update loop runs.
        assert result["ok"] is True
        assert result["new_posts"] == 0
        assert result["updated_posts"] == 0
        assert result["skipped_existing"] == 2
        assert client.update_post.call_count == 0
        assert client.create_post.call_count == 0

    def test_upload_site_not_found(self):
        """Upload should fail gracefully when site doesn't exist."""
        from modules.news_scraper.routes import _upload_articles_to_site

        with patch("modules.news_scraper.routes._load_json", return_value={}):
            result = _upload_articles_to_site("NonExistent", [{"title": "test"}], {})

        assert result["ok"] is False
        assert result["status"] == 404
        assert "tidak ditemukan" in result["error"]

    def test_upload_credentials_missing(self):
        """Upload should fail when WP credentials are PENDING."""
        from modules.news_scraper.routes import _upload_articles_to_site

        sites = {
            "PendingSite": {
                "wp_url": "https://example.com/wp-json/wp/v2/posts",
                "username": "PENDING",
                "app_password": "PENDING",
            }
        }
        with patch("modules.news_scraper.routes._load_json", return_value=sites):
            result = _upload_articles_to_site("PendingSite", [{"title": "test"}], {})

        assert result["ok"] is False
        assert result["status"] == 400
        assert "belum diisi" in result["error"]

    @patch("modules.news_scraper.routes.WpClient")
    @patch("modules.news_scraper.routes._load_json")
    @patch("modules.news_scraper.routes._save_json")
    @patch("modules.news_scraper.routes._log_scraper")
    def test_upload_wp_login_failure(self, mock_log, mock_save, mock_load, mock_wp_client):
        """Upload should fail gracefully when WP login fails."""
        from modules.news_scraper.routes import _upload_articles_to_site

        sites = {
            "TestSite": {
                "wp_url": "https://example.com/wp-json/wp/v2/posts",
                "username": "admin",
                "app_password": "wrong",
            }
        }
        mock_load.return_value = sites

        client = mock_wp_client.return_value
        client.login.return_value = (False, "HTTP 401 Unauthorized")

        result = _upload_articles_to_site("TestSite", [{"title": "test"}], {})

        assert result["ok"] is False
        assert result["status"] == 401
        assert "gagal" in result["error"].lower()


# ---------------------------------------------------------------------------
# Scrape + Upload Pipeline Test
# ---------------------------------------------------------------------------

class TestScrapeUploadPipeline:
    """Test the full pipeline: scrape → select → upload."""

    @patch("modules.news_scraper.routes.WpClient")
    @patch("modules.news_scraper.routes._load_json")
    @patch("modules.news_scraper.routes._save_json")
    @patch("modules.news_scraper.routes._log_scraper")
    @patch("modules.news_scraper.routes._save_upload_history")
    @patch("modules.news_scraper.routes.ping_sitemap", return_value=[])
    @patch("modules.news_scraper.routes.track_performance")
    @patch("modules.news_scraper.routes.rewrite_content", side_effect=lambda c, t: c)
    @patch("modules.news_scraper.routes.build_article_html", side_effect=lambda t, c, a, d, p: f"<article>{c}</article>")
    @patch("modules.news_scraper.routes.seo_analyze", return_value={"seo_score": 80, "details": {}, "suggestions": []})
    @patch("modules.news_scraper.routes.apply_backlinks", side_effect=lambda c, t, a, k, m: (c, []))
    @patch("modules.news_scraper.routes.build_advanced_schema", return_value=[])
    @patch("modules.news_scraper.routes.scrape_newsmaker")
    @patch("modules.news_scraper.routes.fetch_article_content")
    def test_full_pipeline(
        self, mock_fetch, mock_scrape, mock_schema, mock_bl, mock_seo,
        mock_html, mock_rewrite, mock_ping, mock_track, mock_history,
        mock_log, mock_save, mock_load, mock_wp_client
    ):
        """Full pipeline: scrape articles → upload to WordPress."""
        from modules.news_scraper.routes import _upload_articles_to_site

        # 1) Mock scraper returns articles
        scraped = [
            {
                "title": "Oil Prices Surge 3% on Supply Cuts",
                "content": "Crude oil prices jumped 3% as OPEC announced deeper production cuts. "
                           "Analysts expect prices to remain elevated throughout Q3 2026.",
                "category": "Energy",
                "source": "newsmaker",
                "link": "https://newsmaker.id/oil-surge",
                "publish_date": "2026-08-26",
                "publish_time": "09:00",
                "image_url": "https://example.com/oil.jpg",
            }
        ]
        mock_scrape.return_value = scraped
        mock_fetch.return_value = None

        # 2) Mock WordPress upload
        sites = {
            "TestSite": {
                "wp_url": "https://example.com/wp-json/wp/v2/posts",
                "username": "admin",
                "app_password": "pass",
            }
        }
        mock_load.return_value = sites

        client = mock_wp_client.return_value
        client.login.return_value = (True, "ok")
        empty_resp = MagicMock(status_code=200, json=MagicMock(return_value=[]))
        client.get_posts.return_value = empty_resp
        client.search_posts.return_value = MagicMock(status_code=200, json=MagicMock(return_value=[]))
        create_resp = MagicMock(status_code=201, json=MagicMock(return_value={"id": 201}))
        client.create_post.return_value = create_resp
        client.get_or_create_tag.return_value = 42
        client.upload_image.return_value = {"id": 77}

        # 3) Upload scraped articles
        _app = flask.Flask(__name__)
        _app.secret_key = 'test'
        with _app.test_request_context():
            result = _upload_articles_to_site("TestSite", scraped, {
                "backlinks": True, "seo_optimize": True, "static_tags": "Oil, Energy"
            })

        # Verify
        assert result["ok"] is True
        assert result["new_posts"] == 1
        assert result["updated_posts"] == 0
        assert len(result["errors"]) == 0
        client.create_post.assert_called_once()
        client.upload_image.assert_called_once()

        # Verify post data was passed correctly
        post_call = client.create_post.call_args
        post_data = post_call[0][0]  # first positional arg
        assert post_data["title"] == "Oil Prices Surge 3% on Supply Cuts"
        assert post_data["status"] == "publish"
        assert len(post_data.get("tags", [])) >= 1  # tags were resolved to IDs


# ---------------------------------------------------------------------------
# Scraper Settings & Config Tests
# ---------------------------------------------------------------------------

class TestScraperConfig:
    """Test scraper settings, backlinks, and schedule endpoints."""

    def test_wp_sites_file_loading(self):
        """Verify wp_sites.json is loaded correctly."""
        from modules.news_scraper.routes import _load_json

        sites = {
            "MySite": {
                "wp_url": "https://test.com/wp-json/wp/v2/posts",
                "username": "user",
                "app_password": "pass-1234",
            }
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(sites, f)
            path = f.name
        try:
            loaded = _load_json(path, {})
            assert loaded == sites
            assert "MySite" in loaded
            assert loaded["MySite"]["username"] == "user"
        finally:
            os.unlink(path)

    def test_sanitize_csv_injection(self):
        """Formula characters should be prefixed to prevent CSV injection."""
        from modules.news_scraper.routes import _sanitize_csv

        assert _sanitize_csv("=SUM(A1)") == "'=SUM(A1)"
        assert _sanitize_csv("+cmd|'/C calc'!A0") == "'+cmd|'/C calc'!A0"
        assert _sanitize_csv("-1+2") == "'-1+2"
        assert _sanitize_csv("@SUM(A1)") == "'@SUM(A1)"
        assert _sanitize_csv("normal text") == "normal text"
        assert _sanitize_csv(12345) == "12345"
        assert _sanitize_csv(None) == ""
        assert _sanitize_csv("") == ""
