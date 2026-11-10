"""Inventaris IT (v2.78.0) — klasifikasi, tag, label PDF, impor, scoping.

Unit test murni (tanpa DB/jaringan): memakai fungsi publik modul
`it_classifier`, `routes_it_assets`, dan `it_inventory_schema`.
"""
import io
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from modules.it_classifier import (  # noqa: E402
    classify, is_locally_administered, mac_vendor, normalize_mac,
)
from modules.routes_it_assets import (  # noqa: E402
    _clean_fields, _dedupe_key, _expand_cidr, _label_pdf, _next_tag,
    _serialize, _tag_prefix, _validate_import_rows, _loads, _asset_report_pdf,
)
from modules.it_inventory_schema import (  # noqa: E402
    IT_CATEGORIES, IT_CATEGORY_CODES, IT_CONDITIONS, IT_STATUSES,
)


class FakeCursor:
    """Cursor minimal untuk fungsi yang hanya butuh fetchone()."""

    def __init__(self, row=None, log=None):
        self.row = row
        self.log = log if log is not None else []

    def execute(self, sql, params=None):
        self.log.append((sql, params))

    def fetchone(self):
        return self.row


class TestMacHelpers:
    def test_normalize_valid(self):
        assert normalize_mac('aa-bb-cc-dd-ee-ff') == 'AA:BB:CC:DD:EE:FF'
        assert normalize_mac('aabbccddeeff') == 'AA:BB:CC:DD:EE:FF'

    def test_normalize_invalid(self):
        assert normalize_mac('') is None
        assert normalize_mac('aa:bb:cc') is None
        assert normalize_mac(None) is None

    def test_locally_administered(self):
        # 0x86 = 1000 0110 → bit U/L (0x02) menyala
        assert is_locally_administered('86:E2:42:A9:CF:EE') is True
        # 0x28 = 0010 1000 → bit U/L mati (vendor asli)
        assert is_locally_administered('28:D0:F5:00:00:01') is False

    def test_vendor_lookup_offline(self):
        # Fallback OUI lokal harus tetap menjawab meski netaddr tidak dipasang.
        assert mac_vendor('28:D0:F5:00:00:01').lower().startswith('ruijie')
        assert mac_vendor('90:2B:34:00:00:01').lower().startswith('giga')

    def test_vendor_unknown(self):
        assert mac_vendor('') == ''


class TestClassifier:
    def test_printer_by_port(self):
        r = classify(ip='192.168.2.50', mac='00:1A:2B:00:00:01', ports=[9100])
        assert r['category_suggest'] == 'printer'
        assert r['confidence'] >= 0.70
        assert r['is_asset'] is True
        assert any('9100' in x for x in r['reasons'])

    def test_pc_by_smb_and_vendor(self):
        r = classify(ip='192.168.2.10', mac='90:2B:34:00:00:01',
                     hostname='FTP-EF', ports=[135, 445, 3389])
        assert r['category_suggest'] == 'pc'
        assert r['confidence'] >= 0.75
        assert r['is_asset'] is True

    def test_network_by_vendor(self):
        r = classify(ip='192.168.2.2', mac='28:D0:F5:00:00:02', ports=[80, 443])
        assert r['category_suggest'] == 'network'
        assert r['is_asset'] is True

    def test_server_by_ssh_and_hostname(self):
        r = classify(ip='192.168.2.31', mac='00:25:11:00:00:01',
                     hostname='nas-bpf', ports=[22, 443])
        assert r['category_suggest'] == 'server'

    def test_cctv_by_port(self):
        r = classify(ip='192.168.2.60', mac='3C:5A:37:00:00:01', ports=[554])
        assert r['category_suggest'] == 'cctv'

    def test_random_mac_without_ports_is_not_asset(self):
        r = classify(ip='192.168.2.120', mac='86:E2:42:A9:CF:EE', ports=[])
        assert r['is_asset'] is False
        assert 'HP' in r['non_asset_reason'] or 'acak' in r['non_asset_reason']

    def test_empty_evidence(self):
        r = classify()
        assert r['is_asset'] is False
        assert r['confidence'] == 0.0


class TestSchemaConstants:
    def test_category_codes_unique(self):
        assert len(IT_CATEGORY_CODES) == len(set(IT_CATEGORY_CODES))
        assert 'pc' in IT_CATEGORY_CODES and 'printer' in IT_CATEGORY_CODES
        assert all(len(c) == 3 and c[2] for c in IT_CATEGORIES)

    def test_status_and_condition_enums(self):
        assert 'disposed' in IT_STATUSES
        assert set(IT_CONDITIONS) == {'baik', 'rusak_ringan', 'rusak_berat'}


class TestTagGeneration:
    def test_prefix(self):
        assert _tag_prefix('sby', 'pc') == 'SBY-IT-PC-'

    def test_first_tag(self):
        cur = FakeCursor(row=None)
        assert _next_tag(cur, 'SBY', 'pc') == 'SBY-IT-PC-0001'

    def test_increment_from_tuple(self):
        cur = FakeCursor(row=('SBY-IT-PC-0007',))
        assert _next_tag(cur, 'SBY', 'pc') == 'SBY-IT-PC-0008'

    def test_increment_from_dict(self):
        cur = FakeCursor(row={'asset_tag': 'SBY-IT-LAPTOP-0042'})
        assert _next_tag(cur, 'SBY', 'laptop') == 'SBY-IT-LAPTOP-0043'


class TestCidr:
    def test_slash_24(self):
        ips = _expand_cidr('192.168.2.0/24')
        assert len(ips) == 254
        assert ips[0] == '192.168.2.1'
        assert ips[-1] == '192.168.2.254'

    def test_slash_30(self):
        assert _expand_cidr('10.0.0.0/30') == ['10.0.0.1', '10.0.0.2']

    def test_invalid_prefix(self):
        with pytest.raises(ValueError):
            _expand_cidr('10.0.0.0/8')


class TestCleanFields:
    def test_category_required(self):
        with pytest.raises(ValueError):
            _clean_fields({})

    def test_unknown_category(self):
        with pytest.raises(ValueError):
            _clean_fields({'category': 'spaceship'})

    def test_normalizes_mac_and_upper(self):
        out = _clean_fields({'category': 'pc', 'mac_address': 'aa-bb-cc-dd-ee-ff'})
        assert out['mac_address'] == 'AA:BB:CC:DD:EE:FF'

    def test_invalid_date(self):
        with pytest.raises(ValueError):
            _clean_fields({'category': 'pc', 'purchase_date': '31/12/2026'})

    def test_partial_update_without_category(self):
        out = _clean_fields({'location_room': 'Lantai 2'}, partial=True)
        assert out == {'location_room': 'Lantai 2'}

    def test_unknown_status_rejected(self):
        with pytest.raises(ValueError):
            _clean_fields({'category': 'pc', 'status': 'kadaluarsa'})


class TestImportValidation:
    def test_alias_mapping_and_auto_tag(self):
        rows = [{
            'kategori': 'Laptop', 'merek': 'Lenovo', 'tipe': 'T14',
            'sn': 'PF123', 'kondisi': 'Baik', 'ruangan': 'Lantai 3',
            'pic': 'Budi', 'garansi': '2027-12-31', 'harga': '15000000',
        }]
        out = _validate_import_rows(rows)
        assert not out['errors']
        item = out['valid'][0]
        assert item['tag'] == ''
        assert item['fields']['category'] == 'laptop'
        assert item['fields']['brand'] == 'Lenovo'
        assert item['fields']['assigned_to'] == 'Budi'
        assert item['fields']['warranty_until'] == '2027-12-31'

    def test_invalid_category_reported(self):
        out = _validate_import_rows([{'kategori': 'kendaraan'}])
        assert out['valid'] == []
        assert out['errors'][0]['row'] == 2

    def test_empty_rows_skipped(self):
        out = _validate_import_rows([{}, {'kategori': ''}])
        assert out['valid'] == [] and out['errors'] == []


class TestSerialization:
    def test_json_columns_parsed(self):
        row = {
            'asset_tag': 'SBY-IT-PC-0001',
            'specs': '{"ram_gb": 16}',
            'reasons': '["port 445"]',
        }
        out = _serialize(row)
        assert out['specs'] == {'ram_gb': 16}
        assert out['reasons'] == ['port 445']

    def test_loads_accepts_dict_and_none(self):
        assert _loads({'a': 1}) == {'a': 1}
        assert _loads(None, 'x') == 'x'
        assert _loads('bukan json', 'fallback') == 'fallback'


class TestDedupeKey:
    def test_prefers_mac(self):
        assert _dedupe_key('SBY', 'AA:BB:CC:DD:EE:FF', '10.0.0.1') == 'SBY|AA:BB:CC:DD:EE:FF'

    def test_falls_back_to_ip(self):
        assert _dedupe_key('SBY', '', '10.0.0.1') == 'SBY|ip:10.0.0.1'


class TestLabelPdf:
    ASSETS = [
        {'id': 1, 'asset_tag': 'SBY-IT-PC-0001', 'category': 'pc',
         'brand': 'Dell', 'model': 'OptiPlex', 'location_room': 'Lantai 2'},
    ]

    def test_pdf_generated(self):
        buf = _label_pdf(self.ASSETS, 'a4-24', 'https://contoh.local')
        data = buf.getvalue()
        assert data.startswith(b'%PDF')
        assert len(data) > 1000

    def test_multi_page(self):
        assets = [
            {'id': i, 'asset_tag': f'SBY-IT-PC-{i:04d}', 'category': 'pc',
             'brand': 'Dell', 'model': 'X', 'location_room': ''}
            for i in range(1, 31)
        ]
        buf = _label_pdf(assets, 'a4-24')
        data = buf.getvalue()
        # 30 label / 24 per halaman = 2 halaman
        assert data.count(b'/Type /Page') >= 2 or b'/Count 2' in data

    def test_unknown_layout(self):
        with pytest.raises(ValueError):
            _label_pdf(self.ASSETS, 'a4-999')

    def test_fallback_payload_without_base_url(self):
        buf = _label_pdf(self.ASSETS, 'a4-24', '')
        assert buf.getvalue().startswith(b'%PDF')


class TestReportPdf:
    ROWS = [
        {'id': 1, 'asset_tag': 'SBY-IT-PC-0001', 'category': 'pc', 'brand': 'Dell',
         'model': 'OptiPlex 7080', 'status': 'aktif', 'cond': 'baik',
         'location_room': 'Lantai 2 - Trading', 'assigned_to': 'Budi',
         'warranty_until': '2026-12-31'},
        {'id': 2, 'asset_tag': 'SBY-IT-PRINTER-0001', 'category': 'printer',
         'brand': 'Epson', 'model': 'L3210', 'status': 'service',
         'cond': 'rusak_ringan', 'location_room': 'Front Office',
         'assigned_to': '', 'warranty_until': None},
    ]

    def test_report_generated(self):
        buf = _asset_report_pdf(self.ROWS, 'SBY', 'Tester')
        data = buf.getvalue()
        assert data.startswith(b'%PDF')
        assert len(data) > 800

    def test_report_empty_rows_still_valid(self):
        buf = _asset_report_pdf([], 'BDG', 'Tester')
        assert buf.getvalue().startswith(b'%PDF')
