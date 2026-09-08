// Verifikasi UI v2.37.8: Service Worker tidak lagi menyajikan /api/* dari cache.
// Membuktikan alur PERSIS yang dilaporkan user lewat UI sungguhan:
//   Finance klik ✅ Verifikasi → isi remark → PIN step-up → daftar BERUBAH
//   OTOMATIS (badge pending → Terverifikasi) TANPA refresh manual.
//   + Audit Cache Storage SW: tidak boleh ada entri /api/*.
// Data uji: pengajuan dibuat admin (role create = ob|admin) via API, setelah
// selesai dihapus dari DB (bukan data produksi).
// Jalankan: cd frontend && node scripts/verify_sw_api_fresh.mjs
import puppeteer from 'puppeteer-core'
import { mkdirSync, writeFileSync } from 'fs'

const BASE = process.env.BASE || 'https://nasbpfsby.duckdns.org:5000'
const CHROME = '/home/it-ef/.local/opt/chrome/chrome-linux64/chrome'
const SHOT_DIR = '/tmp/ui_shots_sw'
mkdirSync(SHOT_DIR, { recursive: true })

const browser = await puppeteer.launch({
  executablePath: CHROME, headless: 'new',
  args: ['--no-sandbox', '--disable-gpu', '--ignore-certificate-errors'],
  defaultViewport: { width: 1440, height: 900 },
})
const page = await browser.newPage()
const errors = []
page.on('pageerror', (e) => errors.push('PAGEERROR: ' + String(e).slice(0, 160)))
// alert() native (sukses verifikasi) harus di-accept agar flow lanjut
page.on('dialog', (d) => d.accept().catch(() => {}))

const ok = (name, cond, extra = '') => {
  console.log((cond ? '✅' : '❌') + ' ' + name + (cond ? '' : ' GAGAL') + (extra ? ' — ' + extra : ''))
  if (!cond) process.exitCode = 1
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function login(username) {
  // Login via API di dalam konteks browser → session cookie + CSRF tersimpan.
  await page.goto(BASE + '/app/login', { waitUntil: 'domcontentloaded' }).catch(() => {})
  await sleep(500)
  const res = await page.evaluate(async (username) => {
    const old = localStorage.getItem('bpf_csrf') || sessionStorage.getItem('bpf_csrf') || ''
    try { await fetch('/api/auth/logout', { method: 'POST', headers: { 'X-CSRF-Token': old } }) } catch { /* noop */ }
    localStorage.removeItem('bpf_csrf'); sessionStorage.removeItem('bpf_csrf')
    const r = await fetch('/api/auth/login', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, pin: '123456' }),
    })
    const d = await r.json().catch(() => null)
    if (d?.csrf_token) localStorage.setItem('bpf_csrf', d.csrf_token)
    return { status: r.status, role: d?.user?.role || null, csrf: d?.csrf_token || '' }
  }, username)
  ok(`Login ${username} (API)`, res.status === 200 && !!res.csrf, `HTTP ${res.status} role=${res.role}`)
  return res.csrf
}

// ---------- 1. Login admin → buat pengajuan uji ----------
let csrf = await login('admin_master')

const pngB64 = 'iVBORw0KGgoAAAANSUhEUgAAAAoAAAAKCAYAAACNMs+9AAAAFUlEQVR42mNk+M+ACzDhZUGgA2wEAFH0Q/h1CJeMAAAAAElFTkSuQmCC'
// FormData harus dibuat DI DALAM browser (tidak bisa dikirim dari Node)
const created = await page.evaluate(async ({ pngB64, csrf }) => {
  const bin = Uint8Array.from(atob(pngB64), (c) => c.charCodeAt(0))
  const fd = new FormData()
  fd.append('purchase_date', new Date().toISOString().slice(0, 10))
  fd.append('items', JSON.stringify([{ drink_type: 'Galon', brand: 'UJI-SW-TEST', satuan: 'galon', quantity: 1 }]))
  fd.append('foto_before', new Blob([bin], { type: 'image/png' }), 'before.png')
  fd.append('foto_after', new Blob([bin], { type: 'image/png' }), 'after.png')
  const r = await fetch('/api/water/purchases', { method: 'POST', headers: { 'X-CSRF-Token': csrf }, body: fd })
  return { status: r.status, body: await r.json().catch(() => null) }
}, { pngB64, csrf })
ok('Pengajuan uji dibuat oleh admin (data uji)', created.status === 200 && created.body?.status === 'success',
  `HTTP ${created.status} ${(created.body?.msg || '').slice(0, 60)}`)
const TEST_ID = created.body?.id
const DISPLAY_ID = created.body?.display_id || ''

// ---------- 2. Login finance → alur UI PERSIS seperti user ----------
await login('finance_sby')
await page.goto(BASE + '/app/water', { waitUntil: 'domcontentloaded' })
await page.waitForFunction((did) => document.body.innerText.includes(did), { timeout: 25000 }, DISPLAY_ID)
  .catch(() => {})
const badgeBefore = await page.evaluate((did) => {
  const el = [...document.querySelectorAll('.cash-item')].find((e) => e.textContent.includes(did))
  return el?.querySelector('.badge')?.textContent.trim() || null
}, DISPLAY_ID)
ok('Item uji tampil di list — badge "Menunggu Verifikasi"', badgeBefore === 'Menunggu Verifikasi', badgeBefore || 'tidak ketemu')

// 2b. Klik ✅ Verifikasi pada baris uji (tombol di list, bukan modal)
await page.evaluate((did) => {
  const el = [...document.querySelectorAll('.cash-item')].find((e) => e.textContent.includes(did))
  const btn = [...el.querySelectorAll('button')].find((b) => b.textContent.includes('Verifikasi'))
  btn.click()
}, DISPLAY_ID)
await sleep(900) // modal verifikasi terbuka + detail foto dimuat

// 2c. Isi Remark (textarea pertama di modal) → klik ✅ Verifikasi di modal
await page.evaluate(() => {
  const modal = document.querySelector('.modal-box') || document.querySelector('.modal')
  const ta = modal.querySelector('textarea')
  const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set
  setter.call(ta, 'UJI-SW-FRESH ' + Date.now())
  ta.dispatchEvent(new Event('input', { bubbles: true }))
})
await page.evaluate(() => {
  const modal = document.querySelector('.modal-box') || document.querySelector('.modal')
  const btn = [...modal.querySelectorAll('button')].find((b) => b.textContent.includes('Verifikasi'))
  btn.click()
})
await sleep(800) // StepUpModal muncul (428 → PIN)

// 2d. PIN step-up
await page.waitForSelector('input[placeholder="PIN 6 digit"]', { timeout: 10000 })
await page.type('input[placeholder="PIN 6 digit"]', '123456')
await page.evaluate(() => {
  const btn = [...document.querySelectorAll('button')].find((b) => b.textContent.includes('✔ Verifikasi'))
  btn.click()
})
await sleep(2200) // alert sukses (auto-accept) → load() berjalan

// 2e. INTI LAPORAN USER: badge berubah OTOMATIS tanpa refresh manual
const badgeAfter = await page.evaluate((did) => {
  const el = [...document.querySelectorAll('.cash-item')].find((e) => e.textContent.includes(did))
  return el?.querySelector('.badge')?.textContent.trim() || null
}, DISPLAY_ID)
ok('BADGE BERUBAH OTOMATIS → "Terverifikasi" (tanpa refresh manual)', badgeAfter === 'Terverifikasi', badgeAfter || 'tidak ketemu')
await page.screenshot({ path: SHOT_DIR + '/01-list-setelah-verifikasi.png' })

// 2f. Bukti mekanisme: fetch ulang URL yang SAMA tetap data baru (bukan cache)
const fresh = await page.evaluate(async (id) => {
  const r = await fetch(`/api/water/purchases?q=${encodeURIComponent('UJI-SW-TEST')}`)
  const d = await r.json()
  return (d?.purchases || []).find((p) => p.id === id)?.status || null
}, TEST_ID)
ok('FETCH URL sama tanpa reload → status=verified (bukan cache lama)', fresh === 'verified', `status=${fresh}`)

// ---------- 3. Audit Cache Storage SW ----------
const auditCache = () => page.evaluate(async () => {
  const names = await caches.keys()
  const apiEntries = []
  let total = 0
  for (const n of names) {
    if (!n.startsWith('bpf-spa-')) continue
    const c = await caches.open(n)
    const reqs = await c.keys()
    total += reqs.length
    for (const r of reqs) {
      const u = new URL(r.url)
      if (u.pathname.startsWith('/api/') || u.pathname.includes('/socket.io/')) apiEntries.push(r.url)
    }
  }
  return { total, apiEntries, names }
})
const cacheAudit = await auditCache()
ok('Cache SW berisi shell/asset', cacheAudit.total > 0, `${cacheAudit.total} entri: ${cacheAudit.names.join(', ')}`)
ok('TIDAK ADA entri /api/* di cache SW', cacheAudit.apiEntries.length === 0, cacheAudit.apiEntries.slice(0, 3).join(' | '))

// ---------- 4. Bersih-bersih: hapus pengajuan uji dari DB (via API admin) ----------
await login('admin_master')
// fitur edit/hapus mungkin nonaktif — cek dulu; bila aktif pakai endpoint resmi
const del = await page.evaluate(async ({ id, csrf }) => {
  const st = await fetch('/api/water/edit-enabled').then((r) => r.json()).catch(() => ({ enabled: false }))
  if (st?.enabled) {
    const r = await fetch(`/api/water/purchases/${id}`, {
      method: 'DELETE', headers: { 'X-CSRF-Token': csrf, 'Content-Type': 'application/json' },
      body: JSON.stringify({ pin: '123456' }),
    })
    return { via: 'endpoint', status: r.status, body: await r.json().catch(() => null) }
  }
  return { via: 'skip', status: 0, body: null }
}, { id: TEST_ID, csrf })
ok(del.via === 'skip' || del.status === 200,
  del.via === 'skip' ? 'Fitur edit nonaktif — cleanup via SQL berikutnya' : 'Pengajuan uji dihapus via endpoint',
  `via=${del.via} HTTP ${del.status}`)

writeFileSync(SHOT_DIR + '/result.json', JSON.stringify({ TEST_ID, DISPLAY_ID, badgeBefore, badgeAfter, fresh, cacheAudit, del }, null, 2))
ok('Tanpa pageerror', errors.length === 0, errors.join(' | ').slice(0, 120))

await browser.close()
console.log(process.exitCode ? '\n❌ ADA YANG GAGAL — artefak di ' + SHOT_DIR : '\n✅ SEMUA CEK LULUS — alur verifikasi UI update otomatis, SW bersih dari API')
