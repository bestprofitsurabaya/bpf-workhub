/**
 * BPF WorkHub — Bridge Google Apps Script untuk sheet Overtime DRIVER.
 * VERSI 3 (REV 2, 11 Sep 2026) — nama file baru + penanda versi + nama fungsi
 * unik sehingga TIDAK bisa ditimpa sisa kode lama di proyek manapun.
 *
 * RIWAYAT REV:
 *   rev 1 — terbitan awal v3 (marker + wall-clock utk sel Date).
 *   rev 2 — (a) SEMUA helper diberi akhiran V3_ (getVachedData_ lama dkk tidak
 *           bisa menimpa — penyebab tersangka feed ISO saat rev 1);
 *           (b) sel bertipe STRING ISO-UTC ikut dikonversi ke wall-clock
 *           (penyebab tersangka kedua: sel sheet tersimpan sbg teks);
 *           (c) ?debug=1 untuk diagnosis jarak jauh; code_rev di tiap respons.
 *   rev 3 — AKAR MASALAH SEBENARNYA (terbukti via ?debug=1): sel tanggal dari
 *           getValues() adalah objek mirip-Date yang GAGAL `instanceof Date`
 *           (bug sandbox/context Apps Script) → masuk cabang JSON.stringify →
 *           ISO UTC. Fix: deteksi via duck-typing (.getTime) + normalisasi ke
 *           Date asli context script; Utilities.formatDate bekerja normal.
 *   rev 4 — ?debug=1 perluas: probe baris terpilih (display vs raw) + daftar
 *           tab. TEMUAN: sel jam Driver = durasi epoch-1899; formatDate dgn
 *           zona 'Asia/Jakarta' memakai offset HISTORIS 1899 (+07:07:12)
 *           → semua jam bergeser sistematis (display 18:30 terbaca 18:55:08).
 *   rev 5 — FIX FINAL: sel JAM-MURNI (epoch < 1900) diserialisasi dari
 *           getDisplayValue() (ground truth yang dilihat user di sheet),
 *           fallback formatDate bila kosong. Kolom tanggal/timestamp asli
 *           tetap formatDate (aman — bukan epoch 1899).
 *
 * PENANDA VERSI (anti "script lama menyamar"):
 *   <URL_/exec>?marker=1 →
 *     {"marker":"bpf-ot-driver-2026-09-11-v3","code_rev":2,"module":"driver",...}
 *   code_rev < 2 → paste lama; tanpa marker → kode lama bukan v3.
 *   <URL_/exec>?debug=1 → tipe data sel Timestamp baris-1 + jejak panjang
 *   source fungsi (utk memastikan tidak ada definisi ganda yang menimpa).
 *
 * KONTRAK TANGGAL/JAM (v2.39): sel Date ATAU string ISO-UTC diserialisasi
 * sebagai TEKS sesuai tampilan sheet (zona SPREADSHEET):
 *   - Kolom tanggal (Tanggal Overtime) → 'yyyy-MM-dd'
 *   - Kolom timestamp (Timestamp)      → 'yyyy-MM-dd HH:mm:ss'
 *   - Kolom jam (Dari/IN, Sampai/OUT)  → 'HH:mm:ss' (epoch 1899 tetap benar)
 * Server memakai nilai APA ADANYA (tanpa offset) — jam aplikasi = jam sheet.
 *
 * PARAMETER:
 *   ?marker=1 — cek versi (tanpa baca sheet)   ?debug=1 — diagnosis tipe sel
 *   ?year/?month/?from/?to/?since/?limit/?offset/?fields/?summary — spt sebelumnya
 *
 * DEPLOY (11 Sep 2026, proyek baru "BPF OT Driver Bridge v3"):
 *   1. SELECT ALL di Code.gs → DELETE → tempel SEMUA isi file ini (SATU file .gs).
 *   2. Ctrl+S → Deploy → Manage deployments → ✏️ → Version: New version → Deploy.
 *   3. URL /exec TIDAK berubah. Verifikasi ?marker=1 → code_rev:3.
 */

// ====== PENANDA VERSI ======
var BRIDGE_MARKER = 'bpf-ot-driver-2026-09-11-v3';
var CODE_REV = 5;

// ====== CACHE (in-memory, reset setiap cold start ~5 min) ======
var _cacheV3 = {};
var _CACHE_TTL_V3 = 5 * 60 * 1000; // 5 minutes

// ====== ZONA WAKTU & SERIALIZASI (wall-clock sesuai sheet) ======
var _tzCacheV3 = null;
function sheetTimeZoneV3_() {
  if (_tzCacheV3) return _tzCacheV3;
  try {
    _tzCacheV3 = SpreadsheetApp.openById(SHEET_ID).getSpreadsheetTimeZone();
  } catch (err) {
    _tzCacheV3 = Session.getScriptTimeZone() || 'Asia/Jakarta';
  }
  return _tzCacheV3;
}

function isTimeColumnV3_(header) {
  var h = String(header || '').toLowerCase();
  if (/(tanggal|date|timestamp)/.test(h)) return false;
  return /(waktu|jam|mulai|selesai|dari|\bin\b|sampai|\bout\b|time)/.test(h);
}

function isDateOnlyColumnV3_(header) {
  var h = String(header || '').toLowerCase();
  return /(tanggal|date)/.test(h) && !/timestamp/.test(h);
}

// rev 3: Date dari getValues() bisa gagal `instanceof Date` di context
// Apps Script tertentu (bug sandbox) → JSON.stringify mengirim ISO UTC.
// Duck-typing: objek dgn .getTime() diperlakukan sbg tanggal, lalu
// dinormalisasi ke Date asli dalam context script ini.
function isDateLikeV3_(v) {
  if (v instanceof Date) return true;
  if (Object.prototype.toString.call(v) === '[object Date]') return true;
  return typeof v === 'object' && v !== null && typeof v.getTime === 'function';
}

function toDateV3_(v) {
  if (v instanceof Date) return v;
  try {
    if (v && typeof v.getTime === 'function') {
      var t = v.getTime();
      if (typeof t === 'number' && !isNaN(t)) return new Date(t);
    }
  } catch (err) { /* fallthrough */ }
  return null;
}

function dateToTextV3_(v, header, disp) {
  var d = toDateV3_(v);
  if (!d) return (v === null || v === undefined) ? '' : String(v);
  var tz = sheetTimeZoneV3_();
  if (d.getFullYear() < 1900) {
    // Sel JAM/durasi murni (epoch 1899-12-30). PENTING (rev 5): bila zona
    // spreadsheet memakai nama kota berzona historis (mis. 'Asia/Jakarta',
    // offset 1899 = +07:07:12), formatDate menggeser jam sistematis (display
    // 18:30 terbaca 18:55:08). Ground truth = TAMPILAN SEL yang dilihat user.
    if (typeof disp === 'string' && /^\d{1,3}:\d{2}(:\d{2})?$/.test(disp.trim())) {
      var t = disp.trim();
      return t.length === 5 ? t + ':00' : t;
    }
    return Utilities.formatDate(d, tz, 'HH:mm:ss');
  }
  if (isTimeColumnV3_(header)) return Utilities.formatDate(d, tz, 'HH:mm:ss');
  if (isDateOnlyColumnV3_(header)) return Utilities.formatDate(d, tz, 'yyyy-MM-dd');
  return Utilities.formatDate(d, tz, 'yyyy-MM-dd HH:mm:ss');
}

// String ISO-UTC ('2020-12-12T07:08:54.000Z') → wall-clock zona sheet.
// rev 2: beberapa sheet menyimpan tanggal sbg TEKS, bukan objek Date.
var ISO_UTC_RE_V3 = /^(\d{4})-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$/;

function isoUtcToWallV3_(s, header) {
  // Sel jam murni (epoch 1899): bagian jam-nya SUDAH wall-clock — pakai apa adanya.
  if (s.slice(0, 4) === '1899') return s.slice(11, 19); // 'HH:mm:ss'
  try {
    var d = new Date(s); // di-parse sebagai UTC instant
    if (isNaN(d.getTime())) return s;
    return Utilities.formatDate(
      d, sheetTimeZoneV3_(),
      isDateOnlyColumnV3_(header) ? 'yyyy-MM-dd' : 'yyyy-MM-dd HH:mm:ss');
  } catch (err) {
    return s;
  }
}

function cellToTextV3_(v, header, disp) {
  if (isDateLikeV3_(v)) return dateToTextV3_(v, header, disp);
  if (v === null || v === undefined) return '';
  if (typeof v === 'string' && ISO_UTC_RE_V3.test(v)) return isoUtcToWallV3_(v, header);
  if (v instanceof Object) return JSON.stringify(v);
  return v;
}

// Parse string wall-clock 'yyyy-MM-dd[ HH:mm[:ss]]' secara deterministik
// (waktu lokal script) — dipakai untuk bandingkan filter tanggal/since.
function parseWallV3_(s) {
  var d0 = toDateV3_(s);
  if (d0) return d0;
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

    // Penanda versi: /exec?marker=1 → JSON kecil utk verifikasi deployment
    if (params.marker === '1') {
      return jsonV3_({ marker: BRIDGE_MARKER, code_rev: CODE_REV, module: 'driver', rows: [], total: 0 });
    }

    // Diagnosis jarak jauh: tipe sel Timestamp baris-1 + jejak definisi ganda
    if (params.debug === '1') {
      var dbg = { code_rev: CODE_REV, sheet_id_tail: String(SHEET_ID).slice(-6) };
      try {
        var rows0 = getCachedDataV3_(SHEET_ID);
        var v0 = rows0.length ? rows0[0]['Timestamp'] : null;
        dbg.total_rows = rows0.length;
        dbg.ts0_value = String(v0 === undefined || v0 === null ? '' : v0).slice(0, 60);
        dbg.ts0_typeof = typeof v0;
        dbg.ts0_is_date = v0 instanceof Date;
        dbg.ts0_is_datelike = isDateLikeV3_(v0);
        try {
          dbg.ts0_fixed = v0 ? String(cellToTextV3_(v0, 'Timestamp')).slice(0, 40) : null;
        } catch (err3) {
          dbg.ts0_fixed_err = String(err3);
        }
        try { dbg.sheet_tz = sheetTimeZoneV3_(); } catch (errTz) { /* abaikan */ }
      } catch (err2) {
        dbg.read_error = String(err2);
      }
      // rev 4 — bedah baris Guruh terakhir: tampilan sheet vs nilai mentah sel jam
      try {
        var ssD = SpreadsheetApp.openById(SHEET_ID);
        dbg.tabs = ssD.getSheets().map(function(s) { return s.getName() + ':' + s.getLastRow(); }).slice(0, 6);
        var shD = ssD.getSheets()[0];
        var headsD = shD.getRange(1, 1, 1, shD.getLastColumn()).getValues()[0];
        var cols = { nameCol: -1, inCol: -1, outCol: -1, tsCol: -1 };
        for (var c = 0; c < headsD.length; c++) {
          var hh = String(headsD[c] || '').toLowerCase();
          if (cols.nameCol < 0 && hh.indexOf('nama') >= 0) cols.nameCol = c + 1;
          if (cols.inCol < 0 && hh.indexOf('dari') >= 0) cols.inCol = c + 1;
          if (cols.outCol < 0 && hh.indexOf('sampai') >= 0) cols.outCol = c + 1;
          if (cols.tsCol < 0 && hh.indexOf('timestamp') >= 0) cols.tsCol = c + 1;
        }
        dbg.cols = cols;
        var lastRowD = shD.getLastRow();
        var found = -1;
        if (cols.nameCol > 0) {
          var scanFrom = Math.max(2, lastRowD - 500);
          var names = shD.getRange(scanFrom, cols.nameCol, lastRowD - scanFrom + 1, 1).getValues();
          for (var i = names.length - 1; i >= 0; i--) {
            if (String(names[i][0]).toLowerCase().indexOf('guruh') >= 0) { found = scanFrom + i; break; }
          }
        }
        if (found > 0) {
          var probe = { row: found };
          ['inCol', 'outCol', 'tsCol'].forEach(function(key) {
            var cn = cols[key];
            if (cn > 0) {
              var disp = shD.getRange(found, cn).getDisplayValue();
              var raw = shD.getRange(found, cn).getValue();
              var rawStr = isDateLikeV3_(raw)
                ? Utilities.formatDate(toDateV3_(raw), sheetTimeZoneV3_(), "yyyy-MM-dd HH:mm:ss.SSSZ")
                : String(raw);
              probe[key] = { header: String(headsD[cn - 1]), display: disp, raw: rawStr, typeof: typeof raw };
            }
          });
          dbg.guruh_row = probe;
        } else {
          dbg.guruh_row = 'tidak ketemu di ' + (lastRowD - 500) + '..' + lastRowD;
        }
      } catch (err4) {
        dbg.sheet_probe_err = String(err4);
      }
      dbg.len_doGet = String(doGet).length;
      dbg.len_cellToText = String(cellToTextV3_).length;
      dbg.len_getCachedData = String(getCachedDataV3_).length;
      return jsonV3_({ marker: BRIDGE_MARKER, module: 'driver', debug: dbg, rows: [], total: 0 });
    }

    // Parse parameters
    var year      = params.year      ? parseInt(params.year, 10)      : null;
    var month     = params.month     ? parseInt(params.month, 10)     : null;
    var fromDate  = params.from      ? parseDateV3_(params.from)       : null;
    var toDate    = params.to        ? parseDateV3_(params.to)         : null;
    var since     = params.since     ? parseWallV3_(params.since)      : null;
    var limit     = params.limit     ? Math.max(parseInt(params.limit, 10) || 0, 0) : 0;
    var offset    = params.offset    ? Math.max(parseInt(params.offset, 10) || 0, 0) : 0;
    var fields    = params.fields    ? params.fields.split(',').map(function(f) { return f.trim(); }) : null;
    var summary   = params.summary === 'true';

    // Get all data (with cache)
    var allRows = getCachedDataV3_(SHEET_ID);

    // Filter
    var filtered = filterRowsV3_(allRows, year, month, fromDate, toDate, since);
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
      output = paged.map(function(row) { return summarizeV3_(row); });
    } else if (fields) {
      output = paged.map(function(row) { return pickFieldsV3_(row, fields); });
    } else {
      output = paged;
    }

    var response = {
      marker: BRIDGE_MARKER,
      code_rev: CODE_REV,
      rows: output,
      total: total
    };

    // Only include pagination metadata when limit is used
    if (limit > 0) {
      response.limit = limit;
      response.offset = offset;
      response.hasMore = (offset + limit) < total;
    }

    return jsonV3_(response);

  } catch (err) {
    return jsonV3_({ error: String(err), marker: BRIDGE_MARKER, code_rev: CODE_REV, rows: [], total: 0 });
  }
}

// ====== FILTER ======
function filterRowsV3_(rows, year, month, fromDate, toDate, since) {
  if (!year && !month && !fromDate && !toDate && !since) {
    return rows; // No filter, return all
  }

  return rows.filter(function(row) {
    // Use Timestamp for since filter (faster, always present)
    var tsRaw = since ? row['Timestamp'] : null;
    if (since && tsRaw) {
      var tsDate = parseWallV3_(tsRaw);
      if (tsDate && tsDate < since) return false;
    }

    // Use Tanggal Overtime for year/month/date filters
    var ts = row['Tanggal Overtime'] || row['Timestamp'];
    if (!ts) return false;

    var d = parseWallV3_(ts);
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
function parseDateV3_(str) {
  // Accept YYYY-MM-DD format
  var parts = str.split('-');
  if (parts.length === 3) {
    return new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
  }
  return new Date(str);
}

// ====== SUMMARIZE (remove heavy fields like photo URLs) ======
function summarizeV3_(row) {
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
function pickFieldsV3_(row, fields) {
  var out = {};
  fields.forEach(function(f) {
    if (row.hasOwnProperty(f)) {
      out[f] = row[f];
    }
  });
  return out;
}

// ====== CACHED DATA ======
function getCachedDataV3_(sheetId) {
  var now = Date.now();
  if (_cacheV3.data && _cacheV3.sheetId === sheetId && (now - _cacheV3.time) < _CACHE_TTL_V3) {
    return _cacheV3.data;
  }

  var ss = SpreadsheetApp.openById(sheetId);
  var sheet = ss.getSheets()[0];
  var values = sheet.getDataRange().getValues();

  if (values.length < 2) {
    _cacheV3 = { data: [], sheetId: sheetId, time: now };
    return [];
  }

  var headers = values[0].map(function(h) { return String(h || '').trim(); });
  // rev 5: tampilan sel = ground truth utk sel jam/durasi (epoch 1899).
  var dispAll = sheet.getDataRange().getDisplayValues();
  var out = [];
  for (var i = 1; i < values.length; i++) {
    var row = {};
    for (var j = 0; j < headers.length; j++) {
      // Sel Date / string ISO-UTC diserialisasi wall-clock sesuai sheet;
      // sel jam-murni memakai tampilan sel (lihat dateToTextV3_ rev 5).
      row[headers[j]] = cellToTextV3_(values[i][j], headers[j],
                                      dispAll[i] ? dispAll[i][j] : undefined);
    }
    out.push(row);
  }

  _cacheV3 = { data: out, sheetId: sheetId, time: now };
  return out;
}

// ====== JSON RESPONSE ======
function jsonV3_(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

// POST support (anti-cache)
function doPost(e) {
  return doGet(e);
}
