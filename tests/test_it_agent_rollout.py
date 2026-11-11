"""Rollout agen inventaris IT (v2.79) — registry, cakupan, dan penjaga allowlist.

Unit test murni: tidak butuh DB, jaringan, atau Windows. Yang diuji adalah
logika yang menentukan apakah rollout aman dan angka cakupan benar:

- `_agent_host_key` / `_version_tuple` / `_normalize_agent_status`
- `_host_flags` dan `_coverage_payload` (hitungan covered/stale/outdated)
- `_targets_rows` + CSV target (allowlist yang diunduh operator)
- keselarasan versi agen Python vs PowerShell
- penjaga di scripts/deploy_it_agent.ps1: wajib -Targets, batas -MaxHosts,
  tolak CIDR/wildcard, tanpa PsExec/parameter subnet
"""
import os
import re
import sys
from datetime import datetime, timedelta

import pytest
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from modules.it_inventory_schema import _DDL  # noqa: E402
from modules.routes_it_assets import (  # noqa: E402
    AGENT_SCRIPT, AGENT_STALE_DAYS, AGENT_VERSION,
    _agent_host_key, _agent_script_path, _coverage_payload, _host_flags,
    _normalize_agent_status, _targets_csv_response, _targets_rows,
    _version_tuple, register_it_asset_routes,
)

ROOT = os.path.join(os.path.dirname(__file__), '..')
AGENT_PS1 = os.path.join(ROOT, 'scripts', 'it_inventory_agent.ps1')
DEPLOY_PS1 = os.path.join(ROOT, 'scripts', 'deploy_it_agent.ps1')


def _read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


class TestHostKey:
    def test_hostname_dipilih_dan_dinormalkan(self):
        assert _agent_host_key('PC-SBY-01', '192.168.2.10') == 'pc-sby-01'
        assert _agent_host_key('  PC-SBY-02  ', '') == 'pc-sby-02'

    def test_fallback_ip(self):
        assert _agent_host_key('', '192.168.2.10') == 'ip:192.168.2.10'
        assert _agent_host_key(None, ' 10.0.0.5 ') == 'ip:10.0.0.5'

    def test_kosong(self):
        assert _agent_host_key('', '') == ''
        assert _agent_host_key(None, None) == ''

    def test_dipotong_120(self):
        assert len(_agent_host_key('a' * 500, '')) == 120


class TestVersion:
    @pytest.mark.parametrize('value,expected', [
        ('1.1.0', (1, 1, 0)),
        ('v2.10.3', (2, 10, 3)),
        ('1.0', (1, 0)),
        ('', (0,)),
        (None, (0,)),
        ('bukan-versi', (0,)),
    ])
    def test_parse(self, value, expected):
        assert _version_tuple(value) == expected

    def test_urutan_numerik_bukan_leksikal(self):
        assert _version_tuple('1.10.0') > _version_tuple('1.9.9')
        assert _version_tuple('2.0.0') > _version_tuple('1.99.99')

    def test_versi_konstan_masuk_akar(self):
        # AGENT_VERSION harus bisa dibandingkan, bukan string bebas.
        assert _version_tuple(AGENT_VERSION) >= (1, 0, 0)


class TestStatus:
    @pytest.mark.parametrize('value', ['pending', 'installed', 'failed', 'unreachable', 'ignored'])
    def test_status_sah(self, value):
        assert _normalize_agent_status(value) == value

    def test_case_insensitive(self):
        assert _normalize_agent_status('INSTALLED') == 'installed'

    def test_tak_dikenal_dianggap_installed(self):
        assert _normalize_agent_status('apa-saja') == 'installed'
        assert _normalize_agent_status(None) == 'installed'


class TestHostFlags:
    def test_installed_baru_tidak_basi(self):
        now = datetime(2026, 11, 11, 12, 0, 0)
        row = {'deploy_status': 'installed', 'last_report_at': now - timedelta(days=1),
               'agent_version': AGENT_VERSION}
        flags = _host_flags(row, stale_days=7, now=now)
        assert flags['days_since_report'] == 1
        assert flags['is_stale'] is False
        assert flags['outdated'] is False

    def test_laporan_tua_dianggap_basi(self):
        now = datetime(2026, 11, 11, 12, 0, 0)
        row = {'deploy_status': 'installed', 'last_report_at': now - timedelta(days=10),
               'agent_version': AGENT_VERSION}
        flags = _host_flags(row, stale_days=7, now=now)
        assert flags['is_stale'] is True

    def test_tanpa_laporan_dianggap_basi(self):
        row = {'deploy_status': 'installed', 'last_report_at': None, 'agent_version': AGENT_VERSION}
        flags = _host_flags(row, stale_days=7, now=datetime(2026, 11, 11))
        assert flags['days_since_report'] is None
        assert flags['is_stale'] is True

    def test_string_datetime_didukung(self):
        row = {'deploy_status': 'installed', 'last_report_at': '2026-11-10 08:30:00',
               'agent_version': AGENT_VERSION}
        flags = _host_flags(row, stale_days=7, now=datetime(2026, 11, 11, 9, 0, 0))
        assert flags['days_since_report'] == 1
        assert flags['is_stale'] is False

    def test_versi_lama_ditandai_outdated(self):
        row = {'deploy_status': 'installed', 'last_report_at': None, 'agent_version': '0.9.0'}
        assert _host_flags(row)['outdated'] is True


class TestCoverage:
    NOW = datetime(2026, 11, 11, 12, 0, 0)

    def test_hitungan_dasar(self):
        targets = [
            {'asset_tag': 'PC-1', 'hostname': 'PC1', 'ip_address': '10.0.0.1', 'mac_address': ''},
            {'asset_tag': 'PC-2', 'hostname': 'PC2', 'ip_address': '10.0.0.2', 'mac_address': ''},
            {'asset_tag': 'PC-3', 'hostname': '', 'ip_address': '10.0.0.3', 'mac_address': 'AA:BB:CC:00:00:03'},
        ]
        hosts = [
            {'host_key': 'pc1', 'hostname': 'PC1', 'ip': '10.0.0.1', 'mac': '',
             'deploy_status': 'installed', 'agent_version': AGENT_VERSION,
             'last_report_at': self.NOW - timedelta(hours=2)},
        ]
        payload = _coverage_payload(targets, hosts, stale_days=7, now=self.NOW)
        assert payload['targets'] == 3
        assert payload['covered'] == 1
        assert payload['missing'] == 2
        assert payload['percent'] == 33.3
        assert payload['hosts_installed'] == 1
        assert payload['hosts_stale'] == 0
        assert [m['asset_tag'] for m in payload['missing_hosts']] == ['PC-2', 'PC-3']

    def test_cocok_lewat_mac_saja(self):
        targets = [{'asset_tag': 'PC-9', 'hostname': '', 'ip_address': '',
                    'mac_address': 'aa:bb:cc:00:00:09'}]
        hosts = [{'host_key': 'pc9', 'hostname': 'PC9', 'ip': '', 'mac': 'AA:BB:CC:00:00:09',
                  'deploy_status': 'installed', 'agent_version': AGENT_VERSION,
                  'last_report_at': self.NOW}]
        payload = _coverage_payload(targets, hosts, stale_days=7, now=self.NOW)
        assert payload['covered'] == 1
        assert payload['percent'] == 100.0

    def test_host_basi_tidak_menghitung_cakupan(self):
        targets = [{'asset_tag': 'PC-1', 'hostname': 'PC1', 'ip_address': '', 'mac_address': ''}]
        hosts = [{'host_key': 'pc1', 'hostname': 'PC1', 'ip': '', 'mac': '',
                  'deploy_status': 'installed', 'agent_version': AGENT_VERSION,
                  'last_report_at': self.NOW - timedelta(days=30)}]
        payload = _coverage_payload(targets, hosts, stale_days=7, now=self.NOW)
        assert payload['covered'] == 0
        assert payload['hosts_stale'] == 1

    def test_host_failed_tidak_menghitung_cakupan(self):
        targets = [{'asset_tag': 'PC-1', 'hostname': 'PC1', 'ip_address': '', 'mac_address': ''}]
        hosts = [{'host_key': 'pc1', 'hostname': 'PC1', 'ip': '', 'mac': '',
                  'deploy_status': 'failed', 'agent_version': AGENT_VERSION,
                  'last_report_at': self.NOW}]
        payload = _coverage_payload(targets, hosts, stale_days=7, now=self.NOW)
        assert payload['covered'] == 0
        assert payload['hosts_failed'] == 1
        assert payload['hosts_stale'] == 0

    def test_tanpa_target_tidak_division_by_zero(self):
        payload = _coverage_payload([], [], stale_days=7, now=self.NOW)
        assert payload['targets'] == 0
        assert payload['percent'] == 0.0

    def test_ringkasan_field_lengkap(self):
        payload = _coverage_payload([], [], now=self.NOW)
        for key in ('targets', 'covered', 'missing', 'percent', 'stale_days',
                    'hosts_total', 'hosts_installed', 'hosts_stale', 'hosts_failed',
                    'hosts_outdated', 'agent_version', 'missing_hosts', 'hosts'):
            assert key in payload
        assert payload['agent_version'] == AGENT_VERSION
        assert payload['stale_days'] == AGENT_STALE_DAYS


class TestTargets:
    def test_gabungan_dan_dedup(self):
        candidates = [
            {'hostname': 'PC1', 'ip': '10.0.0.1', 'mac': '', 'vendor': 'Dell',
             'category_suggest': 'pc', 'open_ports': '445'},
            {'ip': '10.0.0.2', 'mac': 'AA:BB:CC:00:00:02', 'vendor': 'HP',
             'category_suggest': 'laptop', 'open_ports': '3389'},
        ]
        assets = [
            {'asset_tag': 'SBY-IT-PC-0001', 'hostname': 'PC1', 'ip_address': '10.0.0.1',
             'mac_address': '', 'brand': 'Dell', 'model': 'OptiPlex'},
            {'asset_tag': 'SBY-IT-PC-0002', 'hostname': 'PC3', 'ip_address': '10.0.0.3',
             'mac_address': '', 'brand': 'Lenovo', 'model': 'ThinkCentre'},
            {'asset_tag': 'SBY-IT-PRN-0001', 'hostname': '', 'ip_address': '',
             'mac_address': '', 'brand': 'Epson', 'model': 'L3210'},
        ]
        rows = _targets_rows(candidates, assets, covered_keys=[])
        hosts = [r['host'] for r in rows]
        assert hosts == ['PC1', '10.0.0.2', 'PC3']
        assert rows[0]['source'] == 'discovery'
        assert rows[0]['note'].startswith('Dell')
        assert rows[2]['source'] == 'inventaris'
        assert rows[2]['asset_tag'] == 'SBY-IT-PC-0002'

    def test_target_tercakup_dilewati(self):
        candidates = [
            {'hostname': 'PC1', 'ip': '10.0.0.1', 'mac': '', 'vendor': '', 'category_suggest': 'pc'},
            {'hostname': 'PC2', 'ip': '10.0.0.2', 'mac': '', 'vendor': '', 'category_suggest': 'pc'},
        ]
        rows = _targets_rows(candidates, [], covered_keys=['pc2', '10.0.0.2'])
        assert [r['host'] for r in rows] == ['PC1']

    def test_tanpa_identitas_dilewati(self):
        rows = _targets_rows([{'hostname': '', 'ip': '', 'mac': ''}],
                             [{'asset_tag': 'X'}], covered_keys=[])
        assert rows == []

    def test_csv_target(self):
        rows = [{'host': 'PC1', 'ip': '10.0.0.1', 'mac': '', 'source': 'discovery',
                 'asset_tag': '', 'note': 'Dell, port 445'}]
        app = Flask(__name__)
        with app.app_context():
            resp = _targets_csv_response(rows, 'target.csv')
        body = resp.get_data(as_text=True)
        lines = body.strip().splitlines()
        assert lines[0] == 'host,ip,mac,source,asset_tag,note'
        assert lines[1].startswith('PC1,10.0.0.1,,discovery,,')
        assert resp.headers['Content-Disposition'].endswith('filename=target.csv')
        assert 'no-store' in resp.headers['Cache-Control']


class TestAgentArtifacts:
    def test_path_agen_menunjuk_berkas_nyata(self):
        path = _agent_script_path()
        assert path.endswith(os.path.join('scripts', AGENT_SCRIPT))
        assert os.path.isfile(path)

    def test_versi_python_sama_dengan_powershell(self):
        match = re.search(r"^\s*\$AgentVersion\s*=\s*'([^']+)'", _read(AGENT_PS1), re.MULTILINE)
        assert match, 'AgentVersion tidak ditemukan di agen PowerShell'
        assert match.group(1) == AGENT_VERSION

    def test_agen_punya_penanda_paket_dan_task(self):
        text = _read(AGENT_PS1)
        assert 'BPF-WORKHUB-IT-ASSET-AGENT' in text
        assert '$TaskName' in text and 'Register-ScheduledTask' in text
        assert 'icacls' in text            # ACL config/token
        assert '-TokenFile' in text        # token tidak wajib di command line
        assert '/api/it/agents/version' in text   # self-update
        assert '/api/it/agents/package' in text
        assert '/api/it/agents/report' in text
        assert '/api/it/discovery/agent' in text
        # Tidak boleh menyebar sendiri.
        lower = text.lower()
        for banned in ('psexec', 'new-smbshare', 'copy-item -tosession'):
            assert banned not in lower

    def test_agen_tidak_membuat_aset_otomatis(self):
        text = _read(AGENT_PS1)
        assert '/api/it/assets' not in text


class TestDeployerGuards:
    def setup_method(self):
        self.text = _read(DEPLOY_PS1)
        self.lower = self.text.lower()

    def test_targets_wajib(self):
        assert re.search(r'\[Parameter\(Mandatory\s*=\s*\$true\)\]\s*\[string\]\s*\$Targets', self.text)

    def test_batas_jumlah_host(self):
        assert re.search(r'\[int\]\s*\$MaxHosts\s*=\s*25', self.text)
        assert 'melebihi -MaxHosts' in self.text
        assert re.search(r'\[switch\]\s*\$Force', self.text)

    def test_menolak_cidr_dan_wildcard(self):
        assert "'[/?*]'" in self.text
        assert 'bukan alamat IPv4 tunggal' in self.text
        assert 'bukan host tunggal' in self.text

    def test_hanya_winrm_bukan_psexec(self):
        assert 'New-PSSession' in self.text
        assert 'Copy-Item -ToSession' in self.text
        # Kata "PsExec" hanya boleh muncul di dokumentasi "tidak memakai".
        assert 'psexec.exe' not in self.lower
        assert '-accepteula' not in self.lower
        assert 'winrs' not in self.lower
        assert self.lower.count('psexec') == 1

    def test_tidak_ada_parameter_subnet_atau_all(self):
        assert not re.search(r'\$Subnet', self.text)
        assert not re.search(r'\$Cidr', self.text)
        assert not re.search(r'\$AllHosts', self.text)

    def test_melapor_dan_mencatat_log(self):
        assert '/api/it/agents/report' in self.text
        assert 'Export-Csv' in self.text
        assert 'X-IT-TOKEN' in self.text

    def test_menghapus_token_sementara(self):
        assert '-DeleteTokenFile' in self.text
        assert 'Remove-Item -LiteralPath $tokenTemp' in self.text

    def test_ada_mode_dryrun(self):
        assert re.search(r'\[switch\]\s*\$DryRun', self.text)
        assert 'tidak ada koneksi yang dibuka' in self.text

    def test_ada_penanda_deployer(self):
        assert 'BPF-WORKHUB-IT-AGENT-DEPLOYER' in self.text


class TestSchema:
    def test_tabel_registry_ada(self):
        ddl = '\n'.join(_DDL)
        assert 'it_agent_hosts' in ddl
        assert 'uniq_agent_host' in ddl
        assert "deploy_status ENUM('pending','installed','failed','unreachable','ignored')" in ddl

    def test_init_sql_memuat_tabel_yang_sama(self):
        sql = _read(os.path.join(ROOT, 'init.sql'))
        assert 'CREATE TABLE IF NOT EXISTS it_agent_hosts' in sql
        assert 'uniq_agent_host (branch_code, host_key)' in sql


class TestRoutes:
    def test_route_agen_terdaftar(self):
        app = Flask(__name__)
        register_it_asset_routes(app)
        rules = {r.rule for r in app.url_map.iter_rules()}
        for path in ('/api/it/agents/report', '/api/it/agents', '/api/it/agents/coverage',
                     '/api/it/agents/targets.csv', '/api/it/agents/version',
                     '/api/it/agents/package'):
            assert path in rules

    def test_paket_dan_versi_wajib_token(self):
        app = Flask(__name__)
        register_it_asset_routes(app)
        client = app.test_client()
        assert client.get('/api/it/agents/version').status_code == 401
        assert client.get('/api/it/agents/package').status_code == 401
        assert client.post('/api/it/agents/report', json={}).status_code == 401
