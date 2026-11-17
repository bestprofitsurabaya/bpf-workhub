import shutil

shutil.copyfile('/tmp/ktp_ocr_v21110.py', '/home/it-ef/bpf-workhub/modules/ktp_ocr.py')

s = open('/home/it-ef/bpf-workhub/modules/ktp_ocr.py', encoding='utf-8').read()
s = s.replace('v2.110.0', 'v2.111.0', 1)
s = s.replace(
    "v2.110.0 — model tessdata_best + voting berbobot lintas varian praproses.",
    "v2.111.0 — nilai NIK dibaca dari crop kata-kata di kanan label + validasi\n"
    "tanggal lahir.")
open('/home/it-ef/bpf-workhub/modules/ktp_ocr.py', 'w', encoding='utf-8').write(s)

sub = [
    ('/home/it-ef/bpf-workhub/modules/company_identity.py', "'system_version': 'v2.110.0'", "'system_version': 'v2.111.0'"),
    ('/home/it-ef/bpf-workhub/modules/pdf_generator.py', "SYSTEM_VERSION = 'BPF WorkHub v2.110.0'", "SYSTEM_VERSION = 'BPF WorkHub v2.111.0'"),
    ('/home/it-ef/bpf-workhub/frontend/src/stores/identity.js', "system_version: 'v2.110.0'", "system_version: 'v2.111.0'"),
    ('/home/it-ef/bpf-workhub/frontend/public/sw.js', "const CACHE = 'bpf-spa-20261117-v2.110.0';", "const CACHE = 'bpf-spa-20261117-v2.111.0';"),
    ('/home/it-ef/bpf-workhub/docs/internal/USER_LIST.md', '# 📋 Daftar User & Role — BPF WorkHub v2.110.0', '# 📋 Daftar User & Role — BPF WorkHub v2.111.0'),
    ('/home/it-ef/bpf-workhub/guides/USER_GUIDE.md', '# 📖 Panduan Pengguna BPF WorkHub v2.110.0', '# 📖 Panduan Pengguna BPF WorkHub v2.111.0'),
]
for path, old, new in sub:
    text = open(path, encoding='utf-8').read()
    assert old in text, path
    open(path, 'w', encoding='utf-8').write(text.replace(old, new, 1))

p = '/home/it-ef/bpf-workhub/CHANGELOG.md'
s = open(p, encoding='utf-8').read()
entry = '''## v2.111.0 — 17 November 2026 (OCR NIK lebih kuat: nilai dari crop label)

Laporan lapangan: NIK masih terbaca salah setelah v2.110.0.

Tambahan pada pipeline OCR (`modules/ktp_ocr.py`):

- Nilai NIK kini dibaca dari **crop kata-kata di kanan label** `NIK`
  (multi-scale upscale 3–4x + unsharp + whitelist angka + PSM 7/8/13).
- Validasi **tanggal lahir** (`DD MM YY`, `+40` untuk perempuan) sebagai
  penapis/penimbang kandidat — kandidat yang tidak cocok tanggal dilipat bobotnya.
- Penggabungan kandidat memakai bobot varian + ROI/token + konsistensi
  tanggal, lalu memilih nilai tertinggi.

---

'''
anchor = '## v2.110.0'
assert anchor in s
s = s.replace(anchor, entry + anchor, 1)
open(p, 'w', encoding='utf-8').write(s)
print('v2.111.0 patch ok')
