// Verifikasi UI Sistem Overtime (v2.22) via Chrome nyata (puppeteer-core).
// Cek: form publik /app/overtime-form (dropdown Posisi & Nama, submit sukses
// dengan nomor OTL-*), dashboard GA HR /app/ga-hr (statistik, tab OB/Security
// berisi data migrasi, tombol PDF), dan akses 403 untuk role GA.
// Jalankan: node frontend/scripts/verify_overtime_ui.mjs
import puppeteer from 'puppeteer-core'
import { mkdirSync } from 'fs'

const BASE = process.env.BASE || 'http://localhost:5001'
const CHROME = process.env.CHROME || '/home/it-ef/.local/opt/chrome/chrome-linux64/chrome'
const SHOT_DIR = '/tmp/ui_overtime_shots'
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
  await page.waitForSelector('.login-card', { timeout: 20000 })
  await page.waitForSelector('input[autocomplete="username"]', { timeout: 20000 })
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

// Set nilai input/select Vue (date/time/select) lewat native setter + event.
async function setVueValue(page, selector, index, value) {
  await page.evaluate(([sel, idx, val]) => {
    const el = document.querySelectorAll(sel)[idx]
    if (!el) return
    const proto = el instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype
    const setter = Object.getOwnPropertyDescriptor(proto, 'value').set
    setter.call(el, val)
    el.dispatchEvent(new Event('input', { bubbles: true }))
    el.dispatchEvent(new Event('change', { bubbles: true }))
  }, [selector, index, value])
}

// ================= 1. FORM PUBLIK (/app/overtime-form) =================
const testName = null // dropdown Nama — tidak menambah nama baru
let testKeterangan = 'UI verify ' + Date.now().toString().slice(-6)
{
  const ctx = await browser.createBrowserContext()
  const page = await ctx.newPage()
  page.on('console', (m) => { if (m.type() === 'error') errors.push('FORM ' + m.text().slice(0, 160)) })
  page.on('pageerror', (e) => errors.push('FORM PAGEERROR: ' + String(e).slice(0, 160)))
  await page.goto(BASE + '/app/overtime-form', { waitUntil: 'networkidle2', timeout: 30000 })
  await sleep(2500)

  let formShown = false
  for (let i = 0; i < 15 && !formShown; i++) {
    formShown = await page.evaluate(() => !!document.querySelector('.apply-card form'))
    if (!formShown) await sleep(1000)
  }
  ok('Halaman /app/overtime-form: form tampil', formShown)

  const selects = await page.evaluate(() =>
    [...document.querySelectorAll('.apply-card select')].map((s) => [...s.options].map((o) => o.textContent.trim())))
  ok('Dropdown Posisi berisi OB & Security',
    selects[0]?.includes('OB (Office Boy)') && selects[0]?.includes('Security'), JSON.stringify(selects[0]))
  ok('Dropdown Nama berisi data yang ada (Muhajir, Edwin P…)',
    selects[1]?.includes('Muhajir') && selects[1]?.includes('Edwin P'), (selects[1] || []).slice(0, 5).join(', '))

  // Isi form: pilih posisi OB + nama pertama dari dropdown data
  await setVueValue(page, '.apply-card select', 0, 'OB')
  const firstNama = await page.evaluate(() => {
    const s = document.querySelectorAll('.apply-card select')[1]
    return s && s.options.length > 1 ? s.options[1].value : ''
  })
  await setVueValue(page, '.apply-card select', 1, firstNama)
  await setVueValue(page, '.apply-card input[type="date"]', 0, '2026-08-14')
  await setVueValue(page, '.apply-card input[type="time"]', 0, '18:00')
  await setVueValue(page, '.apply-card input[type="time"]', 1, '21:00')
  await page.type('.apply-card input[list]', testKeterangan)

  await page.click('.apply-card form button.btn-primary')
  let success = false
  for (let i = 0; i < 20 && !success; i++) {
    await sleep(500)
    success = await page.evaluate(() => !!document.querySelector('.apply-success'))
  }
  const info = await page.evaluate(() => document.querySelector('.apply-success')?.textContent || '')
  ok('Submit form -> halaman sukses + nomor OTL-*', success && info.includes('OTL-'),
    (info.match(/OTL-\S+/) || ['?'])[0])
  await page.screenshot({ path: SHOT_DIR + '/01-form-success.png' })
  await ctx.close()
}

// ================= 2. DASHBOARD GA HR (/app/ga-hr) — admin =================
{
  const ctx = await browser.createBrowserContext()
  const page = await ctx.newPage()
  page.on('console', (m) => { if (m.type() === 'error') errors.push('GAHR ' + m.text().slice(0, 160)) })
  page.on('pageerror', (e) => errors.push('GAHR PAGEERROR: ' + String(e).slice(0, 160)))
  await login(page, 'admin', '123456')
  await page.goto(BASE + '/app/ga-hr', { waitUntil: 'networkidle2', timeout: 30000 })
  await sleep(3000)

  let statCards = 0
  for (let i = 0; i < 15 && statCards === 0; i++) {
    await sleep(1000)
    statCards = await page.evaluate(() => document.querySelectorAll('.stat-card').length)
  }
  ok('Dashboard GA HR: kartu statistik tampil (' + statCards + ')', statCards >= 2)

  // Tab OB & Security — tabel berisi data migrasi (546 baris)
  await page.evaluate(() => [...document.querySelectorAll('.tab')].find((t) => t.textContent.includes('OB'))?.click())
  await sleep(2500)
  let obRows = 0
  for (let i = 0; i < 15 && obRows === 0; i++) {
    await sleep(1000)
    obRows = await page.evaluate(() => document.querySelectorAll('.tbl tbody tr').length)
  }
  const obText = await page.evaluate(() => document.querySelector('.tbl tbody')?.textContent || '')
  ok('Tab OB/Security: tabel berisi data migrasi', obRows > 0 && obText.includes('Muhajir'), obRows + ' baris')
  const hasPdfOb = await page.evaluate(() =>
    [...document.querySelectorAll('.filters .btn')].some((b) => b.textContent.includes('PDF')))
  ok('Tombol 📄 PDF ada di tab OB/Security', hasPdfOb)

  // Tab Driver — tombol Refresh + Sumber Data
  await page.evaluate(() => [...document.querySelectorAll('.tab')].find((t) => t.textContent.includes('Driver'))?.click())
  await sleep(1500)
  const driverBtns = await page.evaluate(() => [...document.querySelectorAll('.filters .btn')].map((b) => b.textContent))
  ok('Tab Driver: tombol 🔄 Refresh & ⚙️ Sumber Data ada',
    driverBtns.some((t) => t.includes('Refresh')) && driverBtns.some((t) => t.includes('Sumber Data')), driverBtns.join(' | '))
  await page.screenshot({ path: SHOT_DIR + '/02-gahr.png' })
  await ctx.close()
}

// ================= 3. ROLE GA -> /app/ga-hr TERTOLAK (403) =================
{
  const ctx = await browser.createBrowserContext()
  const page = await ctx.newPage()
  page.on('console', (m) => { if (m.type() === 'error') errors.push('GA ' + m.text().slice(0, 160)) })
  page.on('pageerror', (e) => errors.push('GA PAGEERROR: ' + String(e).slice(0, 160)))
  await login(page, 'ga_sby', '123456')
  await page.goto(BASE + '/app/ga-hr', { waitUntil: 'networkidle2', timeout: 30000 })
  await sleep(2500)
  const url = await page.url()
  const forbidden = await page.evaluate(() => !!document.querySelector('h1')?.textContent.includes('403'))
  ok('Role GA akses /app/ga-hr -> halaman 403', forbidden || url.includes('403'), url)
  await ctx.close()
}

console.log('\n=== ERROR CONSOLE ===')
console.log(errors.length ? errors.join('\n') : '(tidak ada error console)')
await browser.close()
process.exit(errors.length ? 1 : 0)
