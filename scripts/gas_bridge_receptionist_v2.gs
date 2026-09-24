/**
 * BPF WorkHub — Bridge Google Apps Script untuk sheet RECEPTIONIST — v2 REALTIME
 * (data Pelamar Kerja & In-Out Karyawan, v2.42.0 — DUA SPREADSHEET TERPISAH).
 *
 * STATUS: KONFIGURASI PRODUKSI SUDAH TERTANAM (2026-09-24, code_rev 6) —
 *   tidak ada lagi "GANTI…" yang perlu diisi. Tempel → Save → New version → selesai.
 *   Penanda versi naik ke 2026-09-24/rev 6 agar mudah diverifikasi bahwa versi
 *   baru BENAR-BENAR mengalir ke Web App (kasus 2026-09-24: editor "Konfigurasi OK"
 *   tapi /exec masih kode lama karena deployment menjalankan snapshot versi lama).
 *
 * APA YANG BARU DI v2 (beda dari v1)?
 *   v1: hanya "ditarik" server (pull) saat sync berkala / login / tombol Refresh.
 *   v2: sheet MENDORONG setiap edit langsung ke aplikasi (push) lewat trigger
 *       onEdit → webhook POST /api/receptionist/webhook. Hasilnya data di
 *       aplikasi nyaris realtime (detik setelah edit). Pull (v1 URL
 *       /exec?modul=...) TETAP AKTIF sebagai jaring pengaman bila push gagal
 *       (jaringan/kuota Apps Script) — keduanya dipakai bersama.
 *
 * STRUKTUR DATA:
 *   DUA spreadsheet TERPISAH, satu deploy Apps Script:
 *     - SHEET_ID_APPLICANTS → tab "H2" (file POPH1)  — data Pelamar Kerja
 *     - SHEET_ID_INOUT      → tab "In Out Karyawan BPF SBY" (file Rekap) — In-Out
 *   Trigger onEdit dipasang ke KEDUA spreadsheet oleh REC_v2_pasangTrigger_.
 *
 * CARA KERJA PUSH:
 *   Trigger installable onEdit per spreadsheet → deteksi asal (spreadsheet id +
 *   nama tab) → kirim BARIS YANG DIEDIT saja (header + nilai baris) sebagai JSON
 *   ke WEBHOOK_URL dengan header X-BPF-Token. Server melakukan upsert berdasar
 *   kunci stabil — aman walau baris bergeser.
 *
 * FUNGSI PENTING (jalankan dari editor):
 *   REC_v2_cekKonfigurasi   — cek konfigurasi (harus: "✔ Konfigurasi OK")
 *   REC_v2_pasangTrigger_   — pasang trigger onEdit ke KEDUA spreadsheet (SEKALI)
 *   REC_v2_ujiWebhook       — uji URL+secret ke webhook tanpa mengubah data asli
 *                             (server menjawab 200 + menjalankan sinkron penuh)
 *
 * PENANDA VERSI (anti "script lama menyamar"):
 *   <URL_/exec>?marker=1 → {"marker":"bpf-rec-sheet-2026-09-24-v2","code_rev":6,...}
 *   WAJIB menunjukkan marker 2026-09-24 & code_rev 6. Kalau masih 2026-09-23/5,
 *   berarti "New version" belum dilakukan (lihat langkah deploy no. 3).
 *
 * DEPLOY / UPDATE KODE (wajib urut):
 *   1. Buka project Apps Script "BPF Receptionist Bridge v2" (script.google.com).
 *   2. SELECT ALL di Code.gs → DELETE → tempel SEMUA isi file ini → Ctrl+S.
 *   3. ⚠️ Deploy → Manage deployments → ✏️ (pencil) → Version: **New version**
 *      → Deploy.  TANPA LANGKAH INI URL /exec MASIH KODE LAMA — edit di editor
 *      TIDAK otomatis mengalir ke Web App yang sudah ter-deploy.
 *   4. Jalankan REC_v2_cekKonfigurasi → "✔ Konfigurasi OK".
 *   5. Jalankan REC_v2_pasangTrigger_ SEKALI → log "✔ Trigger onEdit terpasang"
 *      (2 baris: pelamar & in-out). Aman dijalankan ulang (anti-duplikat).
 *   6. Verifikasi: buka <URL_/exec>?marker=1 → marker 2026-09-24, code_rev 6,
 *      config_ok true. Lalu REC_v2_ujiWebhook → log "Push inout → 200 …".
 *   7. Uji asli: edit satu sel di tab In-Out → halaman In-Out Karyawan di
 *      aplikasi berubah dalam beberapa detik (tanpa klik Refresh).
 */

// ====== KONFIGURASI (PRODUKSI — tertanam 2026-09-24) ======
// ID spreadsheet PELAMAR KERJA — bagian /spreadsheets/d/<ID>/edit dari URL.
var SHEET_ID_APPLICANTS = '1VIavwXGX1e9R6dbfkmLltEUo0QgpgDEalUPxD2SF8a0';
// ID spreadsheet IN-OUT KARYAWAN (file terpisah).
var SHEET_ID_INOUT = '1oBmm62eY06QDzErmt1jWw0VX4usScd0hOKqX0I0o2gM';
// Nama tab sumber data ASLI di masing-masing spreadsheet (terverifikasi 2026-09-24).
var TAB_APPLICANTS = 'H2';                   // tab data pelamar (file POPH1)
var TAB_INOUT = 'In Out Karyawan BPF SBY';   // tab data in-out (file Rekap In Out Karyawan)
// Webhook aplikasi (push realtime). TLS Let's Encrypt — valid untuk UrlFetchApp.
var WEBHOOK_URL = 'https://nasbpfsby.duckdns.org:5000/api/receptionist/webhook';

// ====== PENANDA VERSI ======
var REC_MARKER = 'bpf-rec-sheet-2026-09-24-v2';
var REC_CODE_REV = 6; // 6 = konfigurasi produksi tertanam + penanda redeploy 24 Sep

// Secret webhook — sumber: BPF WorkHub → Pengaturan → ⚡ Realtime Sheet.
// Tertanam di sini agar deploy tinggal tempel (kebijakan tim mengizinkan).
// ⚠️ Bila dicurigai bocor: ROTASI secret di Pengaturan → 🔄 Rotasi, lalu ganti
// nilai di bawah + ulangi langkah deploy (New version).
var SECRET_INLINE = 'Z18rAhmBe49rO4SsxtsbMWhToKJW1W3dvUbtIX_fIFY';

function REC_v2_secret_() {
  if (SECRET_INLINE) return SECRET_INLINE;
  // Alternatif lebih aman (bila suatu saat SECRET_INLINE dikosongkan):
  // jalankan sekali di editor: REC_v2_setSecret('isi-secret')
  return PropertiesService.getScriptProperties().getProperty('REC_WEBHOOK_SECRET') || '';
}

/** Jalankan SEKALI di editor untuk menyimpan secret ke Project Properties. */
function REC_v2_setSecret(val) {
  PropertiesService.getScriptProperties().setProperty('REC_WEBHOOK_SECRET', String(val || ''));
  console.log('Secret tersimpan di Project Properties (panjang: ' + String(val || '').length + ')');
}

/** Validasi konfigurasi dasar. Return daftar masalah (kosong = OK). */
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
    masalah.push("Secret belum ada — isi SECRET_INLINE di kode ATAU jalankan REC_v2_setSecret('isi-secret')");
  }
  return masalah;
}

/** Jalankan di editor kapan saja untuk cek konfigurasi: REC_v2_cekKonfigurasi */
function REC_v2_cekKonfigurasi() {
  var masalah = REC_v2_validasiKonfig_();
  if (!masalah.length) {
    console.log('✔ Konfigurasi OK — marker ' + REC_MARKER + ' rev ' + REC_CODE_REV +
                ' — siap deploy (INGAT: New version!) & pasang trigger');
    return;
  }
  console.error('❌ Konfigurasi belum valid:\n- ' + masalah.join('\n- '));
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

/** Sheet aktif utk modul: tab konfigurasi bila ada, else tab PERTAMA file. */
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
  // Validasi dulu: bila kedua SHEET_ID sama, push onEdit salah arah modul —
  // lebih baik gagal jelas di sini.
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

/** Installable trigger handler (utk standalone script — ini yang dipakai). */
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
    // Header berubah — kirim tanda; server menjawab 200 + menjalankan
    // sinkron penuh kedua modul di background (v2.42.0).
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

/**
 * Uji webhook TANPA mengubah data asli: kirim tanda header_changed (rows kosong).
 * Server (v2.42.0) menjawab 200 "sinkron penuh dijadwalkan" — sekaligus memicu
 * resync pull. Jalankan REC_v2_ujiWebhook dari editor; harapkan log:
 *   Push inout → 200 {"msg":"Header sheet berubah — sinkron penuh dijadwalkan",...}
 * 401 = secret salah/beda dengan Pengaturan; 404 = backend belum v2.42.0.
 */
function REC_v2_ujiWebhook() {
  REC_v2_push_({ modul: 'inout', rows: [], header_changed: true, tab: 'UJI-CONNECTIVITY' });
}

function REC_json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
