"""ID Fingerprint & ID BPF FirstWork (v2.83.0).

Yang diuji (murni fungsi — tanpa DB):
1. Pemetaan seri counter sheet -> ID tervalidasi: seri tak dikenal / seri
   kembar tidak pernah menghasilkan config yang memetakan dua ID ke satu kolom.
2. Kedua counter sheet (kolom B '28161' & kolom C '6495') dipertahankan oleh
   _normalize_sheet_row — dulu counter kedua dibuang sehingga tidak bisa
   di-backfill.
3. Nilai seri B/C dibaca dari baris ternormalisasi sesuai pemetaan aktif.
4. Nomor ID dari input traineer divalidasi (angka > 0, bukan teks aneh).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from modules import routes_first_work as fw


class TestIdConfigParsing:
    def test_default_mapping_b_fingerprint_c_bpf(self):
        cfg = fw._parse_id_config('')
        assert cfg['fingerprint_series'] == 'B'
        assert cfg['bpf_series'] == 'C'

    def test_invalid_json_falls_back_to_default(self):
        cfg = fw._parse_id_config('bukan-json{')
        assert cfg['fingerprint_series'] == 'B'
        assert cfg['bpf_series'] == 'C'

    def test_explicit_mapping_kept(self):
        cfg = fw._parse_id_config('{"fingerprint_series":"C","bpf_series":"B"}')
        assert cfg['fingerprint_series'] == 'C'
        assert cfg['bpf_series'] == 'B'

    def test_unknown_series_falls_back(self):
        cfg = fw._parse_id_config('{"fingerprint_series":"X","bpf_series":"B"}')
        assert cfg['fingerprint_series'] == 'B'
        assert cfg['bpf_series'] != 'B'

    def test_same_series_is_split(self):
        """Dua ID tidak boleh mengalir dari kolom counter yang sama."""
        cfg = fw._parse_id_config('{"fingerprint_series":"B","bpf_series":"B"}')
        assert cfg['fingerprint_series'] != cfg['bpf_series']

    def test_lowercase_series_normalised(self):
        cfg = fw._parse_id_config('{"fingerprint_series":"c","bpf_series":"b"}')
        assert cfg['fingerprint_series'] == 'C'
        assert cfg['bpf_series'] == 'B'


class TestSheetCounters:
    def _row(self, seq1='28162', seq2='6496'):
        headers = ['timestamp', '28161', '6495', 'namalengkap']
        row = ['01/10/2025 17:04:59', seq1, seq2, 'Contoh Nama']
        return fw._normalize_sheet_row(headers, row, 0)

    def test_both_counters_kept(self):
        row = self._row()
        assert row['sheet_seq1'] == '28162'
        assert row['sheet_seq2'] == '6496'

    def test_legacy_sheet_seq_still_prefers_first_counter(self):
        assert self._row()['sheet_seq'] == '28162'

    def test_series_value_by_mapping(self):
        row = self._row(seq1='29992', seq2='8326')
        cfg = fw._parse_id_config('{"fingerprint_series":"C","bpf_series":"B"}')
        assert fw._sheet_series_value(row, cfg['fingerprint_series']) == 8326
        assert fw._sheet_series_value(row, cfg['bpf_series']) == 29992

    def test_empty_counter_is_none(self):
        row = self._row(seq1='', seq2='bukan-angka')
        assert fw._sheet_series_value(row, 'B') is None
        assert fw._sheet_series_value(row, 'C') is None


class TestIdNumberValidation:
    def test_plain_digits(self):
        assert fw._valid_id_number('29993') == 29993
        assert fw._valid_id_number(29993) == 29993

    def test_junk_rejected(self):
        assert fw._valid_id_number('empat') is None
        assert fw._valid_id_number('12; DROP TABLE x') is None

    def test_zero_and_negative_rejected(self):
        assert fw._valid_id_number('0') is None
        assert fw._valid_id_number('-5') is None

    def test_empty_is_none_not_zero(self):
        assert fw._valid_id_number('') is None
        assert fw._valid_id_number(None) is None
