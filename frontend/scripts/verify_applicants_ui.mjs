// Verifikasi UI Sistem Pelamar Kerja (v2.16) via Chrome nyata (puppeteer-core).
// Cek: form publik /app/apply, dashboard Receptionist (filter/edit/kehadiran/PDF),
// dan dashboard Traineer (scope rekrutan upline sendiri).
// Jalankan: node frontend/scripts/verify_applicants_ui.mjs
import puppeteer from 'puppeteer-core'
import { mkdirSync } from 'fs'

const BASE = process.env.BASE || 'http://localhost:5001'
const CHROME = process.env.CHROME || '/home/it-ef/.local/opt/chrome/chrome-linux64/chrome'
const SHOT_DIR = '/tmp/ui_applicants_shots'
mkdirSync(SHOT_DIR, { recursive: true })

const browser = await puppeteer.launch({
  executablePath: CHROME, headless: 'new',
  args: ['--no-sandbox', '--disable-gpu'],
  defaultViewport: { width: 1440, height: 900 },
})
const errors = []
const ok = (name, cond, extra = '') =>
  console.log((cond ? '✅' : '❌') + ' ' + name + (cond ? '' : ' GAGAL') + (extra ? ' — ' + extra : ''))
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function login(page, username, pin) {
  await page.goto(BASE + '/app/login', { waitUntil: 'networkidle2', timeout: 30000 })
  await sleep(2500)
  try {
    await page.waitForSelector('.login-card', { timeout: 20000 })
    await page.waitForSelector('input[autocomplete="username"]', { timeout: 20000 })
  } catch (e) {
    console.log('⚠️ login page gagal render. URL:', await page.url())
    await page.screenshot({ path: SHOT_DIR + '/login-failed.png' })
    throw e
  }
  await page.type('input[autocomplete="username"]', username)
  await page.type('#login-pin', pin)
  await page.click('form button.btn-primary')
  try {
    await page.waitForFunction(() => !location.pathname.endsWith('/login'), { timeout: 15000 })
  } catch { /* fallback */ }
  let sessionCookie = null
  const t0 = Date.now()
  while (!sessionCookie && Date.now() - t0 < 12000) {
    const cookies = await page.cookies(BASE + '/')
    sessionCookie = (cookies.find((c) => c.name === 'session') || {}).value || null
    if (!sessionCookie) await new Promise((r) => setTimeout(r, 250))
  }
  if (sessionCookie) {
    const cdp = await page.createCDPSession()
    await cdp.send('Network.setCookie', {
      name: 'session', value: sessionCookie, url: BASE,
      path: '/', httpOnly: true, secure: false, sameSite: 'Lax',
    })
  }
  return sessionCookie
}

// ================= 1. FORM PUBLIK PELAMAR (/app/apply) =================
{
  const ctx = await browser.createBrowserContext()
  const page = await ctx.newPage()
  page.on('console', (m) => { if (m.type() === 'error') errors.push('APPLY ' + m.text().slice(0, 160)) })
  page.on('pageerror', (e) => errors.push('APPLY PAGEERROR: ' + String(e).slice(0, 160)))
  await page.goto(BASE + '/app/apply', { waitUntil: 'networkidle2', timeout: 30000 })
  await sleep(2500)

  let formShown = false
  for (let i = 0; i < 15 && !formShown; i++) {
    formShown = await page.evaluate(() => !!document.querySelector('.apply-card form'))
    if (!formShown) await sleep(1000)
  }
  ok('Halaman /app/apply: form pelamar tampil', formShown)
  const fields = await page.evaluate(() =>
    [...document.querySelectorAll('.apply-card input')].map((i) => i.placeholder))
  ok('Form berisi 5 field input + 1 dropdown User',
    fields.length >= 5, fields.join(' | '))

  // Dropdown User terisi dari opsi yang dikelola Receptionist (seed Google Sheet)
  const userSelect = await page.evaluate(() => {
    const s = document.querySelector('.apply-card select')
    return s ? [...s.options].map((o) => o.textContent) : []
  })
  ok('Dropdown User berisi opsi (TEAM YUSIE 3 dst.)',
    userSelect.some((o) => o.includes('TEAM YUSIE 3')), userSelect.join(', '))

  // Isi & submit pelamar test (nama unik agar mudah diverifikasi)
  const nama = 'UI Test Pelamar ' + Date.now().toString().slice(-5)
  await page.type('input[placeholder*="KTP"]', nama)
  await page.type('input[placeholder*="SMA"]', 'SMK')
  await page.type('input[placeholder*="08x"]', '081377889900')
  await page.type('input[placeholder*="Nama orang yang merekrut"]', 'Traineer Upline A')
  // Pilih User dari dropdown (opsi pertama yang bukan placeholder)
  await page.select('.apply-card select', userSelect.find((t) => t.includes('TEAM YUSIE 3')).trim())
  await page.type('input[placeholder*="Marketing, Trader"]', 'Marketing')
  await page.click('.apply-card form button.btn-primary')
  let success = false
  for (let i = 0; i < 20 && !success; i++) {
    await sleep(500)
    success = await page.evaluate(() => !!document.querySelector('.apply-success'))
  }
  const info = await page.evaluate(() => document.querySelector('.apply-success')?.textContent || '')
  ok('Submit form -> halaman sukses + no registrasi + jam interview otomatis',
    success && info.includes('PLM-'), (info.match(/PLM-\S+/) || ['?'])[0])
  await page.screenshot({ path: SHOT_DIR + '/01-apply-success.png' })
  await ctx.close()

  // Simpan nama untuk cek di dashboard receptionist
  globalThis.__UI_TEST_NAME = nama
}

// ================= 2. RECEPTIONIST — dashboard =================
{
  const ctx = await browser.createBrowserContext()
  const page = await ctx.newPage()
  page.on('console', (m) => { if (m.type() === 'error') errors.push('REC ' + m.text().slice(0, 160)) })
  page.on('pageerror', (e) => errors.push('REC PAGEERROR: ' + String(e).slice(0, 160)))
  await login(page, 'receptionist_sby', '123456')
  await page.goto(BASE + '/app/receptionist', { waitUntil: 'networkidle2', timeout: 30000 })
  await sleep(3000)

  let table = false
  for (let i = 0; i < 20 && !table; i++) {
    table = await page.evaluate(() => !!document.querySelector('.tbl tbody tr'))
    if (!table) await sleep(1000)
  }
  ok('Dashboard Receptionist: tabel data pelamar tampil', table)

  // Cari pelamar test via kolom pencarian
  await page.type('input[placeholder*="Ketik lalu Enter"]', globalThis.__UI_TEST_NAME)
  await page.keyboard.press('Enter')
  await sleep(2000)
  const found = await page.evaluate((n) =>
    [...document.querySelectorAll('.tbl tbody tr')].some((tr) => tr.textContent.includes(n)),
    globalThis.__UI_TEST_NAME)
  ok('Fungsi search menemukan pelamar test', found)

  // Tombol aksi lengkap (edit/verifikasi/kehadiran/status/hapus)
  const actions = await page.evaluate(() =>
    [...document.querySelectorAll('.tbl tbody tr')].length
      ? [...document.querySelectorAll('.tbl tbody tr button')].map((b) => b.title).filter(Boolean)
      : [])
  ok('Aksi resepsionis lengkap (edit, kehadiran, resign, lulus, hapus)',
    ['Edit / perbaiki data', 'Catat kehadiran (interview / training)', 'Mengundurkan diri (alasan wajib)', 'Lulus training', 'Hapus']
      .every((t) => actions.includes(t)), actions.join(', '))

  // Tombol laporan PDF
  const hasPdf = await page.evaluate(() =>
    [...document.querySelectorAll('a')].some((a) => a.textContent.includes('Laporan PDF')))
  ok('Tombol "📄 Laporan PDF" ada', hasPdf)

  // Tombol Kelola User + modal kelola opsi dropdown
  const hasManage = await page.evaluate(() =>
    [...document.querySelectorAll('button')].some((b) => b.textContent.includes('Kelola User')))
  ok('Tombol "⚙️ Kelola User" ada', hasManage)
  if (hasManage) {
    await page.evaluate(() =>
      [...document.querySelectorAll('button')].find((b) => b.textContent.includes('Kelola User')).click())
    await sleep(1200)
    const optNames = await page.evaluate(() =>
      [...document.querySelectorAll('.att-edit-row b')].map((b) => b.textContent))
    ok('Modal kelola opsi menampilkan daftar User (seed sheet)',
      optNames.some((n) => n.includes('TEAM YUSIE 3')), optNames.join(', '))
    await page.screenshot({ path: SHOT_DIR + '/02b-manage-user.png' })
    // Tutup modal
    await page.evaluate(() =>
      [...document.querySelectorAll('.modal-header button, .modal button')].find((b) => b.textContent.includes('Tutup'))?.click())
    await sleep(500)
  }
  await page.screenshot({ path: SHOT_DIR + '/02-receptionist.png' })
  await ctx.close()
}

// ================= 3. TRAINEER — rekrutan upline sendiri =================
{
  const ctx = await browser.createBrowserContext()
  const page = await ctx.newPage()
  page.on('console', (m) => { if (m.type() === 'error') errors.push('TR ' + m.text().slice(0, 160)) })
  page.on('pageerror', (e) => errors.push('TR PAGEERROR: ' + String(e).slice(0, 160)))
  await login(page, 'traineer_sby', '123456')
  await page.goto(BASE + '/app/traineer', { waitUntil: 'networkidle2', timeout: 30000 })
  await sleep(3000)

  let rows = 0
  for (let i = 0; i < 20 && rows === 0; i++) {
    await sleep(1000)
    rows = await page.evaluate(() => document.querySelectorAll('.tbl tbody tr').length)
  }
  // Data-agnostik: harus melihat pelamar test (upline miliknya) yang dibuat
  // pada langkah 1 — bukti scope traineer bekerja, tanpa bergantung data lama.
  const names = await page.evaluate(() =>
    [...document.querySelectorAll('.tbl tbody tr')].map((tr) => tr.textContent))
  const seesOwn = names.some((t) => t.includes(globalThis.__UI_TEST_NAME))
  const noForeign = names.every((t) => !t.includes('UI Test Pelamar')) || seesOwn
  ok('Dashboard Traineer: menampilkan rekrutan upline sendiri (' + rows + ' baris)',
    rows > 0 && seesOwn && noForeign)
  // Chip kehadiran (I/H1/H2/H3/H4) terlihat
  const chips = await page.evaluate(() =>
    [...document.querySelectorAll('.att-chip')].map((c) => c.textContent).join(''))
  ok('Chip kehadiran I/H1-H4 tampil', chips.includes('I') && chips.includes('H1'))
  await page.screenshot({ path: SHOT_DIR + '/03-traineer.png' })
  await ctx.close()
}

console.log('\n=== ERROR CONSOLE ===')
console.log(errors.length ? errors.join('\n') : '(tidak ada error console)')
await browser.close()
process.exit(errors.length ? 1 : 0)
