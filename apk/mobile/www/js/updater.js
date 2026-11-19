'use strict';
/* updater APK BPF Agenda (v2.125.0)
 * - cek manifest rilis WorkHub (`/api/app/latest`) saat aplikasi dibuka;
 * - bandingkan versionCode manifest dengan versi terpasang (plugin bpfBridge);
 * - unduh + verifikasi SHA-256 + buka installer sistem lewat plugin native;
 * - "Nanti" mengingat versi yang ditolak (kecuali rilis bertanda wajib).
 * Tanpa plugin/perangkat (preview browser) semua langkah dilewati diam-diam.
 */
(function () {
  const CFG = window.BPF_CONFIG || {};
  const SKIP_KEY = 'bpf_update_skip';   // versionCode yang di-"Nanti"
  const CHECK_MS = 6 * 60 * 60 * 1000;  // cek ulang tiap 6 jam
  const RETRY_MS = 10 * 60 * 1000;      // setelah gagal jaringan, coba lagi 10 menit
  const LAST_KEY = 'bpf_update_checked_at';

  let latest = null;     // manifest rilis aktif
  let installed = null;  // { versionName, versionCode }
  let busy = false;

  const $ = (id) => document.getElementById(id);

  function cordovaReady() {
    return !!(window.cordova && window.bpfBridge);
  }

  function call(action, args) {
    return new Promise((resolve, reject) => {
      if (!window.cordova) { reject(new Error('cordova belum siap')); return; }
      try {
        window.cordova.exec(resolve, reject, 'bpfBridge', action, args || []);
      } catch (e) { reject(e); }
    });
  }

  function show(text, opts) {
    const bar = $('updBar');
    if (!bar) return;
    const msg = $('updText');
    const act = $('updInstall');
    const skip = $('updSkip');
    const title = $('updTitle');
    const notes = $('updNotes');
    if (title) title.textContent = opts && opts.title ? opts.title : 'Pembaruan tersedia';
    if (msg) msg.textContent = text || '';
    if (notes) {
      const body = opts && opts.notes ? String(opts.notes).trim() : '';
      notes.textContent = body;
      notes.classList.toggle('hidden', !body);
    }
    if (act) {
      act.textContent = (opts && opts.action) || 'Perbarui';
      act.disabled = !!(opts && opts.disabled);
      act.classList.toggle('hidden', !(opts && opts.showAction));
    }
    if (skip) skip.classList.toggle('hidden', !(opts && opts.showSkip));
    bar.classList.remove('hidden');
  }

  function hide() {
    const bar = $('updBar');
    if (bar) bar.classList.add('hidden');
  }

  function fmtVersion(name, code) {
    const n = String(name || '').trim();
    return n ? `v${n}` : `build ${code}`;
  }

  async function check(force) {
    if (!cordovaReady() || busy) return 'idle';
    const now = Date.now();
    const last = Number(localStorage.getItem(LAST_KEY) || 0);
    if (!force && now - last < CHECK_MS) return 'throttled';
    localStorage.setItem(LAST_KEY, String(now));

    try {
      const r = await fetch(`${CFG.API_BASE}/api/app/latest`, { cache: 'no-store' });
      if (!r.ok) return 'none'; // belum ada rilis / server lama: diam saja
      latest = await r.json();
    } catch (e) {
      // Jaringan gagal: coba lagi lebih cepat (10 menit), jangan tunggu 6 jam.
      localStorage.setItem(LAST_KEY, String(now - CHECK_MS + RETRY_MS));
      return 'error';
    }

    try {
      installed = await call('appInfo', []);
    } catch (e) {
      installed = null;
    }
    if (!installed || !latest || !latest.ok) return 'none';

    const baru = Number(latest.version_code) > Number(installed.versionCode || 0);
    if (!baru) return 'none';

    const skipped = Number(localStorage.getItem(SKIP_KEY) || 0);
    if (!latest.mandatory && skipped === Number(latest.version_code)) return 'skipped';

    offer();
    return 'update';
  }

  function offer() {
    const name = fmtVersion(latest.version_name, latest.version_code);
    // Catatan rilis tampil di kotak `updNotes`; jangan diulang di teks utama.
    show(`Versi ${name} sudah tersedia (terpasang ${fmtVersion(installed.versionName, installed.versionCode)}).`, {
      title: latest.mandatory ? 'Pembaruan wajib' : 'Pembaruan tersedia',
      notes: latest.notes,
      action: 'Unduh & pasang',
      showAction: true,
      showSkip: !latest.mandatory,
    });
  }

  async function install() {
    if (!latest || busy) return;
    busy = true;
    const act = $('updInstall');
    if (act) act.disabled = true;

    const url = /^https?:\/\//i.test(latest.apk_url || '')
      ? latest.apk_url
      : `${CFG.API_BASE}${latest.apk_url || ''}`;

    try {
      show('Mengunduh… 0%', {
        title: latest.mandatory ? 'Pembaruan wajib' : 'Pembaruan tersedia',
        notes: latest.notes,
        action: 'Mengunduh…',
        showAction: true,
        showSkip: !latest.mandatory,
        disabled: true,
      });
      await call('installApk', [url, latest.sha256 || '', latest.file || 'bpf-agenda.apk']);
      hide();
    } catch (err) {
      const msg = (err && (err.message || err)) + '';
      if (msg === 'izin') {
        show('Izinkan pemasangan dari BPF Agenda di Pengaturan, lalu tekan Pasang lagi.', {
          title: 'Butuh izin pemasangan',
          notes: latest.notes,
          action: 'Coba pasang lagi',
          showAction: true,
          showSkip: false,
        });
        return;
      }
      show(`Gagal memasang pembaruan: ${msg}`, {
        title: 'Pembaruan gagal',
        notes: latest.notes,
        action: 'Coba lagi',
        showAction: true,
        showSkip: !latest.mandatory,
      });
    } finally {
      busy = false;
      if (act) act.disabled = false;
    }
  }

  function onAction() {
    if (busy) return;
    if (latest && !$('updInstall').disabled) install();
  }

  function skip() {
    if (!latest) { hide(); return; }
    if (latest.mandatory) return; // wajib: tombol Nanti memang disembunyikan
    localStorage.setItem(SKIP_KEY, String(latest.version_code));
    hide();
  }

  function init() {
    const bar = $('updBar');
    if (bar) bar.classList.add('hidden');
    const act = $('updInstall');
    const skipBtn = $('updSkip');
    if (act) act.addEventListener('click', onAction);
    if (skipBtn) skipBtn.addEventListener('click', skip);
    // Tombol cek manual ada di menu (app.js) dan memanggil bpfUpdater.check().
    // `updBtn` dipertahankan untuk kompatibilitas bila masih ada di HTML lama.
    check(false);
    // pembaruan juga dicek saat aplikasi kembali dibuka dari background
    document.addEventListener('resume', () => check(false), false);
    document.addEventListener('online', () => check(false), false);
  }

  window.bpfUpdater = { check: () => check(true), offer };

  if (window.cordova) {
    document.addEventListener('deviceready', init, false);
  } else {
    document.addEventListener('DOMContentLoaded', init, false);
  }
})();
