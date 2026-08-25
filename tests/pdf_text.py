"""Ekstraktor teks PDF fpdf2 — sumber tunggal untuk semua test.

Sebelumnya fungsi ini disalin ke 3 file test (test_water, test_pdf_compact,
test_branches) sehingga perbaikan harus diulang di tiap salinan. Sekarang
semua meng-import dari sini:

    from tests.pdf_text import pdf_text

Tanpa dependensi eksternal (pypdf/PyPDF2 tidak tersedia di container):
1. Parse objek PDF & referensi /ToUnicode per font.
2. Bangun CMap glyph-code -> Unicode dari stream CMap (FlateDecode).
3. Baca literal string di content stream, hormati escape backslash
   (spesifikasi PDF §7.3.4.2) dan kurung, lalu decode pasangan 2-byte
   dengan CMap font aktif (/Fx ... Tf).
"""
import re
import zlib


def _decomp(data):
    try:
        return zlib.decompress(data)
    except Exception:
        return data


def _stream_of(body):
    """Ambil isi stream (...endstream) dari body objek & decompress (FlateDecode)."""
    m = re.search(rb'stream\r?\n(.*?)\r?\nendstream', body, re.S)
    if not m:
        return b''
    return _decomp(m.group(1))


def pdf_text(pdf_bytes):
    """Ekstrak teks dari PDF fpdf2 (font disubset → kode glyph 2-byte + CMap ToUnicode)."""
    # 1. Objek PDF: nomor → isi
    objs = {}
    for m in re.finditer(rb'(\d+) 0 obj(.*?)endobj', pdf_bytes, re.S):
        objs[int(m.group(1))] = m.group(2)

    # 2. Font object → objek ToUnicode
    font_to_unicode = {}
    for num, body in objs.items():
        m = re.search(rb'/ToUnicode\s+(\d+)\s+0\s+R', body)
        if m:
            font_to_unicode[num] = int(m.group(1))

    # 3. Nama resource (/F1, /F2, ...) → objek font
    name_to_font = {}
    for body in objs.values():
        m = re.search(rb'/Font\s*<<(.*?)>>', body, re.S)
        if m:
            for fm in re.finditer(rb'/(F\d+)\s+(\d+)\s+0\s+R', m.group(1)):
                name_to_font[fm.group(1).decode()] = int(fm.group(2))

    # 4. CMap per nama font
    cmaps = {}
    for name, font_num in name_to_font.items():
        touni = font_to_unicode.get(font_num)
        if touni is None or touni not in objs:
            continue
        body = _stream_of(objs[touni])
        cmap = {}
        for part in body.split(b'endbfchar'):
            if b'beginbfchar' not in part:
                continue
            section = part.split(b'beginbfchar', 1)[1]
            for bm in re.finditer(rb'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', section):
                code = int(bm.group(1), 16)
                uni = bm.group(2)
                cmap[code] = ''.join(
                    chr(int(uni[i:i + 4], 16)) for i in range(0, len(uni), 4))
        cmaps[name] = cmap

    # 5. Decode satu literal string dengan CMap font aktif
    def _decode(raw, cmap):
        # Fallback: string teks polos (font non-subset) → ASCII langsung
        if all(0x20 <= b < 0x7F for b in raw) and b'\x00' not in raw:
            return raw.decode('latin-1')
        out = []
        k = 0
        while k + 1 < len(raw):
            code = (raw[k] << 8) | raw[k + 1]
            ch = cmap.get(code, '')
            if ch:
                out.append(ch)
            k += 2
        return ''.join(out)

    texts = []
    for body in objs.values():
        stream = _stream_of(body)
        if b'BT' not in stream or b'Tj' not in stream:
            continue
        font = 'F1'
        out = []
        i, n = 0, len(stream)
        while i < n:
            fm = re.match(rb'/(F\d+)\s+[\d.]+\s+Tf', stream[i:])
            if fm:
                font = fm.group(1).decode()
                i += fm.end()
                continue
            if stream[i] == 0x28:  # '('
                j = i + 1
                buf = bytearray()
                while j < n:
                    c = stream[j]
                    if c == 0x5C and j + 1 < n:  # escape backslash (PDF §7.3.4.2)
                        e = stream[j + 1]
                        if e in (0x28, 0x29, 0x5C):          # \( \) \\ → literal
                            buf.append(e)
                            j += 2
                        elif e == 0x6E:                       # \n
                            buf.append(0x0A); j += 2
                        elif e == 0x72:                       # \r
                            buf.append(0x0D); j += 2
                        elif e == 0x74:                       # \t
                            buf.append(0x09); j += 2
                        elif e == 0x62:                       # \b
                            buf.append(0x08); j += 2
                        elif e == 0x66:                       # \f
                            buf.append(0x0C); j += 2
                        elif 0x30 <= e <= 0x37:               # \ddd oktal (1–3 digit)
                            digits = bytearray([e])
                            j += 2
                            while j < n and len(digits) < 3 and 0x30 <= stream[j] <= 0x37:
                                digits.append(stream[j])
                                j += 1
                            buf.append(int(digits.decode('ascii'), 8) & 0xFF)
                        else:                                 # escape tak dikenal → abaikan
                            j += 2
                        continue
                    if c == 0x29:  # ')'
                        break
                    buf.append(c)
                    j += 1
                out.append(_decode(bytes(buf), cmaps.get(font, {})))
                i = j + 1
            else:
                i += 1
        texts.append(''.join(out))
    return '\n'.join(texts)


# Alias kompatibel dengan nama lama yang dipakai file test.
_pdf_text = pdf_text
