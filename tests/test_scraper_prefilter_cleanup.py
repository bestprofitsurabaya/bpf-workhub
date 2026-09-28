"""Tests untuk perbaikan anti-duplikat news scraper.

Cakupan:
- Pre-filter upload: paginasi existing posts PINUH (bukan cuma 1000 terbaru)
- Dedup intra-batch: judul sama dalam satu batch hanya di-create 1x
- Fallback search WP saat paginasi existing tidak lengkap (site besar)
- /api/scraper/duplicates/delete: keep_ids dilindungi (tidak pernah terhapus)
- /api/scraper/duplicates/cleanup: bulk hapus duplikat keep-terbaru + limit

Mengikuti pola test_scraper_duplicates.py / test_scraper_e2e.py: Flask app
mandiri + WpClient palsu, tanpa DB / WordPress nyata.
"""
import json
from unittest.mock import MagicMock, patch

import flask
import pytest

from tests.test_scraper_duplicates import FakeResp, FakeWpClient, make_post


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def norm(title):
    from modules.news_scraper.seo_optimizer import normalize_title
    return normalize_title(title)


def article(title, content="Isi artikel cukup panjang untuk melewati gerbang kualitas. " * 3):
    return {"title": title, "content": content, "link": f"https://s.example/{norm(title)}",
            "source": "newsmaker", "publish_date": "2026-09-28", "publish_time": "08:00"}


SITES = {"TestSite": {"wp_url": "https://example.com/wp-json/wp/v2/posts",
                      "username": "u", "app_password": "p"}}


def _patch_sites(sites):
    return patch("modules.news_scraper.routes._load_json",
                 side_effect=lambda path, default: sites if path.endswith("wp_sites.json") else default)


UPLOAD_PATCHES = [
    "modules.news_scraper.routes._log_scraper",
    "modules.news_scraper.routes._save_upload_history",
    "modules.news_scraper.routes.ping_sitemap",
    "modules.news_scraper.routes.track_performance",
    "modules.news_scraper.routes._sl",
    "modules.news_scraper.routes._set_progress",
]


def run_upload(client, articles, settings=None):
    """Panggil _upload_articles_to_site dengan semua efek samping di-patch."""
    from modules.news_scraper.routes import _upload_articles_to_site
    patches = [patch(p) for p in UPLOAD_PATCHES] + [_patch_sites(SITES)]
    with flask.Flask(__name__).test_request_context():
        with patch("modules.news_scraper.routes._make_wp_client", return_value=client):
            for p in patches:
                p.start()
            try:
                return _upload_articles_to_site("TestSite", articles, settings or {
                    "backlinks": False, "seo_optimize": False, "static_tags": ""
                })
            finally:
                for p in patches:
                    p.stop()


class SearchCapableClient(FakeWpClient):
    """FakeWpClient + search_posts + create_post/update_post."""

    def __init__(self, posts=None, searchable=None):
        super().__init__(posts=posts)
        self.searchable = searchable or []   # post yang bisa ditemukan search
        self.created = []
        self.updated = []

    def search_posts(self, query, nonce, **kwargs):
        q = norm(query)
        hits = [p for p in self.searchable if norm(p["title"]["rendered"]) == q]
        return FakeResp(200, hits)

    def create_post(self, data, nonce, **kwargs):
        self.created.append(data.get("title"))
        pid = 9000 + len(self.created)
        return FakeResp(201, {"id": pid})

    def update_post(self, post_id, data, nonce, **kwargs):
        self.updated.append(post_id)
        return FakeResp(200, {"id": post_id})


# ---------------------------------------------------------------------------
# Pre-filter upload
# ---------------------------------------------------------------------------

class TestPrefilterUpload:
    def test_old_post_beyond_1000_detected(self):
        """Artikel yang cocok dengan post LAMA (di luar 1000 terbaru) tetap
        terdeteksi existing — paginasi harus penuh, bukan cuma 10 halaman."""
        # 350 post existing; duplikatnya di urutan 300 (halaman 4 dgn per_page 100)
        posts = [make_post(i, f"Post Lama {i}") for i in range(1, 301)]
        posts.append(make_post(301, "Berita Emas Hari Ini"))
        posts += [make_post(i, f"Post Lama {i}") for i in range(302, 351)]
        c = SearchCapableClient(posts=posts)

        result = run_upload(c, [article("Berita Emas Hari Ini")])

        assert result["ok"] is True
        assert result["skipped_existing"] == 1
        assert result["new_posts"] == 0
        assert c.created == []          # TIDAK membuat post baru (dulu: duplikat!)

    def test_intra_batch_duplicate_created_once(self):
        """Judul sama 2x dalam satu batch → hanya 1 create, sisanya dedup."""
        c = SearchCapableClient(posts=[make_post(1, "Sudah Ada Di WP")])
        articles = [article("Judul Ganda Uji"), article("Judul Ganda Uji")]

        result = run_upload(c, articles)

        assert result["ok"] is True
        assert result["new_posts"] == 1
        assert len(c.created) == 1
        assert c.created[0] == "Judul Ganda Uji"

    def test_fallback_search_when_pagination_incomplete(self):
        """Paginasi existing tidak lengkap (site besar) → search per-artikel
        menangkap duplikat yang tidak ada di hasil paginasi."""
        from modules.news_scraper.routes import _upload_articles_to_site
        visible = [make_post(i, f"Terbaru {i}") for i in range(1, 101)]
        old_dupe = make_post(555, "Berita Perak Anjlok")
        c = SearchCapableClient(posts=visible, searchable=[old_dupe])

        patches = [patch(p) for p in UPLOAD_PATCHES] + [
            _patch_sites(SITES),
            patch("modules.news_scraper.routes._fetch_all_posts",
                  return_value=(visible, False)),  # simulasi cap paginasi
        ]
        with flask.Flask(__name__).test_request_context():
            with patch("modules.news_scraper.routes._make_wp_client", return_value=c):
                for p in patches:
                    p.start()
                try:
                    result = _upload_articles_to_site(
                        "TestSite",
                        [article("Berita Perak Anjlok"), article("Artikel Benar Baru")],
                        {"backlinks": False, "seo_optimize": False, "static_tags": ""})
                finally:
                    for p in patches:
                        p.stop()

        assert result["skipped_existing"] == 1
        assert result["new_posts"] == 1
        assert len(c.created) == 1
        assert c.created[0] == "Artikel Benar Baru"

    def test_new_post_registered_for_later_same_title(self):
        """Post yang baru di-create terdaftar di norm_map → artikel berjudul
        sama di belakang batch tidak membuat post kedua."""
        c = SearchCapableClient(posts=[])
        articles = [article("Baru Sekali Uji"), article("Baru Sekali Uji")]

        result = run_upload(c, articles)

        assert result["new_posts"] == 1
        assert len(c.created) == 1


# ---------------------------------------------------------------------------
# delete endpoint: keep_ids protection
# ---------------------------------------------------------------------------

class TestDeleteKeepProtection:
    def test_keep_ids_never_deleted(self, scraper_app, client):
        posts = [make_post(1, "Dup A"), make_post(2, "Dup A"), make_post(3, "Dup A")]
        fake = FakeWpClient(posts=posts)
        with _patch_sites(SITES), \
             patch("modules.news_scraper.routes._make_wp_client", return_value=fake), \
             patch("modules.news_scraper.routes._log_scraper"):
            r = client.post("/api/scraper/duplicates/delete",
                            json={"site_name": "TestSite",
                                  "post_ids": [1, 2, 3], "keep_ids": [1]})
        data = r.get_json()
        assert data["ok"] is True
        assert data["deleted"] == 2
        assert data["protected"] == [1]
        assert sorted(fake.deleted_ids) == [2, 3]


@pytest.fixture
def scraper_app():
    from modules.news_scraper import news_scraper_bp
    app = flask.Flask(__name__)
    app.config["TESTING"] = True
    app.secret_key = "test"
    app.register_blueprint(news_scraper_bp)

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


# ---------------------------------------------------------------------------
# cleanup endpoint (bulk keep-newest)
# ---------------------------------------------------------------------------

class TestCleanupDuplicates:
    def _do(self, client, posts, body=None, client_override=None):
        fake = client_override or FakeWpClient(posts=posts)
        with _patch_sites(SITES), \
             patch("modules.news_scraper.routes._make_wp_client", return_value=fake), \
             patch("modules.news_scraper.routes._log_scraper"):
            r = client.post("/api/scraper/duplicates/cleanup",
                            json={"site_name": "TestSite", **(body or {})})
        return r.get_json(), fake

    def test_bulk_cleanup_keeps_newest(self, client):
        d1 = dict(make_post(1, "A"), date="2026-09-01T10:00:00")   # lama
        d2 = dict(make_post(2, "A"), date="2026-09-05T10:00:00")   # TERBARU → keep
        d3 = dict(make_post(3, "A"), date="2026-08-20T10:00:00")   # paling lama
        u1 = make_post(4, "Unik")
        data, fake = self._do(client, [d1, d2, d3, u1])
        assert data["ok"] is True
        assert data["deleted"] == 2
        assert data["duplicate_groups"] == 1
        assert data["remaining"] == 0
        assert sorted(fake.deleted_ids) == [1, 3]
        assert 2 not in fake.deleted_ids

    def test_limit_defers_remaining(self, client):
        # 4 post duplikat "A" → grup berisi 4, yang dihapus 3 (keep terbaru),
        # limit 2 → 2 dihapus sekarang, 1 tersisa.
        posts = [dict(make_post(i, "A"), date=f"2026-09-{10 + i:02d}T10:00:00") for i in range(1, 5)]
        data, fake = self._do(client, posts, {"limit": 2})
        assert data["deleted"] == 2
        assert data["remaining"] == 1
        assert len(fake.deleted_ids) == 2

    def test_no_duplicates_deletes_nothing(self, client):
        data, fake = self._do(client, [make_post(1, "A"), make_post(2, "B")])
        assert data["deleted"] == 0
        assert data["duplicate_groups"] == 0
        assert fake.deleted_ids == []

    def test_unknown_site_404(self, client):
        with patch("modules.news_scraper.routes._load_json", return_value={}):
            r = client.post("/api/scraper/duplicates/cleanup",
                            json={"site_name": "Nope"})
        assert r.status_code == 404

    def test_requires_site_name(self, client):
        r = client.post("/api/scraper/duplicates/cleanup", json={})
        assert r.status_code == 400
