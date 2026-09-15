/**
 * BPF WorkHub — Bridge Google Apps Script untuk sheet RECEPTIONIST
 * (data Pelamar Kerja & In-Out Karyawan, v2.41.2).
 *
 * Kapan dipakai?
 *   Sheet masih publik ("Anyone with the link") → TIDAK perlu script ini;
 *   server membaca gviz CSV langsung. Begitu sheet dibuat PRIVAT, deploy
 *   script ini sebagai Web App lalu tempel URL /exec-nya di
 *   Pengaturan → 🔗 Sumber Sheet Receptionist.
 *
 * Prinsip penting (pelajaran dari bridge Overtime v3):
 *   - SEMUA helper diberi akhiran REC_ agar tidak bisa ditimpa sisa kode
 *     lama di proyek manapun.
 *   - NILAI DIAMBIL DARI getDisplayValues() — persis seperti yang dilihat
 *     user di sheet (teks), sehingga BEBAS dari bug serialisasi tanggal/jam
 *     (ISO UTC, epoch 1899, dsb.). Server parsing menerima format apa pun.
 *
 * PENANDA VERSI (anti "script lama menyamar"):
 *   <URL_/exec>?marker=1 → {"marker":"bpf-rec-sheet-2026-09-15-v1","module":"receptionist"}
 *
 * KONTRAK RESPON (dibaca _fetch_sheet_rows di server):
 *   { "rows": [ { "Nama Lengkap": "...", "Jam": "6:53:19 AM", ... }, ... ] }
 *   Nama kunci = header baris pertama APA ADANYA (server memetakan sendiri).
 *
 * DEPLOY:
 *   1. Buka https://script.google.com → New project (beri nama, mis.
 *      "BPF Receptionist Bridge v1").
 *   2. Isi SHEET_ID di bawah (ID dari URL spreadsheet: /d/<ID>/edit).
 *   3. SELECT ALL di Code.gs → DELETE → tempel SEMUA isi file ini.
 *   4. Ctrl+S → Deploy → New deployment → Type: Web app
 *      - Execute as: Me
 *      - Who has access: Anyone
 *      → Deploy → copy URL /exec.
 *   5. Uji: buka <URL>/exec?marker=1 di browser → harus tampil JSON marker.
 *   6. Tempel URL /exec ke BPF WorkHub: Pengaturan → 🔗 Sumber Sheet
 *      Receptionist → klik 🧪 Uji → 💾 Simpan URL.
 *   Catatan: sheet boleh privat — yang "publik" hanyalah Web App ini.
 *   Update kode → Deploy → Manage deployments → ✏️ → New version.
 */

// ====== KONFIGURASI ======
var SHEET_ID = 'GANTI_DENGAN_ID_SPREADSHEET'; // /spreadsheets/d/<ID>/edit

// ====== PENANDA VERSI ======
var REC_MARKER = 'bpf-rec-sheet-2026-09-15-v1';
var REC_CODE_REV = 1;

// ====== HANDLER WEB APP ======
function doGet(e) {
  var params = (e && e.parameter) || {};
  if (params.marker) {
    return REC_json_({ marker: REC_MARKER, code_rev: REC_CODE_REV,
                       module: 'receptionist', sheet_id: SHEET_ID });
  }
  var modul = (params.modul || 'applicants').toLowerCase();
  var tabName = params.tab || '';
  try {
    var ss = SpreadsheetApp.openById(SHEET_ID);
    var sh = tabName ? ss.getSheetByName(tabName) : ss.getSheets()[0];
    if (!sh) return REC_json_({ error: 'Tab tidak ditemukan: ' + tabName });
    var values = sh.getDataRange().getDisplayValues(); // teks persis di sheet
    if (!values.length) return REC_json_({ rows: [], total: 0, module: modul });
    var headers = values[0];
    var rows = [];
    for (var r = 1; r < values.length; r++) {
      var row = {};
      var hasValue = false;
      for (var c = 0; c < headers.length; c++) {
        var key = String(headers[c] || '').trim();
        if (!key) continue; // kolom tanpa header (mis. "Tidak Penting?") dilewati
        var v = String(values[r][c] || '').trim();
        if (v) hasValue = true;
        // Kunci duplikat (kolom header sama) → gabung dengan spasi
        row[key] = row[key] ? (row[key] + ' ' + v) : v;
      }
      rows.push(row);
    }
    return REC_json_({ rows: rows, total: rows.length, module: modul,
                       sheet: ss.getName(), tab: sh.getName(),
                       marker: REC_MARKER, code_rev: REC_CODE_REV });
  } catch (err) {
    return REC_json_({ error: String(err) });
  }
}

function REC_json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
