"""Test pembersihan konten scraper & gerbang kualitas H2 (v2.39.5).

Kasus nyata: artikel Bahlil & Reli Minyak (11 Sep 2026) di
best-profit-futures-surabaya.com memuat H2 fragmen ucapan narasumber,
boilerplate "SCROLL TO CONTINUE WITH CONTENT", dan paragraf terpotong
yang berdampingan dengan kelengkapannya.
"""

import random

from modules.news_scraper.scraper_engine import clean_article_content
from modules.news_scraper.seo_optimizer import (
    _subheading_candidate,
    build_article_html,
    rewrite_content,
)


# ---------------------------------------------------------------------------
# clean_article_content — boilerplate & artefak paginasi
# ---------------------------------------------------------------------------

class TestCleanArticleContent:

    def test_boilerplate_scroll_dibuang(self):
        a = {'content': 'Paragraf pembuka berita yang cukup panjang.\n\n'
                        'SCROLL TO CONTINUE WITH CONTENT\n\n'
                        'Paragraf penutup berita yang juga cukup panjang.'}
        clean_article_content(a)
        assert 'SCROLL TO CONTINUE' not in a['content']
        assert 'Paragraf pembuka' in a['content']
        assert 'Paragraf penutup' in a['content']

    def test_fragmen_terpotong_dibuang_kelengkapannya_menang(self):
        frag = '"Bayangkan, orang dunia lagi susah, kita'
        utuh = ('"Bayangkan, orang dunia lagi susah, kita masih memilih-milih. '
                'Saya lebih mementingkan kepentingan rakyat daripada kepentingan lain.')
        a = {'content': f'{frag}\n\n{utuh}\n\nParagraf lain yang utuh.'}
        clean_article_content(a)
        assert a['content'] == f'{utuh}\n\nParagraf lain yang utuh.'

    def test_duplikat_persis_dibuang(self):
        a = {'content': 'Paragraf A yang cukup panjang.\n\n'
                        'Paragraf B yang cukup panjang.\n\n'
                        'Paragraf B yang cukup panjang.'}
        clean_article_content(a)
        assert a['content'].count('Paragraf B') == 1

    def test_konten_bersih_tak_berubah(self):
        clean_text = 'Paragraf satu yang cukup panjang.\n\nParagraf dua yang cukup panjang.'
        a = {'content': clean_text}
        clean_article_content(a)
        assert a['content'] == clean_text

    def test_idempoten(self):
        a = {'content': 'SCROLL TO CONTINUE WITH CONTENT\n\n'
                        '"Fragmen ucapan\n\n'
                        '"Fragmen ucapan yang dilanjutkan hingga kalimat selesai di sini.'}
        clean_article_content(a)
        once = a['content']
        clean_article_content(a)
        assert a['content'] == once


# ---------------------------------------------------------------------------
# _subheading_candidate — gerbang kualitas H2
# ---------------------------------------------------------------------------

class TestSubheadingCandidate:

    def test_fragmen_kutipan_ditolak(self):
        para = ('"Bayangkan, orang dunia lagi susah, kita masih memilih-milih dan '
                'mencari skala prioritas mana yang bisa didatangkan dari sumber energi.')
        assert _subheading_candidate(para) == ''

    def test_fallback_klausa_koma(self):
        para = ('Risiko geopolitik tetap menjadi penopang utama, sementara Iran tetap '
                'memaparkan kesiapan melanjutkan konflik meski menghadapi tekanan ekonomi berat.')
        assert _subheading_candidate(para) == 'Risiko geopolitik tetap menjadi penopang utama'

    def test_kalimat_panjang_tanpa_koma_ditolak(self):
        # >80 karakter tanpa koma → tidak ada klausa layak → tanpa H2
        para = ('Pembelian minyak dari Rusia merupakan bagian dari kontrak kerja sama '
                'antarpemerintah yang dilanjutkan skema bisnis. Kalimat kedua di sini.')
        assert _subheading_candidate(para) == ''

    def test_kalimat_pendek_ekstrem_ditolak(self):
        # <15 karakter — terlalu pendek untuk heading bermakna
        assert _subheading_candidate('Ini pendek. Tapi paragrafnya tetap panjang di sini ya.') == ''


# ---------------------------------------------------------------------------
# build_article_html — integrasi (kasus artikel Bahlil)
# ---------------------------------------------------------------------------

class TestBuildArticleHtmlIntegration:

    BAHLIL_CONTENT = (
        'Menteri ESDM Bahlil Lahadalia buka-bukaan perkembangan impor minyak dari '
        'Rusia yang kini mulai berjalan sesuai kontrak kerja sama pemerintah.\n\n'
        'SCROLL TO CONTINUE WITH CONTENT\n\n'
        '"Bayangkan, orang dunia lagi susah, kita\n\n'
        '"Bayangkan, orang dunia lagi susah, kita masih memilih-milih. Saya lebih '
        'mementingkan kepentingan rakyat daripada kepentingan lain, kata Bahlil.\n\n'
        'Dalam catatan detikcom, Indonesia berencana mengimpor minyak dari Rusia '
        'sebanyak 150 juta barel usai pertemuan Presiden Prabowo dan Presiden Putin.'
    )

    def _html(self, content):
        # Simulasikan alur produksi: fetch_article_content membersihkan dulu,
        # baru rewrite & build — seperti routes.py
        a = {'content': content}
        clean_article_content(a)
        return build_article_html('Judul Berita Uji', a['content'], {}, '2026-09-11', '16:07')

    def test_tanpa_h2_fragmen_kutipan(self):
        html = self._html(self.BAHLIL_CONTENT)
        assert 'quot-' not in html  # slug H2 bekas tanda kutip tak boleh ada lagi

    def test_tanpa_boilerplate(self):
        html = self._html(self.BAHLIL_CONTENT)
        assert 'SCROLL TO CONTINUE' not in html

    def test_fragmen_tak_duplikat(self):
        html = self._html(self.BAHLIL_CONTENT)
        body_start = html.find('Bayangkan')
        assert body_start == -1 or html.find('Bayangkan', body_start + 1) == -1

    def test_isi_utuh_tetap_terbit(self):
        html = self._html(self.BAHLIL_CONTENT)
        assert 'masih memilih-milih' in html
        assert '150 juta barel' in html

    def test_disclaimer_resmi_tetap_ada(self):
        html = self._html(self.BAHLIL_CONTENT)
        assert 'Disclaimer' in html


# ---------------------------------------------------------------------------
# rewrite_content — guard gramatika sinonim
# ---------------------------------------------------------------------------

class TestSynonymGuards:

    def test_tetap_menjadi_tak_berubah_jadi(self):
        # "berubah jadi" dihapus dari opsi 'menjadi' — kasus artikel Reli Minyak
        content = ('Risiko geopolitik tetap menjadi penopang utama bagi harga minyak '
                   'saat ini, sementara permintaan global melemah. ' * 4)
        for _ in range(20):
            random.seed()
            out = rewrite_content(content, 'Reli Minyak')
            assert 'berubah jadi' not in out
            assert 'tetap' in out

    def test_terhadap_tak_jadi_bagi_beruntun(self):
        # 'bagi' dihapus dari opsi 'terhadap' — "serangan bagi infrastruktur" salah makna
        content = ('Serangan Ukraina terhadap infrastruktur energi Rusia terus berlanjut '
                   'sehingga produksi turun. ' * 4)
        for _ in range(20):
            random.seed()
            out = rewrite_content(content, 'Serangan Ukraina')
            # 'terhadap' dilindungi judul ATAU diganti 'kepada' — 'bagi' tak mungkin
            assert 'bagi' not in out or 'terhadap' in out
