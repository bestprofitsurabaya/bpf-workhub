/**
 * BPF WorkHub — Bridge Google Apps Script untuk sheet Overtime DRIVER (OPTIMIZED v2).
 *
 * BACKWARD COMPATIBLE: Tanpa parameter, mengembalikan SEMUA data (seperti v1).
 *
 * FITUR OPTIMASI:
 *   - Filter by year/month/tanggal untuk membatasi data yang di-fetch
 *   - Pagination support (limit & offset)
 *   - Incremental sync: ?since=ISO_DATE — hanya baris yang diubah setelah tanggal
 *   - Hanya return field tertentu: ?fields=NAMA,TANGGAL,...
 *   - Summary mode: ?summary=true — tanpa foto/link berat
 *   - Cache data di memory selama 5 menit untuk mengurangi beban sheet
 *
 * v2.39 — KONTRAK TANGGAL/JAM BARU (fix "jam tidak sesuai sumber"):
 *   Nilai Date dari getValues() TIDAK lagi di-JSON.stringify mentah (yang
 *   mengirim ISO UTC dan membuat server menambah +7 jam dengan asumsi sheet
 *   berzona WIB). Kini sel Date diserialisasi sebagai TEKS sesuai tampilan
 *   sheet memakai Utilities.formatDate + zona waktu SPREADSHEET:
 *   - Kolom tanggal (Tanggal Overtime) → 'yyyy-MM-dd'
 *   - Kolom timestamp (Timestamp)      → 'yyyy-MM-dd HH:mm:ss'
 *   - Kolom jam (Dari/IN, Sampai/OUT)  → 'HH:mm:ss' (epoch 1899 tetap benar)
 *   Server menampilkan nilai ini APA ADANYA (tanpa offset) — jam di aplikasi
 *   = jam di sheet, di zona waktu spreadsheet mana pun.
 *
 * PARAMETER (query string):
 *   ?year=2025        — Filter tahun
 *   ?month=08         — Filter bulan (1-12)
 *   ?from=2025-08-01  — Filter tanggal mulai (YYYY-MM-DD)
 *   ?to=2025-08-31    — Filter tanggal sampai (YYYY-MM-DD)
 *   ?since=2025-08-19T00:00:00 — Incremental: hanya baris dengan Timestamp >= ini
 *   ?limit=100        — Jumlah record max per request (default: 0 = semua)
 *   ?offset=0         — Offset untuk pagination
 *   ?fields=Nama,Lama,Overtime  — Field yang diinginkan (comma-separated)
 *   ?summary=true     — Hanya return summary (tanpa foto/link detail)
 *
 * CONTOH:
 *   /exec                              → Semua data (backward compatible)
 *   /exec?year=2025&month=8&limit=50   → 50 data Agustus 2025
 *   /exec?from=2025-08-01&to=2025-08-31&limit=200
 *   /exec?since=2025-08-19T00:00:00    → Data baru/hari ini saja
 *   /exec?summary=true&year=2025       → Ringkasan 2025 tanpa foto
 */

// ====== CACHE (in-memory, reset setiap cold start ~5 min) ======
var _cache = {};
var _CACHE_TTL = 5 * 60 * 1000; // 5 minutes

// ====== ZONA WAKTU & SERIALIZASI (v2.39 — wall-clock sesuai sheet) ======
var _tzCache = null;
function sheetTimeZone_() {
  if (_tzCache) return _tzCache;
  try {
    _tzCache = SpreadsheetApp.openById(SHEET_ID).getSpreadsheetTimeZone();
  } catch (err) {
    _tzCache = Session.getScriptTimeZone() || 'Asia/Jakarta';
  }
  return _tzCache;
}

function isTimeColumn_(header) {
  var h = String(header || '').toLowerCase();
  if (/(tanggal|date|timestamp)/.test(h)) return false;
  return /(waktu|jam|mulai|selesai|dari|\bin\b|sampai|\bout\b|time)/.test(h);
}

function isDateOnlyColumn_(header) {
  var h = String(header || '').toLowerCase();
  return /(tanggal|date)/.test(h) && !/timestamp/.test(h);
}

function dateToText_(v, header) {
  var tz = sheetTimeZone_();
  if (v.getFullYear() < 1900) {
    // Sel JAM murni — epoch waktu Google Sheets (basis 1899-12-30).
    return Utilities.formatDate(v, tz, 'HH:mm:ss');
  }
  if (isTimeColumn_(header)) return Utilities.formatDate(v, tz, 'HH:mm:ss');
  if (isDateOnlyColumn_(header)) return Utilities.formatDate(v, tz, 'yyyy-MM-dd');
  return Utilities.formatDate(v, tz, 'yyyy-MM-dd HH:mm:ss');
}

function cellToText_(v, header) {
  if (v instanceof Date) return dateToText_(v, header);
  if (v === null || v === undefined) return '';
  if (v instanceof Object) return JSON.stringify(v);
  return v;
}

// Parse string wall-clock 'yyyy-MM-dd[ HH:mm[:ss]]' secara deterministik
// (waktu lokal script) — dipakai untuk bandingkan filter tanggal/since.
function parseWall_(s) {
  if (s instanceof Date) return s;
  var m = String(s || '').match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{1,2}):(\d{2})(?::(\d{2}))?$/);
  if (m) return new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +(m[6] || 0));
  var dOnly = String(s || '').match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (dOnly) return new Date(+dOnly[1], +dOnly[2] - 1, +dOnly[3]);
  var d = new Date(s);
  return isNaN(d.getTime()) ? null : d;
}

function doGet(e) {
  var SHEET_ID = '1L-7ZT0p48gVZEbDJS-azMqpGobmvmqCDB9J6sAB3DGM';

  try {
    var params = (e && e.parameter) ? e.parameter : {};

    // Parse parameters
    var year      = params.year      ? parseInt(params.year, 10)      : null;
    var month     = params.month     ? parseInt(params.month, 10)     : null;
    var fromDate  = params.from      ? parseDate_(params.from)         : null;
    var toDate    = params.to        ? parseDate_(params.to)           : null;
    var since     = params.since     ? parseWall_(params.since)        : null;
    var limit     = params.limit     ? Math.max(parseInt(params.limit, 10) || 0, 0) : 0;
    var offset    = params.offset    ? Math.max(parseInt(params.offset, 10) || 0, 0) : 0;
    var fields    = params.fields    ? params.fields.split(',').map(function(f) { return f.trim(); }) : null;
    var summary   = params.summary === 'true';

    // Get all data (with cache)
    var allRows = getCachedData_(SHEET_ID);

    // Filter
    var filtered = filterRows_(allRows, year, month, fromDate, toDate, since);
    var total = filtered.length;

    // Pagination: limit=0 means ALL (backward compatible)
    var paged;
    if (limit > 0) {
      paged = filtered.slice(offset, offset + limit);
    } else {
      paged = filtered; // Return all when no limit specified
    }

    // Format output
    var output;
    if (summary) {
      output = paged.map(function(row) { return summarize_(row); });
    } else if (fields) {
      output = paged.map(function(row) { return pickFields_(row, fields); });
    } else {
      output = paged;
    }

    var response = {
      rows: output,
      total: total
    };

    // Only include pagination metadata when limit is used
    if (limit > 0) {
      response.limit = limit;
      response.offset = offset;
      response.hasMore = (offset + limit) < total;
    }

    return json_(response);

  } catch (err) {
    return json_({ error: String(err), rows: [], total: 0 });
  }
}

// ====== FILTER ======
function filterRows_(rows, year, month, fromDate, toDate, since) {
  if (!year && !month && !fromDate && !toDate && !since) {
    return rows; // No filter, return all
  }

  return rows.filter(function(row) {
    // Use Timestamp for since filter (faster, always present)
    var tsRaw = since ? row['Timestamp'] : null;
    if (since && tsRaw) {
      var tsDate = parseWall_(tsRaw);
      if (tsDate && tsDate < since) return false;
    }

    // Use Tanggal Overtime for year/month/date filters
    var ts = row['Tanggal Overtime'] || row['Timestamp'];
    if (!ts) return false;

    var d = parseWall_(ts);
    if (!d) return false;

    // Year filter
    if (year && d.getFullYear() !== year) return false;

    // Month filter (1-indexed)
    if (month && (d.getMonth() + 1) !== month) return false;

    // Date range filter
    if (fromDate && d < fromDate) return false;
    if (toDate && d > toDate) return false;

    return true;
  });
}

// ====== PARSE DATE ======
function parseDate_(str) {
  // Accept YYYY-MM-DD format
  var parts = str.split('-');
  if (parts.length === 3) {
    return new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
  }
  return new Date(str);
}

// ====== SUMMARIZE (remove heavy fields like photo URLs) ======
function summarize_(row) {
  return {
    'NO FORM':           row['NO FORM'],
    'NAMA LENGKAP':      row['NAMA LENGKAP'],
    'NO KENDARAAN':      row['NO KENDARAAN'],
    'Tanggal Overtime':  row['Tanggal Overtime'],
    'Dari / IN':         row['Dari / IN'],
    'Sampai / OUT':      row['Sampai / OUT'],
    'Nama Broker / Marketing':  row['Nama Broker / Marketing'],
    'Nama Manager / Team leader': row['Nama Manager / Team leader'],
    'KETERANGAN':        row['KETERANGAN'],
    'Document Merge Status - OT DRIVER': row['Document Merge Status - OT DRIVER']
  };
}

// ====== PICK SPECIFIC FIELDS ======
function pickFields_(row, fields) {
  var out = {};
  fields.forEach(function(f) {
    if (row.hasOwnProperty(f)) {
      out[f] = row[f];
    }
  });
  return out;
}

// ====== CACHED DATA ======
function getCachedData_(sheetId) {
  var now = Date.now();
  if (_cache.data && _cache.sheetId === sheetId && (now - _cache.time) < _CACHE_TTL) {
    return _cache.data;
  }

  var ss = SpreadsheetApp.openById(sheetId);
  var sheet = ss.getSheets()[0];
  var values = sheet.getDataRange().getValues();

  if (values.length < 2) {
    _cache = { data: [], sheetId: sheetId, time: now };
    return [];
  }

  var headers = values[0].map(function(h) { return String(h || '').trim(); });
  var out = [];
  for (var i = 1; i < values.length; i++) {
    var row = {};
    for (var j = 0; j < headers.length; j++) {
      // v2.39: sel Date diserialisasi wall-clock sesuai sheet (bukan ISO UTC).
      row[headers[j]] = cellToText_(values[i][j], headers[j]);
    }
    out.push(row);
  }

  _cache = { data: out, sheetId: sheetId, time: now };
  return out;
}

// ====== JSON RESPONSE ======
function json_(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

// POST support (anti-cache)
function doPost(e) {
  return doGet(e);
}
