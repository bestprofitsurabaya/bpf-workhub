"""Tests for the news scraper module.

Validates that WpClient.request() is called with the correct positional
arguments (url, nonce) and that upload_image() receives the nonce parameter.
"""

import json
import os
import tempfile
import threading
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_wp_client():
    """Return a WpClient with mocked session so we never hit real WordPress."""
    from modules.news_scraper.wp_client import WpClient
    client = WpClient("https://example.com/wp-json/wp/v2/posts", "user", "pass-1234")
    client.session = MagicMock()
    return client


def _mock_ok_response(json_data=None, status=200):
    """Build a mock requests.Response that returns ok."""
    resp = MagicMock()
    resp.status_code = status
    resp.ok = status in (200, 201)
    resp.json.return_value = json_data or []
    resp.text = json.dumps(json_data or [])
    resp.headers = {}
    return resp


# ---------------------------------------------------------------------------
# WpClient.request() signature tests
# ---------------------------------------------------------------------------

class TestWpClientRequestSignature:
    """Ensure WpClient.request() and helper methods work correctly."""

    def test_request_requires_url_and_nonce(self):
        """request() should fail if url or nonce are missing."""
        from modules.news_scraper.wp_client import WpClient
        client = WpClient("https://example.com/wp-json/wp/v2/posts", "u", "p")
        client.session = MagicMock()

        with pytest.raises(TypeError, match="url"):
            client.request("GET")

        with pytest.raises(TypeError, match="url"):
            client.request("GET", params={"per_page": 1})

    def test_request_passes_url_to_session(self):
        """The url arg should be forwarded to session.request()."""
        client = _make_wp_client()
        client.session.request.return_value = _mock_ok_response()

        client.request("GET", "https://example.com/wp-json/wp/v2/posts", "nonce123",
                       params={"per_page": 5})

        client.session.request.assert_called_once()
        call_args = client.session.request.call_args
        assert call_args[0][0] == "GET"
        assert call_args[0][1] == "https://example.com/wp-json/wp/v2/posts"
        assert call_args[1]["headers"]["X-WP-Nonce"] == "nonce123"
        assert call_args[1]["params"] == {"per_page": 5}

    def test_request_with_post_json(self):
        """POST with JSON body should pass url, nonce, and json kwarg."""
        client = _make_wp_client()
        client.session.request.return_value = _mock_ok_response({"id": 42}, status=201)

        client.request("POST", "https://example.com/wp-json/wp/v2/posts", "tok",
                       json={"title": "Hello"})

        call_args = client.session.request.call_args
        assert call_args[0][0] == "POST"
        assert call_args[1]["json"] == {"title": "Hello"}

    def test_get_posts_uses_helper(self):
        """get_posts() should delegate to request() with correct URL."""
        client = _make_wp_client()
        client.session.request.return_value = _mock_ok_response([{"id": 1}])

        r = client.get_posts("tok", params={"per_page": 5})
        assert r.status_code == 200
        call_args = client.session.request.call_args
        assert "/wp-json/wp/v2/posts" in call_args[0][1]

    def test_create_post_uses_helper(self):
        """create_post() should send POST with JSON body."""
        client = _make_wp_client()
        client.session.request.return_value = _mock_ok_response({"id": 99}, status=201)

        r = client.create_post({"title": "New"}, "tok")
        assert r.status_code == 201
        call_args = client.session.request.call_args
        assert call_args[0][0] == "POST"
        assert call_args[1]["json"] == {"title": "New"}

    def test_update_post_uses_helper(self):
        """update_post() should send POST to posts/<id>."""
        client = _make_wp_client()
        client.session.request.return_value = _mock_ok_response({"id": 42})

        r = client.update_post(42, {"content": "updated"}, "tok")
        assert r.status_code == 200
        call_args = client.session.request.call_args
        assert "/wp-json/wp/v2/posts/42" in call_args[0][1]

    def test_search_posts_uses_helper(self):
        """search_posts() should use get_posts with search param."""
        client = _make_wp_client()
        client.session.request.return_value = _mock_ok_response([{"id": 1, "title": {"rendered": "Test"}}])

        r = client.search_posts("Test", "tok")
        assert r.status_code == 200
        call_args = client.session.request.call_args
        assert call_args[1]["params"]["search"] == "Test"


# ---------------------------------------------------------------------------
# WpClient URL normalization tests
# ---------------------------------------------------------------------------

class TestWpClientUrlNormalization:
    """WpClient must accept both site root and full REST endpoint URLs.

    Regression test: wp_sites.json stores wp_url as the full endpoint
    ('.../wp-json/wp/v2/posts'), but WpClient appends '/wp-json/wp/v2/...'
    again, producing 404 rest_no_route on every request.
    """

    def test_full_endpoint_url_is_normalized(self):
        from modules.news_scraper.wp_client import WpClient
        client = WpClient("https://example.com/wp-json/wp/v2/posts", "u", "p")
        assert client.wp_url == "https://example.com"

    def test_media_endpoint_url_is_normalized(self):
        from modules.news_scraper.wp_client import WpClient
        client = WpClient("https://example.com/wp-json/wp/v2/media", "u", "p")
        assert client.wp_url == "https://example.com"

    def test_bare_root_url_unchanged(self):
        from modules.news_scraper.wp_client import WpClient
        client = WpClient("https://example.com", "u", "p")
        assert client.wp_url == "https://example.com"

    def test_trailing_slash_stripped(self):
        from modules.news_scraper.wp_client import WpClient
        client = WpClient("https://example.com/", "u", "p")
        assert client.wp_url == "https://example.com"

    def test_login_url_wellformed(self):
        """login() must hit the real /users/me route, not a nested one."""
        from modules.news_scraper.wp_client import WpClient
        client = WpClient("https://example.com/wp-json/wp/v2/posts", "u", "p")
        client.session = MagicMock()
        client.session.get.return_value = _mock_ok_response({"id": 1})
        ok, _msg = client.login()
        assert ok is True
        url = client.session.get.call_args[0][0]
        assert url == "https://example.com/wp-json/wp/v2/users/me"
        assert url.count("/wp-json") == 1

    def _login_response(self, status, code):
        resp = MagicMock()
        resp.status_code = status
        resp.json.return_value = {"code": code, "message": "x", "data": {"status": status}}
        resp.text = json.dumps(resp.json.return_value)
        return resp

    def test_login_401_gives_actionable_message(self):
        """A rejected application password should yield an actionable message."""
        from modules.news_scraper.wp_client import WpClient
        client = WpClient("https://example.com", "it_bpf_surabaya", "bad-pass")
        client.session = MagicMock()
        client.session.get.return_value = self._login_response(401, "rest_not_logged_in")
        ok, msg = client.login()
        assert ok is False
        assert "Application Passwords" in msg
        assert "it_bpf_surabaya" in msg

    def test_login_wrong_password_message(self):
        from modules.news_scraper.wp_client import WpClient
        client = WpClient("https://example.com", "user", "salah")
        client.session = MagicMock()
        client.session.get.return_value = self._login_response(401, "incorrect_password")
        ok, msg = client.login()
        assert ok is False
        assert "Password aplikasi salah" in msg


class TestWpClientFallbackAuth:
    """Basic-auth fallback saat application password ditolak (401)."""

    def _client_with_mock(self, responses):
        from modules.news_scraper.wp_client import WpClient
        client = WpClient("https://example.com", "app_user", "bad-app-pass",
                          fallback_auth=("human", "password"))
        client.session = MagicMock()
        client.session.get.side_effect = responses
        return client

    def test_fallback_used_when_app_password_rejected(self):
        resp401 = MagicMock()
        resp401.status_code = 401
        resp401.json.return_value = {"code": "rest_not_logged_in"}
        resp200 = MagicMock()
        resp200.status_code = 200
        client = self._client_with_mock([resp401, resp200])
        ok, _msg = client.login()
        assert ok is True
        # Kredensial kedua yang aktif untuk request berikutnya
        assert client.active_auth == ("human", "password")
        assert client.session.get.call_count == 2

    def test_request_uses_active_auth_after_fallback(self):
        resp401 = MagicMock(); resp401.status_code = 401
        resp401.json.return_value = {"code": "rest_not_logged_in"}
        resp200 = MagicMock(); resp200.status_code = 200
        client = self._client_with_mock([resp401, resp200])
        client.login()
        client.session.request.return_value = _mock_ok_response([])
        client.get_posts("nonce-x")
        call_kwargs = client.session.request.call_args[1]
        assert call_kwargs["auth"] == ("human", "password")

    def test_no_fallback_when_primary_ok(self):
        resp200 = MagicMock(); resp200.status_code = 200
        client = self._client_with_mock([resp200])
        ok, _msg = client.login()
        assert ok is True
        assert client.active_auth == ("app_user", "bad-app-pass")
        assert client.session.get.call_count == 1

    def test_all_pairs_fail_reports_actionable(self):
        resp401 = MagicMock()
        resp401.status_code = 401
        resp401.json.return_value = {"code": "rest_not_logged_in"}
        client = self._client_with_mock([resp401, resp401])
        ok, msg = client.login()
        assert ok is False
        assert "sudah dicoba" in msg

    def test_make_wp_client_reads_basic_credentials(self):
        """_make_wp_client harus meneruskan basic_username/password sebagai fallback."""
        from modules.news_scraper.routes import _make_wp_client
        site = {
            "wp_url": "https://example.com/wp-json/wp/v2/posts",
            "username": "app_user",
            "app_password": "x",
            "basic_username": "human",
            "basic_password": "password",
        }
        client = _make_wp_client(site)
        assert ("human", "password") in client._auth_pairs

    def test_make_wp_client_without_basic_credentials(self):
        from modules.news_scraper.routes import _make_wp_client
        site = {
            "wp_url": "https://example.com/wp-json/wp/v2/posts",
            "username": "app_user",
            "app_password": "x",
        }
        client = _make_wp_client(site)
        assert len(client._auth_pairs) == 1


# ---------------------------------------------------------------------------
# upload_image() tests
# ---------------------------------------------------------------------------

class TestUploadImage:
    """Ensure upload_image() requires a nonce and works correctly."""

    def test_upload_image_requires_nonce(self):
        """upload_image(url) without nonce should raise TypeError."""
        client = _make_wp_client()
        with pytest.raises(TypeError, match="nonce"):
            client.upload_image("https://example.com/image.jpg")

    def test_upload_image_with_nonce_calls_request(self):
        """upload_image(url, nonce) should call request with POST to media endpoint."""
        client = _make_wp_client()
        client.session.get.return_value.__enter__ = MagicMock(return_value=MagicMock(
            status_code=200,
            headers={"Content-Type": "image/jpeg", "Content-Length": "100"},
            raise_for_status=MagicMock(),
            iter_content=MagicMock(return_value=[b"\x89PNG\r\n\x1a\nfake-image-data"]),
        ))
        client.session.get.return_value.__exit__ = MagicMock(return_value=False)
        client.session.request.return_value = _mock_ok_response({"id": 99, "source_url": "https://example.com/wp-content/uploads/img.jpg"}, status=201)

        result = client.upload_image("https://example.com/image.jpg", "my-nonce")

        assert result is not None
        assert result["id"] == 99
        # Verify it called request with POST to media URL
        client.session.request.assert_called_once()
        call_args = client.session.request.call_args
        assert call_args[0][0] == "POST"
        assert "/wp-json/wp/v2/media" in call_args[0][1]


# ---------------------------------------------------------------------------
# Helper functions tests (from routes.py)
# ---------------------------------------------------------------------------

class TestHelpers:
    """Test the internal helper functions in routes.py."""

    def test_load_json_valid(self, tmp_path):
        from modules.news_scraper.routes import _load_json
        p = tmp_path / "test.json"
        p.write_text('{"key": "value"}')
        result = _load_json(str(p), {})
        assert result == {"key": "value"}

    def test_load_json_missing_returns_default(self):
        from modules.news_scraper.routes import _load_json
        result = _load_json("/nonexistent/path.json", {"default": True})
        assert result == {"default": True}

    def test_save_json_creates_file(self, tmp_path):
        from modules.news_scraper.routes import _save_json
        p = str(tmp_path / "out.json")
        _save_json(p, {"hello": "world"})
        with open(p) as f:
            assert json.load(f) == {"hello": "world"}

    def test_sanitize_csv_prefixes_formula(self):
        from modules.news_scraper.routes import _sanitize_csv
        assert _sanitize_csv("=SUM(A1)") == "'=SUM(A1)"
        assert _sanitize_csv("+hello") == "'+hello"
        assert _sanitize_csv("-100") == "'-100"
        assert _sanitize_csv("@test") == "'@test"
        assert _sanitize_csv("normal text") == "normal text"
        assert _sanitize_csv(None) == ""


# ---------------------------------------------------------------------------
# Branch filtering tests (list_wp_sites helper)
# ---------------------------------------------------------------------------

class TestBranchFiltering:
    """Ensure _visible_sites / _site_matches_branch work for branch users."""

    SITES = {
        "BPF Surabaya": {"branch_code": ""},           # no branch_code set
        "BPF Jakarta (HO)": {"branch_code": "JKT"},
        "BPF Bandung": {"branch_code": "BDG"},
    }

    def test_sby_user_sees_surabaya_without_branch_code(self):
        """it_sby must see 'BPF Surabaya' even when branch_code is missing.

        Regression test: 'sby' is not a substring of 'bpf surabaya', so the
        old naive substring fallback returned zero sites.
        """
        from modules.news_scraper.routes import _visible_sites
        result = _visible_sites(self.SITES, "SBY", "it_sby", "it_sby")
        assert list(result.keys()) == ["BPF Surabaya"]

    def test_branch_code_exact_match(self):
        from modules.news_scraper.routes import _visible_sites
        result = _visible_sites(self.SITES, "BDG", "it_bdg", "it_bdg")
        assert list(result.keys()) == ["BPF Bandung"]

    def test_admin_sees_all_sites(self):
        from modules.news_scraper.routes import _visible_sites
        result = _visible_sites(self.SITES, "", "admin", "admin")
        assert len(result) == 3

    def test_hq_sees_all_sites(self):
        from modules.news_scraper.routes import _visible_sites
        result = _visible_sites(self.SITES, "SBY", "it_hu", "it_hu")
        assert len(result) == 3

    def test_unknown_branch_sees_nothing(self):
        from modules.news_scraper.routes import _visible_sites
        result = _visible_sites(self.SITES, "XXX", "it_xxx", "it_xxx")
        assert result == {}

    def test_match_is_case_insensitive(self):
        from modules.news_scraper.routes import _site_matches_branch
        assert _site_matches_branch("BPF Surabaya", "", "sby") is True
        assert _site_matches_branch("BPF Surabaya", "sby", "SBY") is True


# ---------------------------------------------------------------------------
# ScraperEngine helper tests
# ---------------------------------------------------------------------------

class TestRateLimiter:
    def test_allows_within_limit(self):
        from modules.news_scraper.scraper_engine import RateLimiter
        rl = RateLimiter(max_requests=5, window_seconds=60)
        allowed = rl.check("user1")
        assert allowed is True

    def test_blocks_after_limit(self):
        from modules.news_scraper.scraper_engine import RateLimiter
        rl = RateLimiter(max_requests=2, window_seconds=60)
        rl.check("u1")
        rl.check("u1")
        allowed = rl.check("u1")
        assert allowed is False


class TestProgressTracker:
    def test_set_and_get(self):
        from modules.news_scraper.scraper_engine import ProgressTracker
        pt = ProgressTracker()
        pt.set("task-1", {"stage": "scrape", "progress": 50, "message": "halfway"})
        snap = pt.get("task-1")
        assert snap["stage"] == "scrape"
        assert snap["progress"] == 50
        assert snap["message"] == "halfway"

    def test_get_unknown_returns_none(self):
        from modules.news_scraper.scraper_engine import ProgressTracker
        pt = ProgressTracker()
        assert pt.get("nonexistent") is None


# ---------------------------------------------------------------------------
# SEO helper tests
# ---------------------------------------------------------------------------

class TestSeoOptimizer:
    def test_normalize_title(self):
        from modules.news_scraper.seo_optimizer import normalize_title
        assert normalize_title("Harga Emas Naik!") == normalize_title("harga emas naik")
        assert normalize_title("  Spaced  ") == normalize_title("spaced")

    def test_seo_analyze_returns_score(self):
        from modules.news_scraper.seo_optimizer import seo_analyze
        result = seo_analyze("<h1>Test Title</h1><p>Some content</p><p>More text here for analysis</p>", "Test Title")
        assert "seo_score" in result
        assert isinstance(result["seo_score"], (int, float))
        assert 0 <= result["seo_score"] <= 100
        assert "suggestions" in result

    def test_seo_analyze_empty_content(self):
        from modules.news_scraper.seo_optimizer import seo_analyze
        result = seo_analyze("", "")
        assert result["seo_score"] == 0
        assert len(result["suggestions"]) > 0


# ---------------------------------------------------------------------------
# Integration: route-level smoke test with Flask test client
# ---------------------------------------------------------------------------

@pytest.mark.skipif(True, reason='Requires MySQL Docker environment — run in container')
class TestScraperRoutes:
    """Smoke tests using Flask test client with mocked session."""

    @pytest.fixture
    def client(self):
        from app import app
        app.config["TESTING"] = True
        app.config["SESSION_COOKIE_SECURE"] = False
        with app.test_client() as c:
            yield c

    def _login(self, test_client):
        """Set up a session that looks like a logged-in it_sby user."""
        with test_client.session_transaction() as sess:
            sess["user_role"] = "it_sby"
            sess["user_name"] = "it_sby"
            sess["full_name"] = "IT Surabaya"
            sess["branch_code"] = "SBY"
            sess["csrf_token"] = "test-csrf-token"

    def test_list_sites_requires_auth(self, client):
        """Unauthenticated request should return 401."""
        resp = client.get("/api/scraper/sites")
        assert resp.status_code in (401, 302)

    def test_list_sites_ok_when_logged_in(self, client):
        self._login(client)
        resp = client.get("/api/scraper/sites")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_test_connection_missing_fields(self, client):
        self._login(client)
        resp = client.post("/api/scraper/test-connection",
                           json={"site_name": "nonexistent"},
                           headers={"X-CSRF-Token": "test-csrf-token"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is False
        assert "tidak ditemukan" in data["message"]

    def test_upload_missing_site(self, client):
        self._login(client)
        resp = client.post("/api/scraper/upload",
                           json={"site_name": "", "articles": []},
                           headers={"X-CSRF-Token": "test-csrf-token"})
        assert resp.status_code == 400

    def test_upload_missing_articles(self, client):
        self._login(client)
        resp = client.post("/api/scraper/upload",
                           json={"site_name": "TestSite", "articles": []},
                           headers={"X-CSRF-Token": "test-csrf-token"})
        assert resp.status_code == 400

    def test_check_scraper_requires_role(self, client):
        """User with wrong role should get 403."""
        with client.session_transaction() as sess:
            sess["user_role"] = "driver"
            sess["user_name"] = "driver1"
        resp = client.post("/api/scraper/check",
                           json={"pages": 1},
                           headers={"X-CSRF-Token": "test-csrf-token"})
        assert resp.status_code == 403
