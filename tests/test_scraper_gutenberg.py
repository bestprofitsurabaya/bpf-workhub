"""Test output Gutenberg-ready scraper — v2.46.4.

Latar: artikel hasil scraper berupa HTML polos tanpa komentar blok
``<!-- wp:... -->`` → WordPress menganggapnya SATU blok Classic → tata
letak "rusak" di editor sampai redaksi menekan "Convert to blocks".
Fix: build_article_html() kini memancarkan blok inti Gutenberg per segmen,
plus meta rank_math_focus_keyword di payload create_post.
"""

import json

from modules.news_scraper.seo_optimizer import (
    build_article_html,
    wp_block,
)
from modules.news_scraper.routes import _focus_keyword_from_title


# ---------------------------------------------------------------------------
# wp_block — pembungkus blok inti
# ---------------------------------------------------------------------------

class TestWpBlock:

    def test_paragraf_jadi_wp_paragraph(self):
        out = wp_block('<p>Halo dunia.</p>')
        assert out.startswith('<!-- wp:paragraph -->')
        assert out.endswith('<!-- /wp:paragraph -->')
        assert '<p>Halo dunia.</p>' in out

    def test_h2_jadi_wp_heading_level_2(self):
        out = wp_block('<h2 id="risiko-geopolitik">Risiko Geopolitik</h2>')
        assert '<!-- wp:heading {"level":2} -->' in out
        assert '<!-- /wp:heading -->' in out

    def test_figure_berimg_jadi_wp_image(self):
        out = wp_block('<figure class="wp-block-image"><img src="https://x/y.jpg"/></figure>')
        assert out.startswith('<!-- wp:image -->')

    def test_figure_tanpa_img_jadi_wp_html(self):
        out = wp_block('<figure><figcaption>tanpa gambar</figcaption></figure>')
        assert out.startswith('<!-- wp:html -->')

    def test_div_jadi_wp_html(self):
        out = wp_block('<div style="color:red;">cta</div>')
        assert out.startswith('<!-- wp:html -->')
        assert out.endswith('<!-- /wp:html -->')

    def test_ul_jadi_wp_list(self):
        out = wp_block('<ul><li>a</li></ul>')
        assert out.startswith('<!-- wp:list -->')

    def test_kosong_mengembalikan_string_kosong(self):
        assert wp_block('') == ''
        assert wp_block(None) == ''

    def test_atribut_tambahan_diserialisasi(self):
        out = wp_block('<p>x</p>', {'align': 'center'})
        assert '<!-- wp:paragraph {"align":"center"} -->' in out


# ---------------------------------------------------------------------------
# build_article_html — artikel kini Gutenberg-ready
# ---------------------------------------------------------------------------

class TestBuildArticleHtmlBlocks:

    CONTENT = (
        'Paragraf pembuka berita yang cukup panjang agar lolos filter panjang.\n\n'
        'Paragraf kedua berita yang juga cukup panjang agar lolos filter panjang.\n\n'
        'Risiko geopolitik tetap menjadi penopang utama, sementara Iran tetap '
        'memaparkan kesiapan melanjutkan konflik meski menghadapi tekanan berat.\n\n'
        'Paragraf penutup berita yang juga cukup panjang agar lolos filter.'
    )

    def _html(self):
        return build_article_html(
            'Judul Berita Uji', self.CONTENT,
            {'category': 'Market', 'source': 'newsmaker'}, '2026-09-30', '08:30')

    def test_mengandung_komentar_blok(self):
        assert '<!-- wp:paragraph -->' in self._html()

    def test_tanpa_div_pembuka_polos(self):
        # Artikel lama dibuka <div style="font-family..."> tanpa blok → classic
        assert self._html().startswith('<!-- wp:')

    def test_disclaimer_jadi_blok(self):
        html = self._html()
        assert '<!-- wp:html -->' in html
        assert '<!-- /wp:html -->' in html
        assert 'Disclaimer' in html

    def test_semua_komentar_blok_berpasangan(self):
        html = self._html()
        opens = html.count('<!-- wp:')
        closes = html.count('<!-- /wp:')
        assert opens >= 5
        assert opens == closes

    def test_h2_jadi_blok_heading(self):
        assert '<!-- wp:heading {"level":2} -->' in self._html()

    def test_konten_isi_tetap_utuh(self):
        html = self._html()
        assert 'Paragraf pembuka' in html
        assert 'Paragraf penutup' in html

    def test_script_tetap_ada_di_blok_html(self):
        # Progress bar dsb. kini di blok wp:html — tetap jalan di front-end
        html = self._html()
        assert 'bpf-progress' in html
        assert '<script>' in html

    def test_semua_blok_valid_json_attrs(self):
        import re as _re
        html = self._html()
        for m in _re.finditer(r'<!-- wp:[a-z]+ ({.*?}) -->', html):
            json.loads(m.group(1))  # tidak boleh raise


# ---------------------------------------------------------------------------
# _focus_keyword_from_title — derivasi fokus keyword Rank Math
# ---------------------------------------------------------------------------

class TestFocusKeywordFromTitle:

    def test_ambil_kata_pertama_yang_bermakna(self):
        assert _focus_keyword_from_title('Harga Emas Antam Naik Hari Ini', 3) == 'Harga Emas Antam'
        assert _focus_keyword_from_title('Harga Emas Antam Naik Hari Ini') == 'Harga Emas Antam Naik'

    def test_stopword_dan_kata_pendek_dilewati(self):
        out = _focus_keyword_from_title('Ia Yang Dan Dari Perusak Pasar Saham')
        assert 'yang' not in out.lower().split()
        assert 'Perusak Pasar' in out

    def test_max_words(self):
        assert len(_focus_keyword_from_title('Satu Dua Tiga Empat Lima Enam', 2).split()) == 2

    def test_kosong_aman(self):
        assert _focus_keyword_from_title('') == ''
        assert _focus_keyword_from_title('dan di ke') == ''

    def test_tanda_baca_dibersihkan(self):
        assert _focus_keyword_from_title('"IHSG" Ditutup Menguat!') == 'IHSG Ditutup Menguat'
