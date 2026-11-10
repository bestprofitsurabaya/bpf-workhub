#!/usr/bin/env python3
"""Agen penemuan perangkat Inventaris IT — DIJALANKAN DI HOST NAS (bukan container).

Kenapa di host: tabel ARP LAN hanya terlihat di network namespace host.
Container `bpf-workhub-web` memakai bridge Docker dan tidak bisa membaca MAC
tetangga. Skrip ini TIDAK butuh root:

  - sapuan TCP  : `socket.connect_ex()` biasa
  - MAC lokal   : `/proc/net/arp` (world-readable)
  - MikroTik    : `librouteros` (opsional; API 8728 harus diaktifkan IT)

Hasil dikirim ke BPF WorkHub lewat `POST /api/it/discovery/agent` dengan
header `X-IT-TOKEN` (= env `IT_DISCOVERY_TOKEN` di `.env` aplikasi).

Contoh pemakaian di host NAS:

    # 1) uji tanpa mengirim (lihat hasil di layar)
    python3 scripts/it_discovery_agent.py --dry-run --subnets 192.168.2.0/24

    # 2) kirim ke aplikasi (port 5001 = bind 127.0.0.1:5001 dari compose)
    IT_DISCOVERY_TOKEN=xxxx python3 scripts/it_discovery_agent.py \
        --branch SBY --subnets 192.168.2.0/24 \
        --url http://127.0.0.1:5001

    # 3) tambah DHCP lease MikroTik (hostname lebih akurat)
    IT_DISCOVERY_TOKEN=xxxx python3 scripts/it_discovery_agent.py \
        --branch SBY --subnets 192.168.2.0/24 \
        --mikrotik-host 192.168.2.1 --mikrotik-user itsby \
        --mikrotik-pass '***'

Cron host (2x/hari, di luar jam sibuk):

    0 12,20 * * *  cd /home/it-ef/bpf-workhub && \
        set -a; . ./.env; set +a; \
        python3 scripts/it_discovery_agent.py --branch SBY \
          --subnets 192.168.2.0/24 >> /tmp/it-discovery.log 2>&1

Aman dijalankan berulang: server melakukan dedupe per (cabang, MAC) dan
tidak pernah membuat aset otomatis — perangkat hanya menjadi *kandidat*
yang harus disetujui IT.
"""
import argparse
import concurrent.futures as futures
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request

DEFAULT_PORTS = [135, 445, 139, 3389, 5985, 9100, 631, 515, 80, 443, 22, 53, 554, 8000]


# --------------------------------------------------------------------------- ARP


def read_arp_table():
    """Baca /proc/net/arp → {ip: mac}. Melewati entri tidak lengkap (00:00...)."""
    table = {}
    try:
        with open('/proc/net/arp', 'r', encoding='utf-8', errors='replace') as fh:
            next(fh, None)  # header
            for line in fh:
                parts = line.split()
                if len(parts) < 4:
                    continue
                ip, mac = parts[0], parts[3]
                if not mac or mac == '00:00:00:00:00:00':
                    continue
                if len(mac.replace(':', '')) != 12:
                    continue
                table[ip] = mac.upper()
    except OSError as e:
        print(f'[arp] tidak bisa membaca /proc/net/arp: {e}', file=sys.stderr)
    return table


# ------------------------------------------------------------------------ sapuan


def expand_cidr(cidr):
    """'192.168.2.0/24' → daftar IP host (tanpa network/broadcast)."""
    base, _, prefix = str(cidr).strip().partition('/')
    prefix = int(prefix) if prefix else 32
    if not 16 <= prefix <= 32:
        raise ValueError(f'prefix /{prefix} tidak didukung (pakai /16../32)')
    network = int.from_bytes(socket.inet_aton(base), 'big') & (
        (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF)
    count = 1 << (32 - prefix)
    first, last = (1, count - 2) if prefix <= 30 else (0, count - 1)
    return [socket.inet_ntoa(((network + i) & 0xFFFFFFFF).to_bytes(4, 'big'))
            for i in range(first, last + 1)]


def probe_ports(ip, ports, timeout):
    open_ports = []
    for port in ports:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            if sock.connect_ex((ip, port)) == 0:
                open_ports.append(port)
        except OSError:
            pass
        finally:
            sock.close()
    return open_ports


def reverse_name(ip):
    try:
        return socket.gethostbyaddr(ip)[0].split('.')[0]
    except Exception:
        return ''


def sweep(ips, ports, timeout, workers):
    """Sapuan TCP paralel → {ip: [port,...]} hanya untuk IP yang hidup."""
    alive = {}
    with futures.ThreadPoolExecutor(max_workers=workers) as pool:
        results = pool.map(lambda ip: (ip, probe_ports(ip, ports, timeout)), ips)
        for ip, open_ports in results:
            if open_ports:
                alive[ip] = open_ports
    return alive


# ---------------------------------------------------------------------- MikroTik


def mikrotik_leases(host, user, password, port=8728):
    """DHCP lease + ARP dari RouterOS via API (butuh `librouteros`).

    Returns list[{ip, mac, hostname}] atau [] bila paket/API tidak tersedia.
    """
    try:
        import librouteros  # type: ignore
    except Exception:
        print('[mikrotik] librouteros tidak terpasang — dilewati '
              '(pip install librouteros)', file=sys.stderr)
        return []
    devices = {}
    try:
        api = librouteros.connect(host=host, username=user,
                                 password=password, port=port, timeout=8)
    except Exception as e:
        print(f'[mikrotik] gagal konek {host}:{port}: {e}', file=sys.stderr)
        return []
    try:
        try:
            for lease in api('/ip/dhcp-server/lease/print'):
                ip = lease.get('active-address') or lease.get('address') or ''
                mac = (lease.get('mac-address') or '').upper()
                name = lease.get('host-name') or lease.get('comment') or ''
                if ip and mac:
                    devices[mac] = {'ip': ip, 'mac': mac, 'hostname': name,
                                    'source': 'mikrotik'}
        except Exception as e:
            print(f'[mikrotik] lease error: {e}', file=sys.stderr)
        try:
            for entry in api('/ip/arp/print'):
                ip, mac = entry.get('address', ''), (entry.get('mac-address') or '').upper()
                if ip and mac and mac not in devices:
                    devices[mac] = {'ip': ip, 'mac': mac,
                                    'hostname': entry.get('comment') or '',
                                    'source': 'mikrotik-arp'}
        except Exception as e:
            print(f'[mikrotik] arp error: {e}', file=sys.stderr)
    finally:
        try:
            api.close()
        except Exception:
            pass
    return list(devices.values())


# ------------------------------------------------------------------------ output


def send(url, token, payload, timeout=60):
    body = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        url.rstrip('/') + '/api/it/discovery/agent', data=body, method='POST',
        headers={'Content-Type': 'application/json', 'X-IT-TOKEN': token})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')
    except Exception as e:
        return 0, str(e)


def main(argv=None):
    ap = argparse.ArgumentParser(description='Agen penemuan Inventaris IT (host NAS)')
    ap.add_argument('--branch', default=os.environ.get('IT_BRANCH', 'SBY'),
                    help='kode cabang (SBY, BDG, ...) — default SBY')
    ap.add_argument('--subnets', default=os.environ.get(
        'IT_DISCOVERY_SUBNETS', '192.168.2.0/24'),
        help='daftar CIDR dipisah koma')
    ap.add_argument('--ports', default=','.join(str(p) for p in DEFAULT_PORTS),
                    help='port TCP yang diprobe (dipisah koma)')
    ap.add_argument('--timeout', type=float, default=0.35, help='timeout per port (detik)')
    ap.add_argument('--workers', type=int, default=96, help='thread paralel')
    ap.add_argument('--url', default=os.environ.get('IT_API_URL', 'http://127.0.0.1:5001'),
                    help='basis URL aplikasi')
    ap.add_argument('--token', default=os.environ.get('IT_DISCOVERY_TOKEN', ''),
                    help='token agen (env IT_DISCOVERY_TOKEN)')
    ap.add_argument('--mikrotik-host', default=os.environ.get('MIKROTIK_HOST', ''))
    ap.add_argument('--mikrotik-user', default=os.environ.get('MIKROTIK_USER', ''))
    ap.add_argument('--mikrotik-pass', default=os.environ.get('MIKROTIK_PASSWORD', ''))
    ap.add_argument('--mikrotik-port', type=int, default=8728)
    ap.add_argument('--dry-run', action='store_true', help='jangan kirim, cetak JSON')
    args = ap.parse_args(argv)

    subnets = [s.strip() for s in str(args.subnets).split(',') if s.strip()]
    ports = [int(p) for p in str(args.ports).split(',') if p.strip().isdigit()]
    started = time.time()

    ips = []
    for cidr in subnets:
        try:
            ips.extend(expand_cidr(cidr))
        except ValueError as e:
            print(f'[skip] {cidr}: {e}', file=sys.stderr)
    print(f'[scan] {len(ips)} IP pada {", ".join(subnets)} — {len(ports)} port/thread pool {args.workers}')

    alive = sweep(ips, ports, args.timeout, args.workers)
    arp = read_arp_table()
    devices = {}
    for ip, open_ports in alive.items():
        mac = arp.get(ip, '')
        devices[mac or f'ip:{ip}'] = {
            'ip': ip, 'mac': mac, 'hostname': reverse_name(ip),
            'ports': sorted(open_ports), 'vendor': '', 'source': 'sweep',
        }
    # Perangkat yang tercatat di ARP tetapi tidak membuka port yang diprobe
    # (mis. printer sleep, HP) tetap dikirim sebagai bukti lemah.
    for ip, mac in arp.items():
        if mac not in devices and f'ip:{ip}' not in devices:
            devices[mac] = {'ip': ip, 'mac': mac, 'hostname': reverse_name(ip),
                            'ports': [], 'vendor': '', 'source': 'arp-only'}

    if args.mikrotik_host and args.mikrotik_user:
        leases = mikrotik_leases(args.mikrotik_host, args.mikrotik_user,
                                 args.mikrotik_pass, args.mikrotik_port)
        print(f'[mikrotik] {len(leases)} lease/ARP dari router')
        for lease in leases:
            key = lease['mac']
            if key in devices:
                devices[key]['hostname'] = (
                    devices[key]['hostname'] or lease.get('hostname') or '')
                devices[key]['dhcp_hostname'] = lease.get('hostname') or ''
            else:
                devices[key] = {
                    'ip': lease['ip'], 'mac': lease['mac'],
                    'hostname': lease.get('hostname') or '',
                    'dhcp_hostname': lease.get('hostname') or '',
                    'ports': [], 'vendor': '', 'source': lease.get('source', 'mikrotik'),
                }

    payload = {
        'branch_code': args.branch,
        'method': 'mixed' if args.mikrotik_host else 'sweep',
        'subnets': subnets,
        'devices': list(devices.values()),
    }
    print(f'[scan] selesai {time.time() - started:.1f} dtk — '
          f'{len(payload["devices"])} perangkat (hidup: {len(alive)})')

    if args.dry_run:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    if not args.token:
        print('[error] token kosong — set IT_DISCOVERY_TOKEN atau pakai --token',
              file=sys.stderr)
        return 2
    status, body = send(args.url, args.token, payload)
    print(f'[kirim] HTTP {status}: {body[:400]}')
    return 0 if 200 <= status < 300 else 1


if __name__ == '__main__':
    sys.exit(main())
