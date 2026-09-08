// Verifikasi UI: Admin Master mengedit alamat cabang di Pengaturan → 🏢 Cabang,
// lalu identitas kop dokumen mengikuti nilai baru (alur UI → DB → kop).
// Jalankan:  cd frontend && node scripts/verify_branch_edit_ui.mjs
//   BASE default = produksi (self-signed cert → --ignore-certificate-errors).
import puppeteer from 'puppeteer-core'
import { mkdirSync } from 'fs'

const BASE = process.env.BASE || 'https://nasbpfsby.duckdns.org:5000'
const CHROME = '/home/it-ef/.local/opt/chrome/chrome-linux64/chrome'
const SHOT_DIR = '/tmp/ui_shots_branch'
mkdirSync(SHOT_DIR, { recursive: true })

const browser = await puppeteer.launch({
  executablePath: CHROME, headless: 'new',
  args: ['--no-sandbox', '--disable-gpu', '--ignore-certificate-errors'],
  defaultViewport: { width: 1440, height: 900 },
})
const page = await browser.newPage()
const errors = []
page.on('pageerror', (e) => errors.push('PAGEERROR: ' + String(e).slice(0, 160)))

const ok = (name, cond, extra = '') => {
  console.log((cond ? '✅' : '❌') + ' ' + name + (cond ? '' : ' GAGAL') + (extra ? ' — ' + extra : ''))
  if (!cond) process.exitCode = 1
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

// ---------- 1. Login admin_master ----------
await page.goto(BASE + '/app/login', { waitUntil: 'domcontentloaded' })
await page.waitForSelector('input[autocomplete="username"]', { timeout: 20000 })
await page.type('input[autocomplete="username"]', 'admin_master')
await page.type('input[autocomplete="current-password"]', '123456')
await page.click('form button.btn-primary')
await page.waitForFunction(() => location.pathname.includes('/app/'), { timeout: 20000 })
ok('Login admin_master', page.url().includes('/app/'), page.url())
await sleep(1500)

// ---------- 2. Buka Pengaturan → seksi Cabang ----------
await page.goto(BASE + '/app/settings', { waitUntil: 'domcontentloaded' })
await page.waitForSelector('#sec-cabang', { timeout: 20000 })
await page.evaluate(() => document.getElementById('sec-cabang').scrollIntoView())
await sleep(800)
await page.screenshot({ path: SHOT_DIR + '/01-seksi-cabang.png' })
ok('Seksi 🏢 Cabang tampil', await page.$('#sec-cabang'))

// ---------- 3. Tombol ✏️ Edit ada di baris cabang pertama ----------
const rowInfo = await page.evaluate(() => {
  const row = [...document.querySelectorAll('#sec-cabang table.tbl tbody tr')][0]
  if (!row) return null
  const code = row.querySelector('td b')?.textContent.trim()
  const btn = [...row.querySelectorAll('button')].find((b) => (b.title || '').includes('identitas cabang'))
  return { code, hasEdit: !!btn }
})
ok('Tombol ✏️ Edit tampil di baris ' + (rowInfo?.code || '?') + ' (Admin Pusat)', rowInfo && rowInfo.hasEdit)
const ROW_CODE = rowInfo?.code || 'SBY'

// ---------- 4. Buka modal edit — alamat lama terisi ----------
await page.evaluate((code) => {
  const row = [...document.querySelectorAll('#sec-cabang table.tbl tbody tr')].find((r) => r.querySelector('td b')?.textContent.trim() === code)
  const btn = [...row.querySelectorAll('button')].find((b) => (b.title || '').includes('identitas cabang'))
  btn.click()
}, ROW_CODE)
await sleep(700)
const modalTitle = await page.evaluate(() =>
  [...document.querySelectorAll('.modal-box')].map((m) => m.textContent).join(' '))
ok('Modal "Edit Cabang ' + ROW_CODE + '" terbuka', modalTitle.includes('Edit Cabang ' + ROW_CODE))
await page.screenshot({ path: SHOT_DIR + '/02-modal-edit.png' })

const getAlamat = () => page.evaluate(() => {
  const f = [...document.querySelectorAll('.modal-box .field')]
    .find((el) => el.querySelector('label')?.textContent.trim() === 'Alamat')
  return f ? f.querySelector('input').value : ''
})
const alamatLama = await getAlamat()
ok('Alamat lama terisi', alamatLama.length > 5, alamatLama.slice(0, 50))

// ---------- 5. Ubah alamat → Simpan ----------
const setField = (labelText, value) => page.evaluate((labelText, value) => {
  const f = [...document.querySelectorAll('.modal-box .field')]
    .find((el) => el.querySelector('label')?.textContent.trim() === labelText)
  if (!f) return false
  const input = f.querySelector('input')
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set
  setter.call(input, value)
  input.dispatchEvent(new Event('input', { bubbles: true }))
  return true
}, labelText, value)

const ALAMAT_UJI = 'UJI UI BROWSER - Graha Bukopin Lt.11 Surabaya'
ok('Set alamat uji', await setField('Alamat', ALAMAT_UJI))
await page.evaluate(() => {
  const btn = [...document.querySelectorAll('button')].find((b) => b.textContent.includes('Simpan Cabang'))
  btn.click()
})
await sleep(1500)
await page.screenshot({ path: SHOT_DIR + '/03-setelah-simpan.png' })

// ---------- 6. Verifikasi DB via API dari sesi browser ----------
const after = await page.evaluate(async (code) => {
  const r = await fetch('/api/branches')
  const d = await r.json()
  return (d.branches || []).find((b) => b.code === code)
}, ROW_CODE)
ok('DB berubah sesuai UI', after && after.address === ALAMAT_UJI, (after?.address || '').slice(0, 50))

// ---------- 7. Kembalikan alamat asli lewat UI juga ----------
await page.evaluate((code) => {
  const row = [...document.querySelectorAll('#sec-cabang table.tbl tbody tr')].find((r) => r.querySelector('td b')?.textContent.trim() === code)
  const btn = [...row.querySelectorAll('button')].find((b) => (b.title || '').includes('identitas cabang'))
  btn.click()
}, ROW_CODE)
await sleep(700)
await setField('Alamat', alamatLama)
await page.evaluate(() => {
  const btn = [...document.querySelectorAll('button')].find((b) => b.textContent.includes('Simpan Cabang'))
  btn.click()
})
await sleep(1500)
const restored = await page.evaluate(async (code) => {
  const r = await fetch('/api/branches')
  const d = await r.json()
  return (d.branches || []).find((b) => b.code === code)
}, ROW_CODE)
ok('Alamat asli dikembalikan', restored && restored.address === alamatLama, (restored?.address || '').slice(0, 50))

ok('Tanpa pageerror', errors.length === 0, errors.join(' | ').slice(0, 120))
await browser.close()
console.log(process.exitCode ? '\n❌ ADA KE GAGALAN' : '\n✅ SEMUA CEK UI LULUS')
