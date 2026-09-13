"""Tests for the scraper duplicate endpoints.

Covers:
- _fetch_all_posts pagination helper (incl. WP end-of-range 400 signal + cap)
- check_duplicates fuzzy matching (normalize_title grouping)
- delete_all_posts guards (confirm token, cap) + concurrent deletion

Uses a standalone Flask app registered with the scraper blueprint so no
database or real WordPress is needed; WpClient is mocked.
"""

import json
from unittest.mock import MagicMock, patch

import flask
import pytest


SCRAPER_ROLES = ("it_sby", "admin")


class FakeResp:
    """Minimal stand-in for requests.Response."""

    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else []

    def json(self):
        return self._payload


class FakeWpClient:
    """Fake WpClient backed by a list of posts; records deleted ids."""

    def __init__(self, posts=None, pages=None):
        self.posts = posts or []
        # Optional explicit page->payload mapping (overrides pagination math).
        self.pages = pages or {}
        self.deleted_ids = []
        self.deleted_lock = __import__("threading").Lock()

    def login(self):
        return True, "nonce-123"

    def get_posts(self, nonce, params=None, **kwargs):
        params = params or {}
        page = int(params.get("page", 1))
        per_page = int(params.get("per_page", 100))
        if page in self.pages:
            return self.pages[page]
        start = (page - 1) * per_page
        chunk = self.posts[start:start + per_page]
        if not chunk and page > 1:
            # WordPress returns 400 rest_post_invalid_page_number past the end.
            return FakeResp(400, {"code": "rest_post_invalid_page_number"})
        return FakeResp(200, chunk)

    def request(self, method, url, nonce, **kwargs):
        assert method == "DELETE"
        pid = int(url.rstrip("/").rsplit("/", 1)[-1])
        with self.deleted_lock:
            self.deleted_ids.append(pid)
        return FakeResp(200, {"deleted": True, "previous": {"id": pid}})


def make_post(pid, title):
    return {"id": pid, "title": {"rendered": title}, "date": "2026-09-01T10:00:00"}


# ---------------------------------------------------------------------------
# App fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def scraper_app():
    from modules.news_scraper import news_scraper_bp, SCRAPER_ROLES as roles
    app = flask.Flask(__name__)
    app.config["TESTING"] = True
    app.secret_key = "test"
    app.register_blueprint(news_scraper_bp)

    # Make role_required pass: seed session before each request.
    @app.before_request
    def _fake_session():
        from flask import session
        if session.get("user_role") is None:
            session["user_role"] = "it_sby"
            session["user_name"] = "tester"
    return app


@pytest.fixture
def client(scraper_app):
    return scraper_app.test_client()


@pytest.fixture
def site_with_posts():
    """Two exact dupes + two fuzzy dupes + one unique post."""
    return [
        make_post(1, "Harga Emas Naik"),
        make_post(2, "Harga Emas Naik"),
        make_post(3, "Harga Emas   Naik!"),      # fuzzy dupe of #1/#2
        make_post(4, "IHSG Menguat 0,5%"),
        make_post(5, "ihsg menguat 0,5%. "),     # fuzzy dupe of #4
        make_post(6, "Unik Saja"),
    ]


def _patch_sites(sites):
    return patch("modules.news_scraper.routes._load_json",
                 side_effect=lambda path, default: sites if path.endswith("wp_sites.json") else default)


# ---------------------------------------------------------------------------
# _fetch_all_posts helper
# ---------------------------------------------------------------------------

class TestFetchAllPosts:
    def _client_with(self, n_posts, per_page=3):
        posts = [make_post(i + 1, f"P{i}") for i in range(n_posts)]
        return FakeWpClient(posts=posts), posts

    def test_paginates_until_wp_400(self):
        client, posts = self._client_with(7, per_page=3)
        from modules.news_scraper.routes import _fetch_all_posts
        got, complete = _fetch_all_posts(client, "n", per_page=3)
        assert complete is True
        assert [p["id"] for p in got] == [p["id"] for p in posts]

    def test_short_page_ends_pagination(self):
        client, posts = self._client_with(5, per_page=100)
        from modules.news_scraper.routes import _fetch_all_posts
        got, complete = _fetch_all_posts(client, "n", per_page=100)
        assert complete is True
        assert len(got) == 5

    def test_max_pages_marks_incomplete(self):
        client, _ = self._client_with(30, per_page=3)
        from modules.news_scraper.routes import _fetch_all_posts
        got, complete = _fetch_all_posts(client, "n", per_page=3, max_pages=2)
        assert complete is False
        assert len(got) == 6

    def test_transport_error_marks_incomplete(self):
        client = FakeWpClient()
        client.get_posts = MagicMock(side_effect=RuntimeError("boom"))
        from modules.news_scraper.routes import _fetch_all_posts
        got, complete = _fetch_all_posts(client, "n")
        assert got == []
        assert complete is False


# ---------------------------------------------------------------------------
# check_duplicates (fuzzy)
# ---------------------------------------------------------------------------

class TestCheckDuplicates:
    def test_requires_site_name(self, client):
        r = client.post("/api/scraper/duplicates", json={})
        assert r.status_code == 400

    def test_unknown_site_404(self, client):
        with _patch_sites({}):
            r = client.post("/api/scraper/duplicates", json={"site_name": "Nope"})
        assert r.status_code == 404

    def test_fuzzy_duplicates_grouped(self, client, site_with_posts):
        sites = {"TestSite": {"wp_url": "https://example.com", "username": "u", "app_password": "p"}}
        with _patch_sites(sites), \
             patch("modules.news_scraper.routes._make_wp_client", return_value=FakeWpClient(posts=site_with_posts)):
            r = client.post("/api/scraper/duplicates", json={"site_name": "TestSite"})
        assert r.status_code == 200
        data = r.get_json()
        assert data["ok"] is True
        assert data["total_posts"] == 6
        # 2 fuzzy groups: "Harga Emas Naik" (3 posts) + "IHSG Menguat" (2 posts)
        assert len(data["duplicates"]) == 2
        by_count = {d["count"]: d for d in data["duplicates"]}
        assert sorted(by_count) == [2, 3]
        assert sorted(by_count[3]["post_ids"]) == [1, 2, 3]
        assert sorted(by_count[2]["post_ids"]) == [4, 5]

    def test_html_entities_and_tags_normalized(self, client):
        posts = [
            make_post(1, "Kenaikan &amp; Penurunan"),
            make_post(2, "<b>kenaikan &amp; penurunan</b>"),
            make_post(3, "Kenaikan & Penurunan"),
        ]
        sites = {"TestSite": {"wp_url": "https://example.com", "username": "u", "app_password": "p"}}
        with _patch_sites(sites), \
             patch("modules.news_scraper.routes._make_wp_client", return_value=FakeWpClient(posts=posts)):
            r = client.post("/api/scraper/duplicates", json={"site_name": "TestSite"})
        data = r.get_json()
        assert len(data["duplicates"]) == 1
        assert data["duplicates"][0]["count"] == 3
        assert sorted(data["duplicates"][0]["post_ids"]) == [1, 2, 3]

    def test_no_duplicates(self, client):
        posts = [make_post(1, "Satu"), make_post(2, "Dua")]
        sites = {"TestSite": {"wp_url": "https://example.com", "username": "u", "app_password": "p"}}
        with _patch_sites(sites), \
             patch("modules.news_scraper.routes._make_wp_client", return_value=FakeWpClient(posts=posts)):
            r = client.post("/api/scraper/duplicates", json={"site_name": "TestSite"})
        data = r.get_json()
        assert data["duplicates"] == []
        assert data["total_posts"] == 2

    def test_login_failure_401(self, client):
        sites = {"TestSite": {"wp_url": "https://example.com", "username": "u", "app_password": "p"}}
        bad = FakeWpClient()
        bad.login = lambda: (False, "auth denied")
        with _patch_sites(sites), \
             patch("modules.news_scraper.routes._make_wp_client", return_value=bad):
            r = client.post("/api/scraper/duplicates", json={"site_name": "TestSite"})
        assert r.status_code == 401
        assert r.get_json()["duplicates"] == []


# ---------------------------------------------------------------------------
# delete_all_posts
# ---------------------------------------------------------------------------

class TestDeleteAllPosts:
    SITES = {"TestSite": {"wp_url": "https://example.com", "username": "u", "app_password": "p"}}

    def _do(self, client, posts, body):
        with _patch_sites(self.SITES), \
             patch("modules.news_scraper.routes._make_wp_client", return_value=FakeWpClient(posts=posts)), \
             patch("modules.news_scraper.routes._log_scraper"):
            return client.post("/api/scraper/duplicates/delete-all", json=body)

    def test_requires_site_name(self, client):
        r = client.post("/api/scraper/duplicates/delete-all", json={"confirm": "HAPUS SEMUA"})
        assert r.status_code == 400

    def test_requires_confirm_token(self, client):
        r = self._do(client, [make_post(1, "A")], {"site_name": "TestSite"})
        assert r.status_code == 400
        assert "confirm" in r.get_json()["error"].lower()

    def test_wrong_confirm_token_rejected(self, client):
        r = self._do(client, [make_post(1, "A")], {"site_name": "TestSite", "confirm": "hapus semua!!!"})
        assert r.status_code == 400

    def test_unknown_site_404(self, client):
        with _patch_sites({}):
            r = client.post("/api/scraper/duplicates/delete-all",
                            json={"site_name": "Nope", "confirm": "HAPUS SEMUA"})
        assert r.status_code == 404

    def test_deletes_all_posts_concurrently(self, client):
        posts = [make_post(i, f"Post {i}") for i in range(1, 26)]
        r = self._do(client, posts, {"site_name": "TestSite", "confirm": "HAPUS SEMUA"})
        assert r.status_code == 200
        data = r.get_json()
        assert data["ok"] is True
        assert data["deleted"] == 25
        assert data["total_posts"] == 25
        assert data["truncated"] is False

    def test_cap_blocks_deletion(self, client):
        posts = [make_post(i, f"Post {i}") for i in range(1, 11)]
        r = self._do(client, posts, {"site_name": "TestSite", "confirm": "HAPUS SEMUA", "cap": 5})
        assert r.status_code == 400
        data = r.get_json()
        assert data["deleted"] == 0
        assert data["total_posts"] == 10
        assert data["cap"] == 5

    def test_cap_raisable_and_clamped(self, client):
        posts = [make_post(i, f"Post {i}") for i in range(1, 11)]
        # cap 10 passes
        r = self._do(client, posts, {"site_name": "TestSite", "confirm": "HAPUS SEMUA", "cap": 10})
        assert r.status_code == 200
        assert r.get_json()["deleted"] == 10
        # cap above ceiling is clamped (invalid JSON type falls back to default too)
        r2 = self._do(client, posts, {"site_name": "TestSite", "confirm": "HAPUS SEMUA", "cap": 99999})
        assert r2.status_code == 200

    def test_empty_site_ok(self, client):
        r = self._do(client, [], {"site_name": "TestSite", "confirm": "HAPUS SEMUA"})
        assert r.status_code == 200
        data = r.get_json()
        assert data["deleted"] == 0
        assert data["total_posts"] == 0

    def test_structured_log_entry_records_who_and_what(self, client):
        """DELETE_ALL writes a structured entry (category/msg/extra.user) so the
        activity log modal can show who deleted what."""
        posts = [make_post(i, f"Post {i}") for i in range(1, 6)]
        logged = []
        def _capture(message, user='unknown'):
            logged.append((message, user))
        with _patch_sites(self.SITES), \
             patch("modules.news_scraper.routes._make_wp_client", return_value=FakeWpClient(posts=posts)), \
             patch("modules.news_scraper.routes._log_scraper", side_effect=_capture):
            client.post("/api/scraper/duplicates/delete-all",
                        json={"site_name": "TestSite", "confirm": "HAPUS SEMUA"})
        assert len(logged) == 1
        entry, user = logged[0]
        assert isinstance(entry, dict)
        assert entry["category"] == "DELETE_ALL"
        assert entry["level"] == "INFO"
        assert "5/5" in entry["msg"]
        assert entry["extra"]["site"] == "TestSite"
        assert entry["extra"]["deleted"] == 5
        assert entry["extra"]["failed"] == 0
        # actor is recorded both top-level and in extra
        assert user == "tester"
        assert entry["extra"]["user"] == "tester"

    def test_partial_failure_log_level_is_warning(self, client):
        posts = [make_post(1, "A"), make_post(2, "B")]

        class FlakyClient(FakeWpClient):
            def request(self, method, url, nonce, **kwargs):
                pid = int(url.rstrip("/").rsplit("/", 1)[-1])
                if pid == 2:
                    return FakeResp(500, {})
                return super().request(method, url, nonce, **kwargs)

        logged = []
        with _patch_sites(self.SITES), \
             patch("modules.news_scraper.routes._make_wp_client", return_value=FlakyClient(posts=posts)), \
             patch("modules.news_scraper.routes._log_scraper", side_effect=lambda m, u="unknown": logged.append(m)):
            client.post("/api/scraper/duplicates/delete-all",
                        json={"site_name": "TestSite", "confirm": "HAPUS SEMUA"})
        assert logged[0]["level"] == "WARNING"
        assert logged[0]["extra"]["failed"] == 1

    def test_partial_failure_counted(self, client):
        posts = [make_post(1, "A"), make_post(2, "B")]

        class FlakyClient(FakeWpClient):
            def request(self, method, url, nonce, **kwargs):
                pid = int(url.rstrip("/").rsplit("/", 1)[-1])
                if pid == 2:
                    return FakeResp(500, {})
                return super().request(method, url, nonce, **kwargs)

        with _patch_sites(self.SITES), \
             patch("modules.news_scraper.routes._make_wp_client", return_value=FlakyClient(posts=posts)), \
             patch("modules.news_scraper.routes._log_scraper"):
            r = client.post("/api/scraper/duplicates/delete-all",
                            json={"site_name": "TestSite", "confirm": "HAPUS SEMUA"})
        data = r.get_json()
        assert data["ok"] is True
        assert data["deleted"] == 1
        assert data["total_posts"] == 2
