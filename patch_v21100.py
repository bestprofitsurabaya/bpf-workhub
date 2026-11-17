import re

# 1) Dockerfile: tambah curl + model tessdata_best
p = 'Dockerfile'
s = open(p).read()
old = """    tesseract-ocr \\
    tesseract-ocr-ind \\
    ffmpeg \\"""
new = """    tesseract-ocr \\
    tesseract-ocr-ind \\
    curl \\
    ffmpeg \\"""
assert old in s
s = s.replace(old, new, 1)

anchor = """    && rm -rf /var/lib/apt/lists/*"""
addition = """    && rm -rf /var/lib/apt/lists/*
# v2.110.0: model tessdata_best (akurat) menggantikan versi fast bawaan
# paket. ind ~7,9 MB, eng ~15 MB; diambil dari tessdata_best GitHub.
RUN curl -fsSL -o /usr/share/tesseract-ocr/5/tessdata/ind.traineddata \\
        https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/main/ind.traineddata \\
 && curl -fsSL -o /usr/share/tesseract-ocr/5/tessdata/eng.traineddata \\
        https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/main/eng.traineddata"""
assert anchor in s
s = s.replace(anchor, addition, 1)
open(p, 'w').write(s)

# 2) modul OCR baru
import shutil
shutil.copyfile('ktp_ocr_v21100.py', 'modules/ktp_ocr.py')

# 3) version stamps
edits = {
    'modules/company_identity.py': [("'system_version': 'v2.109.1'", "'system_version': 'v2.110.0'")],
    'modules/pdf_generator.py': [("SYSTEM_VERSION = 'BPF WorkHub v2.109.1'", "SYSTEM_VERSION = 'BPF WorkHub v2.110.0'")],
    'frontend/src/stores/identity.js': [("system_version: 'v2.109.1'", "system_version: 'v2.110.0'")],
    'frontend/public/sw.js': [("const CACHE = 'bpf-spa-20261117-v2.109.1';", "const CACHE = 'bpf-spa-20261117-v2.110.0';")],
    'docs/internal/USER_LIST.md': [('# 📋 Daftar User & Role — BPF WorkHub v2.109.1', '# 📋 Daftar User & Role — BPF WorkHub v2.110.0')],
    'guides/USER_GUIDE.md': [('# 📖 Panduan Pengguna BPF WorkHub v2.109.1', '# 📖 Panduan Pengguna BPF WorkHub v2.110.0')],
}
for path, subs in edits.items():
    text = open(path).read()
    for a, b in subs:
        assert a in text, (path, a)
        text = text.replace(a, b, 1)
    open(path, 'w').write(text)

# 4) changelog
entry = open('changelog_entry_v21100.md').read()
p = 'CHANGELOG.md'
s = open(p).read()
anchor = '## v2.109.1'
assert anchor in s
s = s.replace(anchor, entry + anchor, 1)
open(p, 'w').write(s)
print('patch v2.110.0 ok')
