'use strict';
/* bpf-workhub — aplikasi Cordova (v2.0.0)
 * - portrait & landscape bebas (tidak dikunci)
 * - kategori user: marketing / back office (dipilih user, admin menentukan target agenda)
 * - tema gelap/terang (warna senada logo BestProfit)
 * - kalender bulan penuh + panel agenda hari terpilih (berdampingan di layar lebar)
 * - realtime via SSE, fallback polling; widget + notifikasi lokal
 */

const $ = (id) => document.getElementById(id);
const CFG = window.BPF_CONFIG;

/* Ikon garis (bukan emoji) agar tampil sama di semua perangkat. */
const ICON_CAL = '<svg viewBox="0 0 24 24" width="30" height="30" fill="none" ' +
  'stroke="currentColor" stroke-width="1.6" stroke-linecap="round" ' +
  'stroke-linejoin="round"><rect x="3" y="5" width="18" height="16" rx="3"/>' +
  '<path d="M8 3v4M16 3v4M3 10h18"/><path d="M8 14h2M14 14h2M8 17h2M14 17h2"/></svg>';

const AUD_KEY = 'bpf_audience';   // 'marketing' | 'backoffice'
const THEME_KEY = 'bpf_theme';    // 'dark' | 'light'

let es = null;              // EventSource
let pollTimer = null;
let liveTimer = null;
let audience = null;        // kategori user aktif
let view = null;            // {year, month}
let selected = null;        // 'YYYY-MM-DD' yang disorot di kalender
let modalDate = null;       // tanggal yang sedang dibuka di popup (null = popup tertutup)
let lastDate = null;        // tanggal server terakhir diketahui (auto-reset saat ganti hari)
let months = {};            // cache titik agenda
let monthAnimating = false; // animasi ganti bulan sedang berjalan
let suppressClickUntil = 0; // abaikan klik tanggal sisa gestur swipe

const pad2 = (n) => String(n).padStart(2, '0');
const ymd = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;

/* ---------------- start ---------------- */

document.addEventListener('deviceready', onDeviceReady, false);

if (!window.cordova) {
  // preview di browser: jalankan langsung
  document.addEventListener('DOMContentLoaded', () => onDeviceReady());
}

async function onDeviceReady() {
  unlockOrientation();
  applyTheme(localStorage.getItem(THEME_KEY) || preferredTheme());
  $('logo').src = `${CFG.API_BASE}/assets/logo.png`;
  $('catLogo').src = `${CFG.API_BASE}/assets/logo.png`;

  // menu ⋯ (kategori, widget, tema, pembaruan)
  $('menuBtn').addEventListener('click', (ev) => { ev.stopPropagation(); toggleMenu(); });
  $('menuCat').addEventListener('click', () => { closeMenu(); showCatScreen(true); });
  $('menuWidget').addEventListener('click', () => { closeMenu(); toggleWidget(); });
  $('menuTheme').addEventListener('click', () => { closeMenu(); toggleTheme(); });
  $('menuUpdate').addEventListener('click', () => {
    closeMenu();
    if (window.bpfUpdater) window.bpfUpdater.check();
  });
  $('todayBtn').addEventListener('click', goToday);
  $('catPinForm').addEventListener('submit', submitCatPin);

  const saved = localStorage.getItem(AUD_KEY);
  if (saved === 'marketing' || saved === 'backoffice') {
    audience = saved;
    renderCatChip();
    start();
  } else {
    showCatScreen(true); // menunggu pilihan user; app started setelahnya
  }

  initSwipe();
  // rotasi layar / perubahan ukuran: track harus tetap di pane tengah
  window.addEventListener('resize', () => centerTrack());
  window.addEventListener('orientationchange', () => setTimeout(centerTrack, 220));

  // viewer gambar (tap untuk memperbesar)
  $('viewerClose').addEventListener('click', closeViewer);
  $('viewer').addEventListener('click', (ev) => { if (ev.target.id === 'viewer') closeViewer(); });

  // back Android / Escape: tutup yang paling atas dulu
  document.addEventListener('backbutton', onBackButton, false);
  document.addEventListener('keydown', (ev) => {
    if (ev.key !== 'Escape') return;
    if (!$('menuSheet').classList.contains('hidden')) { closeMenu(); return; }
    onBackButton();
  });
}

/* ---------------- menu ⋯ ---------------- */

function toggleMenu() {
  const sheet = $('menuSheet');
  const open = sheet.classList.contains('hidden');
  sheet.classList.toggle('hidden', !open);
  $('menuBtn').setAttribute('aria-expanded', String(open));
}

function closeMenu() {
  const sheet = $('menuSheet');
  if (!sheet || sheet.classList.contains('hidden')) return;
  sheet.classList.add('hidden');
  $('menuBtn').setAttribute('aria-expanded', 'false');
}

function toggleTheme() {
  const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
  applyTheme(next);
}

function preferredTheme() {
  try {
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) return 'light';
  } catch (e) { /* abaikan */ }
  return 'dark';
}

/* Kembali ke hari ini (tanggal server bila sudah diketahui). */
function goToday() {
  const today = lastDate || ymd(new Date());
  const d = new Date(`${today}T00:00`);
  view = { year: d.getFullYear(), month: d.getMonth() };
  selected = today;
  modalDate = today;
  buildCalendar();
  refreshSelected(today);
}

/* ---------------- popup agenda hari ---------------- */

function openDay(date) {
  const d = new Date(`${date}T00:00`);
  if (d.getFullYear() !== view.year || d.getMonth() !== view.month) {
    view = { year: d.getFullYear(), month: d.getMonth() };
  }
  modalDate = date;
  selected = date;
  $('detailDate').textContent = formatDate(date);
  renderMeta(date);
  $('agenda').innerHTML = '<div class="agenda-item empty"><span class="muted">Memuat agenda…</span></div>';
  const pill = $('agendaCount');
  if (pill) { pill.textContent = '…'; pill.classList.add('zero'); }
  buildCalendar();
  const pane = $('agendaPane');
  if (pane) {
    pane.classList.remove('pulse');
    void pane.offsetWidth;
    pane.classList.add('pulse');
  }
  refreshSelected(date);
}


/* back Android / Escape: tutup yang paling atas dulu */
function onBackButton() {
  if (!$('menuSheet').classList.contains('hidden')) { closeMenu(); return; }
  if (!$('viewer').classList.contains('hidden')) { closeViewer(); return; }
  if (window.navigator && navigator.app && navigator.app.exitApp) navigator.app.exitApp();
}

function closeViewer() {
  $('viewerImg').src = '';
  $('viewer').classList.add('hidden');
}

/* Orientasi bebas: portrait dan landscape sama-sama didukung. */
function unlockOrientation() {
  try {
    if (window.screen && screen.orientation && screen.orientation.unlock) {
      screen.orientation.unlock();
    }
  } catch (e) { /* config.xml sudah 'default' */ }
}

/* ---------------- kategori user (via PIN: BO=123456, Marketing=444444) ---------------- */

function showCatScreen(show) {
  const screen = $('catScreen');
  screen.classList.toggle('hidden', !show);
  if (!show) return;
  // PIN lama jangan tertinggal: input punya maxlength=6 sehingga ketikan
  // baru diabaikan bila field masih berisi PIN sebelumnya.
  const pin = $('catPin');
  if (pin) {
    pin.value = '';
    setTimeout(() => { try { pin.focus(); } catch (e) { } }, 30);
  }
  const hint = $('catHint');
  if (hint) hint.textContent = '';
}

function submitCatPin(ev) {
  if (ev) ev.preventDefault();
  const pin = ($('catPin') || {}).value || '';
  const p = String(pin).trim();
  let aud = null;
  if (p === '123456') aud = 'backoffice';
  else if (p === '444444') aud = 'marketing';
  if (!aud) {
    $('catHint').textContent = 'PIN salah, coba lagi.';
    return;
  }
  localStorage.setItem(AUD_KEY, aud);
  audience = aud;
  renderCatChip();
  const pinField = $('catPin');
  if (pinField) pinField.value = '';
  showCatScreen(false);
  if (!liveTimer) start().catch(() => {});
  else start(true).catch(() => {});
}

async function chooseAudience(aud) { // dipakai jika fallback manual (mis. tidak pakai PIN)
  if (aud !== 'marketing' && aud !== 'backoffice') {
    $('catHint').textContent = 'Pilihan tidak dikenal, coba lagi.';
    return;
  }
  localStorage.setItem(AUD_KEY, aud);
  audience = aud;
  renderCatChip();
  showCatScreen(false);
  if (!liveTimer) await start();
  else await start(true); // reset ulang sumber data sesuai kategori
}

function renderCatChip() {
  const chip = $('catChip');
  if (!chip) return;
  const full = chip.querySelector('.cat-full');
  const short = chip.querySelector('.cat-short');
  const label = !audience ? '–' : (audience === 'marketing' ? 'Marketing' : 'Back Office');
  const abbr = !audience ? '–' : (audience === 'marketing' ? 'MKT' : 'BO');
  if (full) full.textContent = label; else chip.textContent = label;
  if (short) short.textContent = abbr;
  chip.className = 'cat-chip ' + (audience === 'marketing' ? 'mkt' : 'bo');
  chip.title = `Kategori aktif: ${label}`;
}

/* ---------------- tema ---------------- */

function applyTheme(t) {
  document.documentElement.setAttribute('data-theme', t);
  try { localStorage.setItem(THEME_KEY, t); } catch {}
  const label = $('menuThemeLabel');
  if (label) label.textContent = t === 'dark' ? 'Mode terang' : 'Mode gelap';
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute('content', t === 'dark' ? '#0b1020' : '#eef1f8');
}

/* ---------------- state & fetch ---------------- */
async function start(restart) {
  const now = new Date();
  view = { year: now.getFullYear(), month: now.getMonth() };
  selected = ymd(now);
  if (!modalDate) modalDate = selected;

  if (!restart) {
    $('prevMonth').addEventListener('click', () => shiftMonth(-1));
    $('nextMonth').addEventListener('click', () => shiftMonth(1));
  } else {
    // kategori berubah: buang cache titik yang lama supaya kalender segar
    months = {};
    openStream(); // stream lama membawa filter kategori sebelumnya
  }

  buildCalendar();
  await refresh();
  if (modalDate) refreshSelected(modalDate); // kategori berubah -> popup ikut diperbarui
  if (!restart) {
    openStream();
    liveTimer = setInterval(() => refresh(), CFG.POLL_MS);
  }
}

function openStream() {
  if (es) { es.close(); es = null; }
  if (!window.EventSource) { setLive('Menyambung…', 'warn'); return; }
  try {
    es = new EventSource(`${CFG.API_BASE}/api/stream?audience=${audience}`);
    es.addEventListener('open', () => setLive('Live', 'on'));
    es.addEventListener('state', (ev) => {
      setLive('Live', 'on');
      if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
      applyState(JSON.parse(ev.data));
    });
    es.addEventListener('error', () => {
      // stream terputus -> tampilkan status jelas + fallback ke polling
      setLive('Menyambung…', 'warn');
      if (!pollTimer) pollTimer = setInterval(() => refresh(), CFG.POLL_MS);
    });
  } catch (e) {
    setLive('Menyambung…', 'warn');
    pollTimer = setInterval(() => refresh(), CFG.POLL_MS);
  }
}

function setLive(text, cls) {
  const el = $('liveBadge');
  if (!el) return;
  el.className = 'live-badge ' + cls;
  el.title = text;
  const t = el.querySelector('.live-text');
  if (t) t.textContent = text; else el.textContent = text;
}

async function refresh() {
  try {
    const r = await fetch(`${CFG.API_BASE}/api/state?audience=${audience}`);
    if (!r.ok) throw new Error('http ' + r.status);
    applyState(await r.json());
    setLive('Live', 'on');
  } catch (e) {
    // tidak terhubung ke server -> tampilkan status offline yang jelas
    setLive('Offline', 'warn');
  }
}

/* ---------------- terapkan state dari server ---------------- */

let lastAgendaSig = null;   // signature item terakhir yang sudah dipantau
let lastAgendaIds = new Set(); // id item yang sudah pernah di-notifikasi

function applyState(state) {
  const serverDate = state.date; // tanggal hari ini versi server (otoritatif)

  // pergantian tanggal di server -> reset tampilan (agenda hilang otomatis)
  if (lastDate && lastDate !== serverDate) {
    selected = serverDate;
    view = { year: +serverDate.slice(0, 4), month: +serverDate.slice(5, 7) - 1 };
    months = {};
    modalDate = serverDate;   // panel agenda ikut pindah ke hari baru
    buildCalendar();
  }
  lastDate = serverDate;

  // deteksi item agenda baru -> kirim notifikasi lokal
  const items = state.items || [];
  const sig = items.map((i) => i.id).join(',');
  if (lastAgendaSig !== null && sig !== lastAgendaSig) {
    const fresh = items.filter((i) => !lastAgendaIds.has(i.id));
    for (const it of fresh) notifyNewAgenda(it);
  }
  lastAgendaSig = sig;
  for (const it of items) lastAgendaIds.add(it.id);

  // kalender: titik agenda bulan berjalan (mengikuti kategori user)
  fetchMonthDots(buildMonthKey(view));

  // widget home screen: tanggal + agenda hari ini
  pushWidgetAgenda(serverDate, items);

  // panel agenda: tanggal terpilih ikut realtime bila itu hari ini
  if (!modalDate) { modalDate = serverDate; selected = serverDate; }
  if (modalDate === serverDate) {
    renderAgenda(serverDate, state.now, state.server_time, items);
  }
}

/* ---------------- widget home screen: agenda hari ini ---------------- */

let lastWidgetSig = null;

function pushWidgetAgenda(date, items) {
  if (!window.cordova) return;
  const lines = (items || [])
    .map((it) => '• ' + String(it.title || '').trim())
    .filter((s) => s.length > 2);
  const text = lines.length ? lines.slice(0, 3).join('\n') : 'Belum ada agenda hari ini';
  const sig = `${date}|${text}`;
  if (sig === lastWidgetSig) return;
  lastWidgetSig = sig;
  bpfExec('widgetAgenda', [date, text]).catch(() => { lastWidgetSig = null; });
}

/* ---------------- notifikasi agenda baru ---------------- */

function notifyNewAgenda(it) {
  const title = (it.title || 'Agenda baru BPF').toString();
  const msg = (it.body || `Ada agenda baru pada ${it.date || ''}`).toString();
  try {
    const p = bpfExec('notify', [title, msg]);
    if (p && p.then) p.then(() => {}, () => {});
  } catch (e) { /* abaikan */ }
}

/* ---------------- bridge native (notifikasi / widget) ---------------- */

function bpfExec(action, args) {
  return new Promise((resolve, reject) => {
    const c = window.cordova;
    if (!c) { setTimeout(() => reject(new Error('cordova belum siap')), 800); return; }
    try {
      c.exec((r) => resolve(r), (e) => reject(e), 'bpfBridge', action, args || []);
    } catch (e) { reject(e); }
  });
}

/* ---------------- widget home screen ---------------- */

function toggleWidget() {
  const on = localStorage.getItem('bpf_widget') !== '1';
  localStorage.setItem('bpf_widget', on ? '1' : '0');
  if (!on) return;
  // minta izin notifikasi (Android 13+) lalu pin widget 1x1 ke home screen
  bpfExec('notify-permission')
    .catch(() => {})
    .then(() => bpfExec('addWidget'))
    .then(() => { console.info('[bpf] widget: permintaan pin terkirim'); })
    .catch((e) => { console.warn('[bpf] widget gagal:', e); });
}

function buildMonthKey(v) { return `${v.year}-${pad2(v.month + 1)}`; }

function fetchMonthDots(key) {
  if (months[key]) return Promise.resolve(months[key]);
  return fetch(`${CFG.API_BASE}/api/month?month=${key}&audience=${audience}`)
    .then((r) => r.json())
    .then((j) => { months[key] = j.dates || []; renderAll(); })
    .catch(() => {});
}

/* ---------------- hari libur & penanggalan Jawa ---------------- */

function liburFor(date) {
  const list = (window.BPF_HARI_LIBUR || {})[String(date).slice(0, 4)] || [];
  return list.find((x) => x.date === date) || null;
}

function jawaFor(date) {
  const J = window.BPF_JAWA;
  return J && J.parse ? J.parse(date) : null;
}

/* Baris kecil di bawah judul popup: tanggal Jawa + keterangan libur. */
function renderMeta(date) {
  const el = $('detailMeta');
  if (!el) return;

  const parts = [];
  const j = jawaFor(date);
  if (j) parts.push(j.label);
  const lib = liburFor(date);
  if (lib) {
    // nama di data kadang sudah diawali "Cuti Bersama" -> jangan diulang
    const label = lib.type === 'cuti' ? 'Cuti bersama' : 'Libur nasional';
    parts.push(`${label}: ${String(lib.name).replace(/^cuti bersama\s+/i, '')}`);
  }

  el.textContent = parts.join(' · ');
  el.className = 'detail-meta' + (lib ? ' libur' : '');
}

/* ---------------- render ---------------- */

/* ---------------- geser bulan: tombol, swipe, dan animasi ---------------- */

const SWIPE_THRESHOLD = 46;    // px geseran sebelum dianggap pindah bulan
const SWIPE_MAX_RATIO = 0.45;  // batas geseran visual (proporsi lebar grid)
const SLIDE_MS = 190;          // durasi transisi track, samakan dengan .cal-track

/* Track memuat 3 pane: bulan sebelumnya | aktif | bulan berikutnya.
   Posisi normal = -W (pane tengah). */
function trackWidth() {
  const vp = $('calViewport');
  return (vp && vp.clientWidth) || 320;
}

/* Posisi track memakai PERSEN, bukan px. 100% = lebar satu pane = lebar
   viewport, jadi tidak bergantung pada clientWidth yang bisa terukur basi saat
   WebView baru berputar ke landscape (bug yang terlihat di perangkat: grid
   bergeser ke kiri dan kolom Minggu terpotong). */
function trackX(css) {
  const track = $('calTrack');
  if (track) track.style.transform = css;
}

/* Kembalikan track ke pane tengah tanpa animasi. */
function centerTrack() {
  const track = $('calTrack');
  if (!track) return;
  track.classList.add('no-anim');
  track.style.transform = '';    // pakai default CSS translateX(-33.3333%)
  void track.offsetWidth;        // paksa reflow agar no-anim benar-benar dipakai
  track.classList.remove('no-anim');
}

function commitMonth(d) {
  const m = new Date(view.year, view.month + d, 1);
  view = { year: m.getFullYear(), month: m.getMonth() };
  buildCalendar();               // render ulang 3 pane + label + centerTrack
  fetchMonthDots(buildMonthKey(view));
}

/* Geser satu bulan dengan animasi track: bulan tetangga ikut terlihat. */
function slideTo(d) {
  if (monthAnimating) return;
  const track = $('calTrack');
  if (!track) { commitMonth(d); return; }

  monthAnimating = true;
  suppressClickUntil = Date.now() + SLIDE_MS + 250; // klik sisa gestur diabaikan
  renderAll();                   // pastikan pane tetangga sudah terisi
  track.classList.remove('dragging');

  // berikutnya: pane ke-3 (-66.6667%), sebelumnya: pane ke-1 (0%)
  trackX(d > 0 ? 'translateX(-66.6667%)' : 'translateX(0%)');

  const done = () => {
    if (!monthAnimating) return; // sudah dijalankan pemicu lainnya
    commitMonth(d);
    monthAnimating = false;
  };
  track.addEventListener('transitionend', done, { once: true });
  setTimeout(done, SLIDE_MS + 90); // jaring-jaring bila transitionend tak datang
}

function shiftMonth(d, opts) {
  const animate = !opts || opts.animate !== false;
  if (!animate) { commitMonth(d); return; }
  slideTo(d);
}

/* Swipe horizontal pada viewport kalender: geser kiri = bulan berikutnya. */
function initSwipe() {
  const vp = $('calViewport');
  const track = $('calTrack');
  if (!vp || !track) return;

  let startX = 0;
  let startY = 0;
  let dx = 0;
  let axis = null;    // null (belum diputuskan) | 'x' | 'y'
  let active = false;

  vp.addEventListener('touchstart', (ev) => {
    if (ev.touches.length !== 1 || monthAnimating) { active = false; return; }
    active = true;
    axis = null;
    dx = 0;
    startX = ev.touches[0].clientX;
    startY = ev.touches[0].clientY;
  }, { passive: true });

  vp.addEventListener('touchmove', (ev) => {
    if (!active) return;
    const x = ev.touches[0].clientX - startX;
    const y = ev.touches[0].clientY - startY;

    if (!axis) {
      if (Math.abs(x) < 12 && Math.abs(y) < 12) return;   // masih tap, belum geser
      axis = Math.abs(x) > Math.abs(y) ? 'x' : 'y';
      if (axis === 'x') track.classList.add('dragging');
    }
    if (axis !== 'x') return;

    ev.preventDefault();
    dx = x;
    const w = trackWidth();
    const limit = w * SWIPE_MAX_RATIO;
    const applied = Math.max(-limit, Math.min(limit, dx * 0.55));
    // geseran px ditambahkan ke posisi tengah yang berbasis persen
    trackX(`translateX(calc(-33.3333% + ${applied}px))`);
  }, { passive: false });

  const finish = () => {
    if (!active) return;
    active = false;
    track.classList.remove('dragging');

    if (axis !== 'x') { centerTrack(); return; }

    if (Math.abs(dx) > SWIPE_THRESHOLD) {
      suppressClickUntil = Date.now() + SLIDE_MS + 250;
      slideTo(dx < 0 ? 1 : -1);    // geser ke kiri -> bulan berikutnya
    } else {
      centerTrack();               // kurang dari ambang: kembali halus
    }
    axis = null;
    dx = 0;
  };

  vp.addEventListener('touchend', finish, { passive: true });
  vp.addEventListener('touchcancel', finish, { passive: true });
}

const MONTH_NAMES = ['Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli',
  'Agustus', 'September', 'Oktober', 'November', 'Desember'];

/* HTML satu bulan. selectedDate null = pane tetangga (tanpa sorotan pilihan). */
function monthHtml(year, month, selectedDate) {
  const dows = ['Sen', 'Sel', 'Rab', 'Kam', 'Jum', 'Sab', 'Min'];
  let html = dows.map((d) => `<div class="cal-dow">${d}</div>`).join('');

  const first = new Date(year, month, 1);
  const startCol = (first.getDay() + 6) % 7; // Senin mulai
  const firstCell = new Date(year, month, 1 - startCol);
  const today = ymd(new Date());
  const dots = months[`${year}-${pad2(month + 1)}`] || [];

  // indeks tanggal -> {date, count} supaya pencarian di 42 sel tetap O(1)
  const byDate = new Map();
  for (const row of dots) byDate.set(row.date, row);

  for (let i = 0; i < 42; i++) {
    const d = new Date(firstCell.getFullYear(), firstCell.getMonth(), firstCell.getDate() + i);
    const s = ymd(d);
    const other = d.getMonth() !== month ? ' other' : '';
    const isToday = s === today ? ' today' : '';
    const isSel = selectedDate && s === selectedDate ? ' sel' : '';
    // tanggal beragenda: latar aksen + penanda jumlah agenda
    const row = byDate.get(s);
    // count tidak ada di server lama -> anggap 1; count 0 berarti tanpa agenda
    const raw = row ? Number(row.count) : 0;
    const count = row ? (Number.isFinite(raw) ? Math.max(0, Math.trunc(raw)) : 1) : 0;
    const badge = count
      ? `<span class="cal-count" aria-label="${count} agenda">${count > 9 ? '9+' : count}</span>`
      : '';
    const has = count ? ' has' : '';
    // hari libur nasional / cuti bersama: garis aksen di tepi atas sel
    // (cuti bersama memakai garis lebih pudar agar bisa dibedakan)
    const lib = liburFor(s);
    const liburCls = lib ? (lib.type === 'cuti' ? ' libur cuti' : ' libur') : '';
    const title = lib ? ` title="${esc(lib.name)}"` : '';
    const aria = `${formatDate(s)}${count ? `, ${count} agenda` : ''}${lib ? `, ${lib.name}` : ''}`;
    html += `<div class="cal-day${other}${isToday}${isSel}${has}${liburCls}" data-date="${s}"` +
      ` role="button" tabindex="0" aria-label="${esc(aria)}"${title}>${d.getDate()}${badge}</div>`;
  }
  return html;
}

function renderMonth(el, year, month, interactive) {
  if (!el) return;
  el.innerHTML = monthHtml(year, month, interactive ? selected : null);
  if (!interactive) return;

  el.querySelectorAll('.cal-day').forEach((cell) => {
    const pick = () => {
      if (Date.now() < suppressClickUntil) return; // sisa gestur swipe, bukan tap
      selected = cell.dataset.date;
      buildCalendar();
      openDay(selected); // panel agenda menampilkan hari terpilih
    };
    cell.addEventListener('click', pick);
    cell.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); pick(); }
    });
  });
}

/* Render pane aktif + tetangga, tanpa mengubah posisi track.
   Tidak memanggil prefetch agar tidak berputar lewat fetchMonthDots(). */
function renderAll() {
  renderMonth($('calendar'), view.year, view.month, true);

  const prev = new Date(view.year, view.month - 1, 1);
  const next = new Date(view.year, view.month + 1, 1);
  renderMonth($('calPrev'), prev.getFullYear(), prev.getMonth(), false);
  renderMonth($('calNext'), next.getFullYear(), next.getMonth(), false);
}

function prefetchNeighbors() {
  const prev = new Date(view.year, view.month - 1, 1);
  const next = new Date(view.year, view.month + 1, 1);
  fetchMonthDots(`${prev.getFullYear()}-${pad2(prev.getMonth() + 1)}`);
  fetchMonthDots(`${next.getFullYear()}-${pad2(next.getMonth() + 1)}`);
}

function buildCalendar() {
  $('monthLabel').textContent = `${MONTH_NAMES[view.month]} ${view.year}`;
  renderAll();
  centerTrack();
  prefetchNeighbors();
}

async function refreshSelected(date) {
  const target = date || modalDate || selected;
  try {
    const r = await fetch(`${CFG.API_BASE}/api/state?date=${target}&audience=${audience}`);
    if (!r.ok) throw 0;
    const j = await r.json();
    if (modalDate !== target) return; // popup sudah ditutup / pindah tanggal
    renderAgenda(j.date, j.now, j.server_time, j.items || []);
  } catch {
    if (modalDate !== target) return;
    renderAgenda(target, null, null, []);
    setLive('Offline', 'warn'); // kegagalan khusus tanggal ini -> tampilkan status
  }
}

function formatDate(date) {
  const d = new Date(`${date}T00:00`);
  return d.toLocaleDateString('id-ID', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
}

function renderAgenda(date, nowStr, serverTime, items) {
  $('detailDate').textContent = formatDate(date);
  renderMeta(date);

  const box = $('agenda');
  box.innerHTML = '';

  const pill = $('agendaCount');
  if (pill) {
    pill.textContent = items.length ? `${items.length} agenda` : 'Kosong';
    pill.classList.toggle('zero', !items.length);
  }

  if (!items.length) {
    box.innerHTML =
      `<div class="agenda-item empty">
         <span class="empty-ico" aria-hidden="true">${ICON_CAL}</span>
         <strong>Tidak ada agenda</strong>
         <span class="muted">Belum ada informasi untuk tanggal ini.</span>
       </div>`;
  } else {
    for (const it of items) {
      const div = document.createElement('div');
      div.className = 'agenda-item';
      div.innerHTML =
        `<strong>${esc(it.title)}</strong>` +
        (it.body ? `<span>${esc(it.body)}</span>` : '') +
        mediaHtml(it);
      box.appendChild(div);
      div.querySelectorAll('.ag-img[data-full]').forEach((el) =>
        el.addEventListener('click', () => openViewer(el.dataset.full)));
      div.querySelectorAll('.ag-act').forEach((el) =>
        el.addEventListener('click', (ev) => { ev.preventDefault(); mediaAction(el); }));
    }
  }

  if (CFG.SHOW_FRESHNESS && serverTime) {
    const t = new Date(serverTime);
    $('updatedAt').textContent =
      `Diperbarui ${pad2(t.getHours())}:${pad2(t.getMinutes())}:${pad2(t.getSeconds())} · ${audience === 'marketing' ? 'Marketing' : 'Back Office'}`;
  }
}

/* media: absolutkan path relatif server (aplikasi berbasis file:///android_asset) */
function mediaAbs(u) {
  const s = String(u || '');
  return /^https?:\/\//i.test(s) ? s : (CFG.API_BASE + (s.startsWith('/') ? '' : '/') + s);
}

function mediaHtml(it) {
  if (!it.media) return '';
  if (it.media.kind === 'image') {
    const u = mediaAbs(it.media.url);
    return `<img class="ag-img" src="${esc(u)}" data-full="${esc(u)}" alt="media agenda">`
      + mediaActions(u, mediaName(it, u, 'jpg'), 'image/jpeg');
  }
  if (it.media.kind === 'video') {
    const u = mediaAbs(it.media.url);
    return `<video class="ag-video" controls playsinline preload="metadata" src="${esc(u)}"></video>`
      + mediaActions(u, mediaName(it, u, 'mp4'), 'video/mp4');
  }
  if (it.media.kind === 'youtube' && it.media.yt_id) {
    const watch = `https://www.youtube.com/watch?v=${it.media.yt_id}`;
    return `<iframe class="ag-frame" src="https://www.youtube-nocookie.com/embed/${esc(it.media.yt_id)}?rel=0" allowfullscreen title="video agenda"></iframe>`
      + mediaActions(watch, `bpf-video-${it.id || 'agenda'}.txt`, 'text/plain', false);
  }
  const u = mediaAbs(it.media.url);
  return `<a class="ag-link" href="${esc(u)}" target="_blank" rel="noopener">Buka tautan media</a>`
    + mediaActions(u, mediaName(it, u, 'bin'), 'application/octet-stream', false);
}

/* tombol unduh / bagikan untuk media agenda */
function mediaActions(url, name, mime, allowDownload) {
  const dl = allowDownload === false ? ''
    : `<button class="ag-act" data-dl="${esc(url)}" data-name="${esc(name)}">⬇ Unduh</button>`;
  return `<div class="ag-actions">${dl}`
    + `<button class="ag-act" data-share="${esc(url)}" data-name="${esc(name)}" data-mime="${esc(mime)}">↗ Bagikan</button>`
    + '</div>';
}

function mediaName(it, url, ext) {
  const base = String(url || '').split('?')[0].split('/').pop() || '';
  if (/\.[A-Za-z0-9]{2,5}$/.test(base)) return base;
  return `bpf-agenda-${it.id || it.date || Date.now()}.${ext}`;
}

function mediaAction(el) {
  const download = el.dataset.dl;
  const url = download || el.dataset.share;
  const name = el.dataset.name || mediaName({}, url, 'bin');
  if (!window.cordova) { window.open(url, '_blank'); return; } // preview browser
  if (download) {
    bpfExec('download', [url, name]).catch(() => { setLive('UNDUH GAGAL', 'warn'); });
  } else {
    bpfExec('share', [url, name, el.dataset.mime || '']).catch(() => { setLive('BAGIKAN GAGAL', 'warn'); });
  }
}

function openViewer(url) {
  $('viewerImg').src = url;
  $('viewer').classList.remove('hidden');
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}
