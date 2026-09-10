/**
 * BPF WorkHub — Bridge Google Apps Script untuk sheet Overtime DRIVER.
 *
 * MASALAH:
 *   Sheet overtime Driver (1L-7Z…p48gVZEbDJS-azMqpGobmvmqCDB9J6sAB3DGM)
 *   PRIVATE — hanya bisa dibaca akun yang diberi akses (mis. view saja).
 *   Server BPF WorkHub tidak bisa login ke Google, jadi tombol "Refresh"
 *   tidak bisa membaca CSV-nya langsung (401).
 *
 * SOLUSI (TIDAK perlu akses ke akun PEMILIK):
 *   Cukup salah satu akun Google yang SUDAH punya akses ke sheet — termasuk
 *   akses VIEW (read-only) — membuat script standalone ini lalu di-deploy
 *   sebagai "Web App" dengan akses "Anyone". Karena script dieksekusi
 *   sebagai akun tersebut (yang punya akses baca), ia bisa membaca sheet
 *   private, lalu hasilnya dikembalikan sebagai JSON publik. Sheet TIDAK
 *   perlu diubah pengaturannya, pemilik tidak perlu dilibatkan.
 *
 * LANGKAH DEPLOY (sekali saja, di akun Google mana pun yang punya akses):
 *   1. Buka https://script.google.com → "New project" (proyek STANDALONE,
 *      jangan lewat menu sheet — menu itu butuh akses edit).
 *   2. Hapus isi Code.gs, tempel SEMUA kode di bawah, lalu simpan (Ctrl+S).
 *   3. Klik "Deploy" → "New deployment" → pilih type "Web app".
 *   4. Atur:
 *        - Execute as:  Me (akun Anda yang punya akses ke sheet)
 *        - Who has access: Anyone
 *   5. Saat diminta izin (Authorization): pilih akun yang sama, klik
 *      "Advanced" → "Go to <proyek> (unsafe)" → Allow. Izin "view" ke
 *      spreadsheet cukup — script hanya MEMBACA, tidak menulis.
 *   6. Klik Deploy → salin URL Web App (https://script.google.com/macros/s/…/exec)
 *   7. Tempel URL itu di dashboard GA HR → tombol ⚙️ Sumber Data → Simpan.
 *      Tombol 🔄 Refresh kini menarik data dari sheet (tetap private).
 *
 * v2.39 — KONTRAK TANGGAL/JAM BARU (fix "jam tidak sesuai sumber"):
 *   Nilai Date dari getValues() TIDAK lagi di-JSON.stringify mentah (ISO UTC,
 *   yang membuat server menambah +7 jam dengan asumsi sheet berzona WIB).
 *   Sel Date kini diserialisasi sebagai TEKS sesuai tampilan sheet:
 *   Utilities.formatDate + zona waktu SPREADSHEET (tanggal → 'yyyy-MM-dd',
 *   Timestamp → 'yyyy-MM-dd HH:mm:ss', kolom jam → 'HH:mm:ss'). Server
 *   memakai nilai ini APA ADANYA — jam di aplikasi = jam di sheet.
 */

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

function doGet(e) {
  // Ganti ID ini bila sheet Driver diganti.
  var SHEET_ID = '1L-7ZT0p48gVZEbDJS-azMqpGobmvmqCDB9J6sAB3DGM';

  try {
    var ss = SpreadsheetApp.openById(SHEET_ID);
    var sheet = ss.getSheets()[0];
    var values = sheet.getDataRange().getValues();
    var out = [];

    if (values.length < 2) {
      return json_({ rows: [], total: 0 });
    }

    var headers = values[0].map(function (h) { return String(h || '').trim(); });
    for (var i = 1; i < values.length; i++) {
      var row = {};
      for (var j = 0; j < headers.length; j++) {
        // v2.39: sel Date diserialisasi wall-clock sesuai sheet (bukan ISO UTC).
        row[headers[j]] = cellToText_(values[i][j], headers[j]);
      }
      out.push(row);
    }

    return json_({ rows: out, total: out.length });
  } catch (err) {
    return json_({ error: String(err), rows: [] });
  }
}

function json_(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

// Opsional: versi POST (anti-cache tambahan) — sama outputnya dengan doGet.
function doPost(e) {
  return doGet(e);
}
