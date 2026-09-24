/**
 * BPF WorkHub — Bridge Google Apps Script untuk sheet RECEPTIONIST — v2 REALTIME
 * (data Pelamar Kerja & In-Out Karyawan, v2.42.0 — DUA SPREADSHEET TERPISAH).
 *
 * APA YANG BARU DI v2 (beda dari v1)?
 *   v1: hanya "ditarik" server (pull) saat sync berkala / login / tombol Refresh.
 *   v2: sheet MENDORONG setiap edit langsung ke aplikasi (push) lewat trigger
 *       onEdit → webhook POST /api/receptionist/webhook. Hasilnya data di
 *       aplikasi nyaris realtime (detik setelah edit), sejajar pengalaman
 *       overtime di GA HR — bahkan lebih cepat (tanpa menunggu refresh).
 *       Pull (v1 URL /exec?modul=...) TETAP AKTIF sebagai jaring pengaman bila
 *       push gagal (jaringan/kuota Apps Script) — keduanya dipakai bersama.
 *
 * STRUKTUR DATA (v2.1):
 *   DUA spreadsheet TERPISAH, satu deploy Apps Script:
 *     - SHEET_ID_APPLICANTS → berisi tab data Pelamar Kerja
 *     - SHEET_ID_INOUT      → berisi tab data In-Out Karyawan
 *   Trigger onEdit dipasang ke KEDUA spreadsheet oleh REC_v2_pasangTrigger_.
 *   Kedua SHEET_ID WAJIB BERBEDA — push onEdit membedakan modul (pelamar vs
 *   in-out) dari spreadsheet asal edit; bila sama, pemasangan trigger
 *   dibatalkan dengan pesan jelas (lihat REC_v2_validasiKonfig_).
 *
 * CARA KERJA PUSH:
 *   Trigger terpasang (installable) onEdit per spreadsheet → deteksi asal
 *   (spreadsheet id + nama tab) → kirim BARIS YANG DIEDIT saja (header + nilai
 *   baris) sebagai JSON ke WEBHOOK_URL dengan header X-BPF-Token (secret dari
 *   Web App Properties). Server melakukan upsert berdasar kunci stabil (md5
 *   nama|tanggal|jam utk pelamar, md5 isi baris utk in-out) — aman walau
 *   baris bergeser.
 *
 * PENANDA VERSI (anti "script lama menyamar"):
 *   <URL_/exec>?marker=1 → {"marker":"bpf-rec-sheet-2026-09-23-v2","code_rev":5,...}
 *   Marker juga memuat config_issues — daftar masalah konfigurasi (mis. kedua
 *   SHEET_ID sama) yang bisa dilihat tanpa membuka editor Apps Script.
 *
 * KONTRAK PULL (dibaca _fetch_sheet_rows di server):
 *   { "rows": [ { "Nama Lengkap": "...", "Jam": "6:53:19 AM", ... }, ... ] }
 *   ?modul=applicants → baca spreadsheet pelamar; ?modul=inout → in-out.
 * KONTRAK PUSH (dibaca POST /api/receptionist/webhook di server):
 *   { "modul": "inout" | "applicants", "rows": [ {<header: nilai satu baris>} ] }
 *
 * DEPLOY:
 *   1. Buka https://script.google.com → New project (nama: "BPF Receptionist Bridge v2").
 *   2. Isi konfigurasi di bawah:
 *      - SHEET_ID_APPLICANTS : ID spreadsheet pelamar (URL /d/<ID>/edit)
 *      - SHEET_ID_INOUT      : ID spreadsheet in-out karyawan
 *      - TAB_APPLICANTS / TAB_INOUT : nama tab sumber di masing-masing file
 *        (boleh dibiarkan; bila nama tab tidak cocok, tab PERTAMA file yang dipakai)
 *      - WEBHOOK_URL : https://<host-aplikasi>/api/receptionist/webhook
 *      - SECRET      : ambil dari BPF WorkHub → Pengaturan → Sumber Sheet
 *                      Receptionist → Webhook Realtime (admin) → salin secret.
 *   3. SELECT ALL di Code.gs → DELETE → tempel SEMUA isi file ini → Ctrl+S.
 *      Lalu jalankan REC_v2_cekKonfigurasi di editor — pastikan log "✔
 *      Konfigurasi OK" (cek ini juga mendeteksi kedua SHEET_ID yang sama).
 *   4. Deploy → New deployment → Web app (Execute as: Me, access: Anyone)
 *      → copy URL /exec (untuk PULL) → tempel di Pengaturan sumber sheet
 *      (satu URL untuk kedua modul; server membedakan via ?modul=...).
 *   5. Jalankan fungsi REC_v2_pasangTrigger_ SEKALI dari editor (atau reload
 *      sheet — onEdit simple juga dipasang otomatis via REC_v2_installHint).
 *      Cek log Eksekusi: "✔ Trigger onEdit terpasang: ..." (2 baris, pelamar & in-out).
 *   6. Uji PUSH: edit satu sel di tab In-Out → di BPF WorkHub halaman In-Out
 *      Karyawan baris baru muncul dalam beberapa detik (tanpa klik Refresh).
 *   Update kode → Deploy → Manage deployments → ✏️ → New version.
 */

// ====== KONFIGURASI ======
// ID spreadsheet PELAMAR KERJA — bagian /spreadsheets/d/<ID>/edit dari URL.
var SHEET_ID_APPLICANTS = 'GANTI_DENGAN_ID_SPREADSHEET_PELAMAR';
// ID spreadsheet IN-OUT KARYAWAN (file terpisah).
var SHEET_ID_INOUT = 'GANTI_DENGAN_ID_SPREADSHEET_INOUT';
// Nama tab sumber data di masing-masing spreadsheet — push hanya untuk tab ini.
var TAB_APPLICANTS = 'Form Responses'; // ganti sesuai nama tab pelamar
var TAB_INOUT = 'In-Out';              // ganti sesuai nama tab in-out
var WEBHOOK_URL = 'https://GANTI-HOST/api/receptionist/webhook';

// ====== PENANDA VERSI ======
var REC_MARKER = 'bpf-rec-sheet-2026-09-23-v2';
var REC_CODE_REV = 5; // 5 = validasi konfigurasi (SHEET_ID dua file wajib beda)

// Secret TIDAK ditulis di kode — simpan lewat File → Project properties:
//   REC_v2_setSecret('isi-secret-dari-pengaturan')  sekali di editor.
// Alternatif praktis: isi konstanta di bawah bila kebijakan tim mengizinkan.
var SECRET_INLINE = '';

function REC_v2_secret_() {
  if (SECRET_INLINE) return SECRET_INLINE;
  return PropertiesService.getScriptProperties().getProperty('REC_WEBHOOK_SECRET') || '';
}

/** Jalankan SEKALI di editor untuk menyimpan secret: REC_v2_setSecret('...') */
function REC_v2_setSecret(val) {
  PropertiesService.getScriptProperties().setProperty('REC_WEBHOOK_SECRET', String(val || ''));
}

/** Validasi + buka spreadsheet untuk modul tertentu ('applicants' | 'inout'). */
function REC_v2_ss_(modul) {
  var id = (modul === 'inout') ? SHEET_ID_INOUT : SHEET_ID_APPLICANTS;
  if (!id || String(id).indexOf('GANTI') === 0) {
    throw new Error('SHEET_ID untuk modul "' + modul + '" belum diisi di konfigurasi');
  }
  return SpreadsheetApp.openById(id);
}

/** Tab default untuk modul tertentu. */
function REC_v2_tab_(modul) {
  return (modul === 'inout') ? TAB_INOUT : TAB_APPLICANTS;
}

/** Validasi konfigurasi dasar. Return daftar masalah (kosong = OK).
 *  Dipanggil saat memasang trigger & dilaporkan via ?marker=1. */
function REC_v2_validasiKonfig_() {
  var masalah = [];
  var idA = String(SHEET_ID_APPLICANTS || '');
  var idB = String(SHEET_ID_INOUT || '');
  var terisiA = idA && idA.indexOf('GANTI') !== 0;
  var terisiB = idB && idB.indexOf('GANTI') !== 0;
  if (!terisiA) masalah.push('SHEET_ID_APPLICANTS belum diisi');
  if (!terisiB) masalah.push('SHEET_ID_INOUT belum diisi');
  if (terisiA && terisiB && idA === idB) {
    masalah.push('SHEET_ID_APPLICANTS dan SHEET_ID_INOUT SAMA — push onEdit tidak bisa ' +
                 'membedakan modul pelamar vs in-out. Pakai DUA spreadsheet berbeda.');
  }
  if (!WEBHOOK_URL || String(WEBHOOK_URL).indexOf('GANTI') === 0) {
    masalah.push('WEBHOOK_URL belum diisi');
  }
  if (!REC_v2_secret_()) {
    masalah.push('Secret belum disimpan — jalankan REC_v2_setSecret(\'isi-secret\') sekali');
  }
  return masalah;
}

/** Jalankan di editor kapan saja untuk cek konfigurasi: REC_v2_cekKonfigurasi */
function REC_v2_cekKonfigurasi() {
  var masalah = REC_v2_validasiKonfig_();
  if (!masalah.length) { console.log('✔ Konfigurasi OK — siap deploy & pasang trigger'); return; }
  console.error('❌ Konfigurasi belum valid:\n- ' + masalah.join('\n- '));
}

/** Sheet aktif utk modul: tab konfigurasi bila ada, else tab PERTAMA file.
 *  Mencegah push pull gagal diam-diam hanya karena nama tab beda. */
function REC_v2_activeTab_(ss, modul) {
  var wanted = REC_v2_tab_(modul);
  var sh = wanted ? ss.getSheetByName(wanted) : null;
  if (sh) return { sheet: sh, matched: true };
  return { sheet: ss.getSheets()[0], matched: false }; // fallback: tab pertama
}

// ====== HANDLER WEB APP (PULL — paritas v1) ======
function doGet(e) {
  var params = (e && e.parameter) || {};
  if (params.marker) {
    return REC_json_({ marker: REC_MARKER, code_rev: REC_CODE_REV,
                       module: 'receptionist', layout: 'two-spreadsheets',
                       sheet_id_applicants: SHEET_ID_APPLICANTS,
                       sheet_id_inout: SHEET_ID_INOUT,
                       tab_applicants: TAB_APPLICANTS, tab_inout: TAB_INOUT,
                       push: true, webhook_configured: !!(WEBHOOK_URL && REC_v2_secret_()),
                       config_ok: !REC_v2_validasiKonfig_().length,
                       config_issues: REC_v2_validasiKonfig_() });
  }
  var modul = (params.modul || 'applicants').toLowerCase();
  var tabName = params.tab || '';
  try {
    var ss = REC_v2_ss_(modul);
    var pick = tabName
      ? (function () { var s = ss.getSheetByName(tabName);
                        return s ? { sheet: s, matched: true } : null; })()
      : REC_v2_activeTab_(ss, modul);
    if (!pick || !pick.sheet) return REC_json_({ error: 'Tab tidak ditemukan: ' + tabName });
    var sh = pick.sheet;
    var values = sh.getDataRange().getDisplayValues(); // teks persis di sheet
    if (!values.length) return REC_json_({ rows: [], total: 0, module: modul });
    var headers = values[0];
    var rows = [];
    for (var r = 1; r < values.length; r++) {
      var obj = REC_v2_rowObj_(headers, values[r]);
      if (obj) rows.push(obj);
    }
    return REC_json_({ rows: rows, total: rows.length, module: modul,
                       sheet: ss.getName(), tab: sh.getName(),
                       tab_config_matched: pick.matched,
                       marker: REC_MARKER, code_rev: REC_CODE_REV });
  } catch (err) {
    return REC_json_({ error: String(err) });
  }
}

/** Gabungkan header + satu baris nilai → objek {header: nilai}. */
function REC_v2_rowObj_(headers, values) {
  var row = {};
  var hasValue = false;
  for (var c = 0; c < headers.length; c++) {
    var key = String(headers[c] || '').trim();
    if (!key) continue; // kolom tanpa header dilewati
    var v = String(values[c] || '').trim();
    if (v) hasValue = true;
    row[key] = row[key] ? (row[key] + ' ' + v) : v; // header duplikat → gabung
  }
  return hasValue ? row : null;
}

// ====== PUSH REALTIME (v2) — trigger onEdit per spreadsheet ======

/** Dipanggil simple trigger bila kode ditempel di proyek yang terikat sheet. */
function onEdit(e) {
  try { REC_v2_handleEdit_(e); } catch (err) { console.error('onEdit: ' + err); }
}

/** Pasang installable trigger ke KEDUA spreadsheet (jalankan SEKALI dari editor). */
function REC_v2_pasangTrigger_() {
  // Validasi dulu: bila kedua SHEET_ID sama, push onEdit salah arah modul
  // (edit pelamar terkirim sebagai in-out) — lebih baik gagal jelas di sini.
  var idA = String(SHEET_ID_APPLICANTS || ''), idB = String(SHEET_ID_INOUT || '');
  if (idA && idB && idA.indexOf('GANTI') !== 0 && idB.indexOf('GANTI') !== 0 && idA === idB) {
    console.error('❌ Pemasangan trigger DIBATALKAN: SHEET_ID_APPLICANTS dan ' +
                  'SHEET_ID_INOUT sama. Pakai DUA spreadsheet berbeda, lalu jalankan lagi.');
    return;
  }
  var masalah = REC_v2_validasiKonfig_();
  for (var m = 0; m < masalah.length; m++) console.warn('⚠️ Konfigurasi: ' + masalah[m]);
  var targets = [
    { id: SHEET_ID_APPLICANTS, label: 'Pelamar (' + TAB_APPLICANTS + ')' },
    { id: SHEET_ID_INOUT, label: 'In-Out (' + TAB_INOUT + ')' },
  ];
  var existing = ScriptApp.getProjectTriggers();
  for (var t = 0; t < targets.length; t++) {
    if (!targets[t].id || String(targets[t].id).indexOf('GANTI') === 0) {
      console.warn('SHEET_ID ' + targets[t].label + ' belum diisi — trigger dilewati');
      continue;
    }
    var ss = SpreadsheetApp.openById(targets[t].id);
    var sudah = false;
    for (var i = 0; i < existing.length; i++) {
      if (existing[i].getEventType() === ScriptApp.EventType.ON_EDIT &&
          existing[i].getHandlerFunction() === 'REC_v2_onEditInstallable' &&
          String(existing[i].getTriggerSourceId() || '') === String(targets[t].id)) {
        sudah = true; break;
      }
    }
    if (sudah) { console.log('Trigger sudah ada — skip: ' + targets[t].label); continue; }
    ScriptApp.newTrigger('REC_v2_onEditInstallable').forSpreadsheet(ss).onEdit().create();
    console.log('✔ Trigger onEdit terpasang: ' + targets[t].label);
  }
}

/** Installable trigger handler (cadangan utk simple trigger; jalan per sheet). */
function REC_v2_onEditInstallable(e) {
  try { REC_v2_handleEdit_(e); } catch (err) { console.error('onEditInstallable: ' + err); }
}

/** Tentukan modul dari asal edit (spreadsheet id dulu, lalu nama tab).
 *  Tab diterima bila cocok konfigurasi ATAU merupakan tab PERTAMA file —
 *  supaya nama tab asli yang beda dari tebakan default tetap ter-push. */
function REC_v2_modulFor_(ss, tab) {
  var id = '';
  try { id = String(ss && ss.getId ? ss.getId() : ''); } catch (err) { id = ''; }
  if (id === String(SHEET_ID_INOUT) || id === String(SHEET_ID_APPLICANTS)) {
    var modul = (id === String(SHEET_ID_INOUT)) ? 'inout' : 'applicants';
    if (REC_v2_sameTab_(tab, REC_v2_tab_(modul))) return modul;
    try {
      var first = ss.getSheets()[0];
      if (first && REC_v2_sameTab_(first.getName(), tab)) return modul;
    } catch (err) { /* abaikan */ }
    return null; // tab lain (mis. arsip) diabaikan
  }
  // Fallback bila id tak terbaca: cocokkan nama tab saja.
  if (REC_v2_sameTab_(tab, TAB_INOUT)) return 'inout';
  if (REC_v2_sameTab_(tab, TAB_APPLICANTS)) return 'applicants';
  return null;
}

function REC_v2_handleEdit_(e) {
  if (!e || !e.range) return;
  var sh = e.range.getSheet();
  var ss = sh.getParent();
  var tab = sh.getName();
  var modul = REC_v2_modulFor_(ss, tab);
  if (!modul) return; // edit di spreadsheet/tab lain diabaikan

  var rowIdx = e.range.getRow();
  if (rowIdx < 1) return;
  var headers = sh.getRange(1, 1, 1, sh.getLastColumn()).getDisplayValues()[0];
  if (rowIdx === 1) {
    // Header berubah — kirim tanda agar admin sinkron penuh via pull.
    REC_v2_push_({ modul: modul, rows: [], header_changed: true, tab: tab });
    return;
  }
  var values = sh.getRange(rowIdx, 1, 1, headers.length).getDisplayValues()[0];
  var rowObj = REC_v2_rowObj_(headers, values);
  if (!rowObj) return; // baris kosong
  rowObj['__row'] = String(rowIdx); // info tambahan (tidak dipakai server utk kunci)
  REC_v2_push_({ modul: modul, rows: [rowObj], tab: tab, row: rowIdx });
}

function REC_v2_sameTab_(a, b) {
  return String(a || '').trim().toLowerCase() === String(b || '').trim().toLowerCase();
}

/** POST baris ke webhook aplikasi. Best-effort — error hanya di-log. */
function REC_v2_push_(payload) {
  var secret = REC_v2_secret_();
  if (!WEBHOOK_URL || !secret) {
    console.warn('Push dilewati: WEBHOOK_URL / secret belum diisi');
    return;
  }
  payload.source = 'gas-push';
  payload.marker = REC_MARKER;
  var res = UrlFetchApp.fetch(WEBHOOK_URL, {
    method: 'post',
    contentType: 'application/json',
    headers: { 'X-BPF-Token': secret },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true,
    followRedirects: true,
  });
  console.log('Push ' + payload.modul + ' → ' + res.getResponseCode() + ' ' + res.getContentText().slice(0, 160));
}

function REC_json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
