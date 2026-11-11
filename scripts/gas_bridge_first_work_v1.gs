/**
 * BPF WorkHub — Bridge Google Apps Script untuk sheet **Absensi FirstWork**.
 * Versi 1 — 11 Nov 2026.
 *
 * Tujuan: aplikasi membaca Sheet yang tetap PRIVATE. URL /exec adalah satunya
 * jalur publik; Sheet tidak perlu dibuka "anyone with the link".
 *
 * Sheet: https://docs.google.com/spreadsheets/d/1GG82WjF3a5WIsUhTlP0LOtD2Gb8hyovjAh5SKiN1upM
 * Tab  : tab pertama (respons form "Absensi FirstWork").
 *
 * KONTRAK (semua respons JSON):
 *   ?marker=1                      → {marker, code_rev, module, total}
 *   ?headers=1                     → {headers:[...], sheet_name, last_row, code_rev}
 *   ?rows=1&offset=0&limit=500     → {headers:[...], rows:[[...]], total, next_offset, code_rev}
 *   ?since=YYYY-MM-DD              → filter baris dengan timestamp >= tanggal
 *   ?debug=1                       → info tipe sel, tab, dan zona waktu
 *   ?cache_bust=1                  → abaikan cache in-memory
 *   ?ktp=<fileId>&token=<secret>   → unduh 1 file KTP (base64) — lihat catatan
 *
 * KEAMANAN ENDPOINT KTP:
 *   - Token disimpan di Script Properties dengan nama KTP_TOKEN; WAJIB diisi.
 *   - File ID harus ada di kolom UPLOAD KTP / photoid pada Sheet (allowlist),
 *     sehingga token yang bocor tidak bisa dipakai membaca Drive lain.
 *   - Aplikasi memanggil endpoint ini dari server (bukan browser), lalu
 *     menyimpan/menyajikan file lewat endpoint terautentikasi.
 *   - Respons: {name, mimeType, size, data_base64}. Batas praktis Apps Script
 *     ±50 MB per respons; KTP normal jauh di bawah itu.
 *
 * CATATAN PENTING:
 *   - Baris dikirim sebagai ARRAY sesuai urutan kolom Sheet (header index 0
 *     kosong = Timestamp). Server memetakan lewat indeks, bukan nama.
 *   - Sel tanggal/jam diserialisasi sebagai wall-clock zona spreadsheet
 *     'yyyy-MM-dd HH:mm:ss' (BUKAN ISO UTC) agar tidak bergeser.
 *   - Nilai lain dikirim apa adanya (string/angka). NIK yang sudah rusak
 *     menjadi notasi ilmiah tetap dikirim sebagai teks; server menandainya
 *     tidak valid, bukan menebak.
 *   - Tidak ada operasi tulis. Bridge ini read-only.
 *
 * DEPLOY:
 *   1. Buka Sheet → Extensions → Apps Script → hapus isi Code.gs.
 *   2. Tempel SELURUH file ini (satu file .gs) → Ctrl+S.
 *   3. Deploy → New deployment → Web app
 *        Execute as : Me
 *        Who has access : Anyone
 *      → Deploy → salin URL /exec.
 *   4. Project Settings → Script properties → tambah `KTP_TOKEN` dengan
 *      string acak panjang (mis. 48 karakter). Token ini juga disimpan di
 *      system_config aplikasi (first_work_ktp_token).
 *   5. Verifikasi: <URL>/exec?marker=1 harus menampilkan code_rev: 1.
 *   6. Simpan URL /exec di system_config aplikasi (first_work_sheet_url).
 *      Jangan taruh URL/token di frontend/repo.
 */

// ====== KONFIGURASI ======
var FW1_SHEET_ID = '1GG82WjF3a5WIsUhTlP0LOtD2Gb8hyovjAh5SKiN1upM';
var FW1_TAB_NAME = ''; // kosong = tab pertama
var FW1_MARKER = 'bpf-first-work-2026-11-11-v1';
var FW1_CODE_REV = 1;

var FW1_DEFAULT_LIMIT = 500;
var FW1_MAX_LIMIT = 2000;
var FW1_CACHE_TTL_MS = 5 * 60 * 1000;
var FW1_KTP_TOKEN_PROP = 'KTP_TOKEN'; // isi via Project Settings → Script properties

// ====== CACHE IN-MEMORY ======
var FW1_cache = null;      // { at: ms, headers: [], rows: [] }
var FW1_tzCache = null;

function fw1Sheet_() {
  var ss = SpreadsheetApp.openById(FW1_SHEET_ID);
  if (FW1_TAB_NAME) {
    var named = ss.getSheetByName(FW1_TAB_NAME);
    if (named) return named;
  }
  return ss.getSheets()[0];
}

function fw1Tz_() {
  if (FW1_tzCache) return FW1_tzCache;
  try {
    FW1_tzCache = SpreadsheetApp.openById(FW1_SHEET_ID).getSpreadsheetTimeZone();
  } catch (err) {
    FW1_tzCache = Session.getScriptTimeZone() || 'Asia/Jakarta';
  }
  return FW1_tzCache;
}

// Date bisa gagal `instanceof Date` di sandbox Apps Script → duck-typing.
function fw1IsDateLike_(v) {
  if (v instanceof Date) return true;
  if (Object.prototype.toString.call(v) === '[object Date]') return true;
  return typeof v === 'object' && v !== null && typeof v.getTime === 'function';
}

function fw1ToDate_(v) {
  if (v instanceof Date) return v;
  try {
    if (v && typeof v.getTime === 'function') {
      var t = v.getTime();
      if (typeof t === 'number' && !isNaN(t)) return new Date(t);
    }
  } catch (err) { /* abaikan */ }
  return null;
}

function fw1CellToText_(v) {
  if (v === null || v === undefined) return '';
  var d = fw1ToDate_(v);
  if (d) {
    // Wall-clock zona spreadsheet — bukan ISO UTC.
    if (d.getFullYear() < 1900) {
      return Utilities.formatDate(d, fw1Tz_(), 'HH:mm:ss');
    }
    return Utilities.formatDate(d, fw1Tz_(), 'yyyy-MM-dd HH:mm:ss');
  }
  if (v instanceof Object) {
    try { return JSON.stringify(v); } catch (err) { return String(v); }
  }
  return v;
}

function fw1Json_(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

// ====== KTP: allowlist + token ======
function fw1DriveId_(s) {
  s = String(s || '');
  var m = s.match(/[?&]id=([A-Za-z0-9_-]+)/) || s.match(/\/d\/([A-Za-z0-9_-]+)/);
  return m ? m[1] : '';
}

function fw1KtpColumns_(headers) {
  var idx = [];
  for (var i = 0; i < headers.length; i++) {
    var h = String(headers[i] || '').toLowerCase();
    if (h.indexOf('upload ktp') >= 0 || h.indexOf('photoid') >= 0) idx.push(i);
  }
  // Fallback sesuai struktur Sheet saat ini: J=9 (UPLOAD KTP), K=10 (photoid).
  if (!idx.length) idx = [9, 10];
  return idx;
}

function fw1AllowedFileIds_() {
  var all = fw1ReadAll_();
  var idx = fw1KtpColumns_(all.headers);
  var allowed = {};
  for (var r = 0; r < all.rows.length; r++) {
    for (var k = 0; k < idx.length; k++) {
      var fid = fw1DriveId_(all.rows[r][idx[k]]);
      if (fid) allowed[fid] = true;
    }
  }
  return allowed;
}

function fw1SecureEquals_(a, b) {
  a = String(a || '');
  b = String(b || '');
  if (!a || !b || a.length !== b.length) return false;
  var diff = 0;
  for (var i = 0; i < a.length; i++) {
    diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return diff === 0;
}

function fw1HandleKtp_(p) {
  var expected = PropertiesService.getScriptProperties().getProperty(FW1_KTP_TOKEN_PROP);
  if (!expected) {
    return { error: 'KTP_TOKEN belum diset di Script Properties' };
  }
  if (!fw1SecureEquals_(p.token, expected)) {
    return { error: 'unauthorized' };
  }

  var fileId = String(p.ktp || '').trim();
  if (!/^[A-Za-z0-9_-]{10,}$/.test(fileId)) {
    return { error: 'file id tidak valid' };
  }

  var allowed = fw1AllowedFileIds_();
  if (!allowed[fileId]) {
    return { error: 'file tidak terdaftar pada Sheet First Work' };
  }

  try {
    var file = DriveApp.getFileById(fileId);
    var blob = file.getBlob();
    var bytes = blob.getBytes();
    return {
      name: file.getName(),
      mimeType: blob.getContentType(),
      size: bytes.length,
      data_base64: Utilities.base64Encode(bytes)
    };
  } catch (err) {
    return { error: 'gagal membaca file: ' + String(err) };
  }
}

function fw1ReadAll_() {
  var now = new Date().getTime();
  if (FW1_cache && (now - FW1_cache.at) < FW1_CACHE_TTL_MS) return FW1_cache;

  var sh = fw1Sheet_();
  var lastRow = sh.getLastRow();
  var lastCol = sh.getLastColumn();
  var data = [];

  if (lastRow > 0 && lastCol > 0) {
    // Header + data dalam satu bacaan; nilai mentah dipertahankan.
    var values = sh.getRange(1, 1, lastRow, lastCol).getValues();
    var headers = values[0].map(function (h) { return String(h === null ? '' : h); });
    var rows = [];
    for (var r = 1; r < values.length; r++) {
      var row = [];
      for (var c = 0; c < lastCol; c++) {
        row.push(fw1CellToText_(values[r][c]));
      }
      // Lewati baris yang benar-benar kosong (mis. sisa format).
      var any = false;
      for (var k = 0; k < row.length; k++) {
        if (String(row[k] || '').trim() !== '') { any = true; break; }
      }
      if (any) rows.push(row);
    }
    data = { headers: headers, rows: rows };
  } else {
    data = { headers: [], rows: [] };
  }

  FW1_cache = {
    at: now,
    headers: data.headers,
    rows: data.rows,
    sheet_name: sh.getName(),
    last_row: lastRow
  };
  return FW1_cache;
}

// Filter ?since=YYYY-MM-DD berdasarkan kolom pertama (Timestamp).
// Timestamp dari fw1CellToText_ berbentuk 'yyyy-MM-dd HH:mm:ss' atau
// 'dd/MM/yyyy HH:mm:ss' (tergantung bagaimana Sheet menyimpannya).
function fw1RowDate_(row) {
  if (!row || row.length === 0) return null;
  var s = String(row[0] || '').trim();
  if (!s) return null;

  var m = s.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?/);
  if (m) return new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +(m[6] || 0));

  m = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})[ T](\d{1,2}):(\d{2})(?::(\d{2}))?/);
  if (m) return new Date(+m[3], +m[2] - 1, +m[1], +m[4], +m[5], +(m[6] || 0));

  var d = new Date(s);
  return isNaN(d.getTime()) ? null : d;
}

function fw1ParseSince_(s) {
  var m = String(s || '').match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!m) return null;
  return new Date(+m[1], +m[2] - 1, +m[3]);
}

function doGet(e) {
  try {
    var p = (e && e.parameter) ? e.parameter : {};

    if (p.ktp) {
      return fw1Json_(fw1HandleKtp_(p));
    }

    if (p.marker === '1') {
      var all0 = fw1ReadAll_();
      return fw1Json_({
        marker: FW1_MARKER,
        code_rev: FW1_CODE_REV,
        module: 'first_work',
        sheet_name: all0.sheet_name,
        total: all0.rows.length
      });
    }

    if (p.cache_bust === '1') FW1_cache = null;

    if (p.debug === '1') {
      var sh = fw1Sheet_();
      var dbg = {
        marker: FW1_MARKER,
        code_rev: FW1_CODE_REV,
        sheet_id_tail: String(FW1_SHEET_ID).slice(-6),
        sheet_name: sh.getName(),
        last_row: sh.getLastRow(),
        last_col: sh.getLastColumn(),
        timezone: fw1Tz_(),
        tabs: sh.getParent().getSheets().map(function (s) {
          return s.getName() + ':' + s.getLastRow();
        })
      };
      if (sh.getLastRow() > 0 && sh.getLastColumn() > 0) {
        var first = sh.getRange(1, 1, Math.min(2, sh.getLastRow()), sh.getLastColumn()).getValues();
        dbg.header_count = first[0].length;
        dbg.headers_preview = first[0].slice(0, 8).map(function (h) { return String(h || ''); });
        if (first.length > 1) {
          dbg.first_ts_raw_type = typeof first[1][0];
          dbg.first_ts_is_date = fw1IsDateLike_(first[1][0]);
          dbg.first_ts_text = String(fw1CellToText_(first[1][0]));
        }
      }
      return fw1Json_(dbg);
    }

    var all = fw1ReadAll_();

    if (p.headers === '1') {
      return fw1Json_({
        marker: FW1_MARKER,
        code_rev: FW1_CODE_REV,
        sheet_name: all.sheet_name,
        last_row: all.last_row,
        total: all.rows.length,
        headers: all.headers
      });
    }

    // Default: kirim baris (pagination).
    var offset = parseInt(p.offset || '0', 10);
    if (isNaN(offset) || offset < 0) offset = 0;

    var limit = parseInt(p.limit || String(FW1_DEFAULT_LIMIT), 10);
    if (isNaN(limit) || limit <= 0) limit = FW1_DEFAULT_LIMIT;
    if (limit > FW1_MAX_LIMIT) limit = FW1_MAX_LIMIT;

    var since = fw1ParseSince_(p.since);
    var source = all.rows;

    if (since) {
      source = source.filter(function (row) {
        var d = fw1RowDate_(row);
        return d && d.getTime() >= since.getTime();
      });
    }

    var total = source.length;
    var page = source.slice(offset, offset + limit);
    var next = offset + page.length;
    if (next >= total) next = null;

    return fw1Json_({
      marker: FW1_MARKER,
      code_rev: FW1_CODE_REV,
      sheet_name: all.sheet_name,
      headers: all.headers,
      total: total,
      offset: offset,
      limit: limit,
      next_offset: next,
      rows: page
    });
  } catch (err) {
    return fw1Json_({
      marker: FW1_MARKER,
      code_rev: FW1_CODE_REV,
      error: String(err && err.message ? err.message : err)
    });
  }
}
