/**
 * BPF WorkHub — Bridge Google Apps Script untuk sheet Overtime OB & SECURITY.
 *
 * Pola sama dengan apps_script_overtime_driver_v2.gs — dibuat agar tombol
 * "Refresh" OB/Security di dashboard GA HR tetap bisa membaca sheet yang
 * PRIVATE (diisi Google Form), tanpa mengubah izin sheet atau melibatkan
 * akun pemilik.
 *
 * MASALAH:
 *   Sheet OB/Security (1AsBq-rHssGmv5vHAzorrphZeNxchodkJQXz1wdBPoms) hanya
 *   bisa dibaca akun yang diberi akses. Server BPF WorkHub tidak bisa login
 *   ke Google, jadi fetch langsung ke URL sheet mengembalikan HTML (bukan
 *   CSV/JSON) → sinkronisasi tidak pernah berhasil.
 *
 * SOLUSI (sama seperti Driver — TIDAK perlu akses ke akun PEMILIK):
 *   Cukup salah satu akun Google yang SUDAH punya akses ke sheet (termasuk
 *   akses VIEW/read-only) membuat script standalone ini lalu di-deploy
 *   sebagai "Web App" dengan akses "Anyone". Script dieksekusi sebagai akun
 *   tersebut (yang punya akses baca), membaca sheet private, lalu hasilnya
 *   dikembalikan sebagai JSON publik. Sheet TIDAK perlu diubah izinnya.
 *
 * KONTRAK OUTPUT (harus sama dengan ekspektasi server routes_overtime.py):
 *   - Row = {header: nilai} dengan key persis nama kolom Google Sheet.
 *   - Nilai tanggal/jam dari getValues() berupa Date → JSON.stringify
 *     mengirim ISO 8601 UTC ("2020-12-12T07:08:54.000Z"). Server menambah
 *     +7 jam (WIB) saat parse — sama dengan sheet Driver.
 *   - Foto (Upload Foto Mulai/Selesai) berupa URL teks → server simpan utuh.
 *
 * PARAMETER (query string) — backward compatible, tanpa parameter = semua data:
 *   ?year=2025            — Filter tahun (kolom Tanggal)
 *   ?month=08             — Filter bulan (1-12)
 *   ?from=2025-08-01      — Filter tanggal mulai (YYYY-MM-DD)
 *   ?to=2025-08-31        — Filter tanggal sampai (YYYY-MM-DD)
 *   ?since=2025-08-19T00:00:00 — Incremental: hanya baris Timestamp >= ini
 *   ?limit=100            — Jumlah record maks per request (0 = semua)
 *   ?offset=0             — Offset untuk pagination
 *   ?fields=Nama,Tanggal  — Hanya field tertentu (comma-separated)
 *   ?summary=true         — Tanpa field berat (foto/URL)
 *
 * CONTOH:
 *   /exec                              → Semua data
 *   /exec?since=2026-09-04T00:00:00    → Baris baru sejak 4 Sep (dipakai
 *                                        sinkronisasi incremental server)
 *
 * LANGKAH DEPLOY (sekali saja, di akun Google mana pun yang punya akses):
 *   1. Buka https://script.google.com → "New project" (proyek STANDALONE,
 *      jangan lewat menu sheet — menu itu butuh akses edit).
 *   2. Hapus isi Code.gs, tempel SEMUA kode di bawah, simpan (Ctrl+S).
 *   3. Klik "Deploy" → "New deployment" → type "Web app".
 *   4. Atur:
 *        - Execute as:  Me (akun Anda yang punya akses ke sheet)
 *        - Who has access: Anyone
 *   5. Saat diminta izin: pilih akun yang sama → "Advanced" → "Go to <proyek>
 *      (unsafe)" → Allow. Izin "view" spreadsheet cukup — script hanya
 *      MEMBACA, tidak menulis.
 *   6. Salin URL Web App (https://script.google.com/macros/s/…/exec).
 *   7. Tempel URL itu di dashboard GA HR → tab OB/Security → ⚙️ Sumber Data →
 *      Simpan (menggantikan URL sheet yang lama), lalu klik 🔄 Refresh.
 */

// ====== KONFIGURASI ======
// ID sheet OB & SECURITY — dari URL:
// https://docs.google.com/spreadsheets/d/1AsBq-rHssGmv5vHAzorrphZeNxchodkJQXz1wdBPoms/edit
var SHEET_ID = '1AsBq-rHssGmv5vHAzorrphZeNxchodkJQXz1wdBPoms';

// ====== CACHE (in-memory, reset setiap cold start ~5 min) ======
var _cache = {};
var _CACHE_TTL = 5 * 60 * 1000; // 5 minutes

function doGet(e) {
  try {
    var params = (e && e.parameter) ? e.parameter : {};

    // Parse parameters
    var year      = params.year      ? parseInt(params.year, 10)      : null;
    var month     = params.month     ? parseInt(params.month, 10)     : null;
    var fromDate  = params.from      ? parseDate_(params.from)         : null;
    var toDate    = params.to        ? parseDate_(params.to)           : null;
    var since     = params.since     ? new Date(params.since)          : null;
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
      paged = filtered;
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
      var tsDate;
      if (tsRaw instanceof Date) {
        tsDate = tsRaw;
      } else {
        tsDate = new Date(tsRaw);
      }
      if (!isNaN(tsDate.getTime()) && tsDate < since) return false;
    }

    // Use Tanggal (overtime date) for year/month/date filters
    var ts = row['Tanggal'] || row['Timestamp'];
    if (!ts) return false;

    var d;
    if (ts instanceof Date) {
      d = ts;
    } else {
      d = new Date(ts);
    }
    if (isNaN(d.getTime())) return false;

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
  var parts = String(str).split('-');
  if (parts.length === 3) {
    return new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
  }
  return new Date(str);
}

// ====== SUMMARIZE (remove heavy fields like photo URLs) ======
function summarize_(row) {
  return {
    'Timestamp':           row['Timestamp'],
    'Email Address':       row['Email Address'],
    'Nama Lengkap':        row['Nama Lengkap'],
    'Tanggal':             row['Tanggal'],
    'Waktu Mulai Overtime': row['Waktu Mulai Overtime'],
    'Waktu Selesai Overtime': row['Waktu Selesai Overtime'],
    'Keterangan':          row['Keterangan']
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
      row[headers[j]] = values[i][j];
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
