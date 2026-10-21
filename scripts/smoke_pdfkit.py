"""Smoke test NYATA PDF Kit v2.47.0 — verifikasi deploy.

Login sebagai it_sby (PIN dibaca dari DB, tidak pernah dicetak), unggah PDF scan
2 halaman, tunggu job selesai, unduh hasilnya, cek laporan pemakaian, lalu hapus
job uji supaya tidak mengotori data. Jalankan setelah `docker compose build web
&& up -d`:

    docker cp scripts/smoke_pdfkit.py bbm_web:/tmp/smoke_pdfkit.py
    docker exec -w /app bbm_web python3 /tmp/smoke_pdfkit.py

WAJIB lewat HTTPS — `SESSION_COOKIE_SECURE=true` sehingga cookie sesi tidak
terkirim via http:// (lihat BASE di bawah). Keluaran terakhir: login ok, 6 mode,
job done hemat 95,5%, unduh HTTP 200, laporan 1 baris konsisten, job uji terhapus.
"""
import os
import subprocess
import sys
import time
import urllib.parse

sys.path.insert(0, '/app')

import numpy as np  # noqa: E402
import requests  # noqa: E402
from PIL import Image  # noqa: E402
from fpdf import FPDF  # noqa: E402

# WAJIB HTTPS: SESSION_COOKIE_SECURE=true → browser/requests tidak mengirim
# cookie sesi lewat http (pengujian via http://127.0.0.1:5000 akan 401).
BASE = 'https://nasbpfsby.duckdns.org:5000'
SRC = '/tmp/smoke_scan.pdf'
OUT = '/tmp/smoke_hasil.pdf'

s = requests.Session()
me = s.get(BASE + '/api/auth/me', timeout=30).json()
csrf = me.get('csrf_token', '')

from modules.config import get_master_connection  # noqa: E402
conn = get_master_connection()
cur = conn.cursor(dictionary=True)
cur.execute("SELECT pin FROM users WHERE username='it_sby' AND is_active=1")
row = cur.fetchone() or {}
cur.close()
conn.close()
if not row.get('pin'):
    print('GAGAL: user it_sby tidak aktif / PIN tidak terbaca')
    sys.exit(1)

r = s.post(BASE + '/api/auth/login', json={'username': 'it_sby', 'pin': row['pin']},
           headers={'X-CSRF-Token': csrf}, timeout=30)
d = r.json()
u = d.get('user') or {}
print('1) login it_sby       : status={} role={} cabang={} home={} csrf={}'.format(
    d.get('status'), u.get('role'), u.get('branch_name'), u.get('home'),
    bool(d.get('csrf_token'))))
csrf = d.get('csrf_token') or csrf

modes = s.get(BASE + '/api/pdfkit/modes', timeout=30).json()
print('2) mode tersedia      : {} | limits={}'.format(
    ','.join(m['key'] for m in modes['modes']), modes['limits']))

arr = np.random.default_rng(3).integers(0, 256, (1800, 1800, 3), dtype=np.uint8)
Image.fromarray(arr).save('/tmp/smoke_src.jpg', quality=95)
pdf = FPDF()
for _ in range(2):
    pdf.add_page()
    pdf.image('/tmp/smoke_src.jpg', x=10, y=10, w=190)
pdf.output(SRC)
before = os.path.getsize(SRC)
pages = subprocess.run(['pdfinfo', SRC], capture_output=True, text=True).stdout
print('3) berkas uji         : {} byte, {}'.format(
    before, [ln for ln in pages.splitlines() if ln.startswith('Pages')][0]))

with open(SRC, 'rb') as fh:
    r = s.post(BASE + '/api/pdfkit/jobs', data={'mode': 'sedang'},
               files=[('files', ('smoke_scan.pdf', fh, 'application/pdf'))],
               headers={'X-CSRF-Token': csrf}, timeout=120)
job = r.json()['job']
jid = job['id']
print('4) job dibuat         : {} (HTTP {})'.format(jid, r.status_code))

job = None
for _ in range(120):
    job = s.get(BASE + '/api/pdfkit/jobs/' + jid, timeout=30).json()['job']
    if job['status'] in ('done', 'error', 'cancelled'):
        break
    time.sleep(1)
it = job['items'][0]
print('5) hasil job          : status={} hemat={}% ({} byte) | {} -> {} byte | hlm={} | mode={}'.format(
    job['status'], job['ratio_pct'], job['saved_bytes'], it['size_before'],
    it['size_after'], it['pages'], it['mode_used']))
print('   catatan           : {}'.format(it['note']))
fname = it['outputs'][0]['file']

r = s.get('{}/api/pdfkit/download/{}/{}'.format(BASE, jid, urllib.parse.quote(fname)),
          timeout=120)
with open(OUT, 'wb') as fh:
    fh.write(r.content)
info = subprocess.run(['pdfinfo', OUT], capture_output=True, text=True).stdout
print('6) unduh hasil        : HTTP {} | {} byte | {}'.format(
    r.status_code, len(r.content),
    ' | '.join(ln for ln in info.splitlines() if ln.startswith(('Pages', 'File size')))))
print('   content-type      : {} | teks terekstrak: {} byte (0 = wajar utk scan)'.format(
    r.headers.get('Content-Type'),
    len(subprocess.run(['pdftotext', OUT, '-'], capture_output=True, text=True).stdout)))

rep = s.get(BASE + '/api/pdfkit/report', timeout=30).json()['data']
t = rep['totals']
print('7) laporan pemakaian  : jobs={} files={} done={} hemat={} byte ({}%) | sebelum={} sesudah={}'.format(
    t['jobs'], t['files'], t['done'], t['saved_bytes'], t['ratio_pct'],
    t['size_before'], t['size_after']))
for usr in rep['per_user']:
    print('   - {} ({}): {} job, {} berkas, hemat {} byte ({}%), terakhir {}'.format(
        usr['user'], usr['role'], usr['jobs'], usr['files'], usr['saved_bytes'],
        usr['ratio_pct'], usr['last_at']))

print('8) bersih-bersih      : {}'.format(
    s.delete(BASE + '/api/pdfkit/jobs/' + jid, headers={'X-CSRF-Token': csrf},
             timeout=30).json().get('msg')))
print('   sisa job tersimpan : {}'.format(s.get(BASE + '/api/pdfkit/jobs', timeout=30).json()['jobs']))
for p in (SRC, OUT, '/tmp/smoke_src.jpg'):
    try:
        os.remove(p)
    except OSError:
        pass
