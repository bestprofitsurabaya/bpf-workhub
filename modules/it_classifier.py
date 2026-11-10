"""Klasifikasi perangkat jaringan untuk Inventaris IT (v2.78.0).

Pendekatan: **rule engine berbobot**, bukan ML. Alasannya:
- deterministik & bisa dijelaskan ke auditor (`reasons` disimpan apa adanya),
- tidak butuh data latih, mudah diperbaiki IT sendiri,
- keputusan IT (adopt/ignore) bisa dipakai menaikkan bobot aturan yang benar.

Semua fungsi murni (tanpa DB/jaringan) supaya bisa diuji unit.
"""
import re

# ---------------------------------------------------------------------------
# OUI (prefix MAC) — daftar kecil vendor yang paling sering muncul di kantor.
# Bila paket `netaddr` terpasang, lookup diperluas ke database IEEE lengkap.
# ---------------------------------------------------------------------------
_OUI_FALLBACK = {
    '28D0F5': 'Ruijie Networks',
    '3868A4': 'Samsung Electronics',
    '902B34': 'GIGA-BYTE Technology',
    'D067E5': 'Dell',
    '002511': 'ACTP',
    '04F41C': 'Routerboard',
    '00259C': 'Cisco-Linksys',
    '0018F3': 'Asustek',
    '3C5A37': 'Samsung Electronics',
    '001B21': 'Intel',
    'F4CE46': 'Hewlett Packard',
    '9C8E99': 'Hewlett Packard',
    '001A2B': 'Canon',
    '0021B7': 'Lexmark',
    '50F5DA': 'Amazon',
    'B827EB': 'Raspberry Pi',
}

_NETWORK_VENDORS = (
    'ruijie', 'huawei', 'ubiquiti', 'cisco', 'tp-link', 'tplink', 'aruba',
    'mikrotik', 'ruckus', 'juniper', 'zyxel', 'd-link', 'dlink', 'netgear',
    'h3c', 'fortinet', 'routerboard', 'linksys', 'extreme networks',
)
_PRINTER_VENDORS = (
    'hewlett', 'hp inc', 'canon', 'epson', 'brother', 'ricoh', 'kyocera',
    'xerox', 'lexmark', 'zebra', 'sharp', 'konica', 'fuji',
)
_CCTV_VENDORS = ('hikvision', 'dahua', 'axis', 'hanwha', 'uniview', 'bosch')
_PHONE_VENDORS = (
    'apple', 'samsung', 'xiaomi', 'oppo', 'vivo', 'realme', 'oneplus',
    'motorola', 'nokia', 'honor', 'tcl', 'infinix',
)
_PC_VENDORS = (
    'gigabyte', 'asustek', 'asus', 'msi', 'dell', 'lenovo', 'acer',
    'fujitsu', 'intel', 'micro-star', 'foxconn', 'pegatron',
)

# Hostname → petunjuk kategori
_HOST_RULES = [
    (re.compile(r'^(prn|printer|print)[-_]?', re.I), 'printer', 0.45, 'hostname printer'),
    (re.compile(r'^(hp|canon|epson|brother|ricoh)[-_]', re.I), 'printer', 0.30, 'hostname merek printer'),
    (re.compile(r'^(ap|wifi|wap)[-_]', re.I), 'network', 0.40, 'hostname access point'),
    (re.compile(r'^(sw|switch|rtr|router|gw|gateway)[-_]', re.I), 'network', 0.40, 'hostname jaringan'),
    (re.compile(r'^(nas|srv|server|dc\d)', re.I), 'server', 0.45, 'hostname server/NAS'),
    (re.compile(r'(cctv|cam|nvr|dvr)', re.I), 'cctv', 0.50, 'hostname CCTV'),
    (re.compile(r'^(desktop|pc|workstation)[-_]', re.I), 'pc', 0.30, 'hostname PC'),
    (re.compile(r'^(lt|laptop|nb)[-_]', re.I), 'laptop', 0.35, 'hostname laptop'),
    (re.compile(r'-(ef|ei|ej|ek|el|em|ea|eb|ec|ed|eg|eh|ex)$', re.I), 'pc', 0.20, 'akhiran kode cabang'),
]

# Port → petunjuk kategori
_PORT_RULES = {
    9100: ('printer', 0.70, 'port cetak 9100'),
    631: ('printer', 0.60, 'port IPP 631'),
    515: ('printer', 0.55, 'port LPD 515'),
    135: ('pc', 0.35, 'RPC Windows 135'),
    445: ('pc', 0.30, 'SMB 445'),
    139: ('pc', 0.15, 'NetBIOS 139'),
    3389: ('pc', 0.20, 'RDP 3389'),
    5985: ('pc', 0.15, 'WinRM 5985'),
    53: ('network', 0.45, 'DNS 53'),
    554: ('cctv', 0.50, 'RTSP 554'),
    8000: ('cctv', 0.30, 'HTTP kamera 8000'),
    22: ('server', 0.25, 'SSH 22'),
    80: ('network', 0.10, 'HTTP 80'),
    443: ('network', 0.10, 'HTTPS 443'),
}


def normalize_mac(mac):
    """Ubah MAC ke bentuk `AA:BB:CC:DD:EE:FF` (uppercase). None bila invalid."""
    if not mac:
        return None
    s = re.sub(r'[^0-9A-Fa-f]', '', str(mac))
    if len(s) != 12:
        return None
    s = s.upper()
    return ':'.join(s[i:i + 2] for i in range(0, 12, 2))


def mac_prefix(mac):
    m = normalize_mac(mac)
    return m.replace(':', '')[:6] if m else None


def is_locally_administered(mac):
    """True bila MAC bersifat lokal/acak (umum pada WiFi HP & VM).

    Bit U/L = bit ke-2 oktet pertama.
    """
    m = normalize_mac(mac)
    if not m:
        return False
    first = int(m[:2], 16)
    return bool(first & 0b10)


def mac_vendor(mac):
    """Nama vendor dari OUI. Fallback ke tabel kecil bila netaddr absen."""
    prefix = mac_prefix(mac)
    if not prefix:
        return ''
    try:
        from netaddr import EUI  # opsional; tersedia di image produksi
        eui = EUI(mac)
        reg = eui.oui
        org = (reg.registration().org or '').strip()
        if org:
            return org
    except Exception:
        pass
    return _OUI_FALLBACK.get(prefix, '')


def _vendor_has(vendor, needles):
    v = (vendor or '').lower()
    return any(n in v for n in needles)


def classify(ip='', mac='', hostname='', vendor='', ports=None,
             ad_os='', dhcp_hostname=''):
    """Tentukan kategori perangkat dari bukti yang ada.

    Returns dict:
      category_suggest, confidence (0..1), reasons (list[str]),
      is_asset (bool), non_asset_reason (str)
    """
    ports = [int(p) for p in (ports or []) if str(p).isdigit()]
    hostname = (hostname or dhcp_hostname or '').strip()
    vendor = (vendor or mac_vendor(mac) or '').strip()

    scores = {}
    reasons = {}

    def add(cat, weight, reason):
        scores[cat] = scores.get(cat, 0.0) + float(weight)
        reasons.setdefault(cat, []).append(reason)

    for port in ports:
        rule = _PORT_RULES.get(port)
        if rule:
            add(rule[0], rule[1], rule[2])

    if vendor:
        if _vendor_has(vendor, _PRINTER_VENDORS):
            add('printer', 0.35, f'OUI {vendor}')
        if _vendor_has(vendor, _NETWORK_VENDORS):
            add('network', 0.40, f'OUI {vendor}')
        if _vendor_has(vendor, _CCTV_VENDORS):
            add('cctv', 0.45, f'OUI {vendor}')
        if _vendor_has(vendor, _PC_VENDORS):
            add('pc', 0.15, f'OUI {vendor}')

    for pattern, cat, weight, label in _HOST_RULES:
        if hostname and pattern.search(hostname):
            add(cat, weight, label)

    if ad_os:
        low = ad_os.lower()
        if 'server' in low:
            add('server', 0.35, f'AD: {ad_os}')
        elif 'windows' in low:
            add('pc', 0.30, f'AD: {ad_os}')

    # ---- penyaring non-aset (HP pribadi, VM, perangkat acak) ----
    non_asset = ''
    if is_locally_administered(mac) and not ports:
        if not vendor or _vendor_has(vendor, _PHONE_VENDORS):
            non_asset = 'MAC acak tanpa port terbuka (kemungkinan HP/VM)'
    if not mac and not hostname and not ports:
        non_asset = 'Tidak ada identitas yang bisa dipakai'

    if not scores:
        return {
            'category_suggest': '', 'confidence': 0.0,
            'reasons': ['tidak ada bukti yang cocok'],
            'is_asset': False, 'non_asset_reason': non_asset or 'tidak dikenal',
        }

    best = max(scores, key=scores.get)
    confidence = min(0.98, round(scores[best], 2))
    # bukti dari beberapa sumber berbeda menaikkan keyakinan sedikit
    if len(reasons[best]) >= 3:
        confidence = min(0.98, round(confidence + 0.05, 2))

    return {
        'category_suggest': best,
        'confidence': confidence,
        'reasons': reasons[best] + [r for c, rs in reasons.items() if c != best for r in rs][:3],
        'is_asset': bool(not non_asset and confidence >= 0.50),
        'non_asset_reason': non_asset,
    }
