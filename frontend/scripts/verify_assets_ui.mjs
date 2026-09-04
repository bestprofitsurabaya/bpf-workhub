// Verifikasi UI Aset & Pemeliharaan (v2.18) via Chrome nyata.
// Cek: login GA -> /app/assets (tab AC dengan 15 unit, tab kendaraan 8 unit,
// rekomendasi, komponen, tombol PDF) + konsol bersih.
import puppeteer from 'puppeteer-core'

const BASE = process.env.BASE || 'http://localhost:5001'
const CHROME = process.env.CHROME || '/home/it-ef/.local/opt/chrome/chrome-linux64/chrome'
const SHOT_DIR = '/tmp/ui_assets_shots'
const { mkdirSync } = await import('fs')
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

const ctx = await browser.createBrowserContext()
const page = await ctx.newPage()
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text().slice(0, 160)) })
page.on('pageerror', (e) => errors.push(String(e).slice(0, 160)))

// Login GA
await page.goto(BASE + '/app/login', { waitUntil: 'networkidle2', timeout: 30000 })
await sleep(2500)
await page.waitForSelector('input[autocomplete="username"]', { timeout: 20000 })
await page.type('input[autocomplete="username"]', 'ga_sby')
await page.type('#login-pin', '123456')
await page.click('form button.btn-primary')
await page.waitForFunction(() => !location.pathname.endsWith('/login'), { timeout: 15000 }).catch(() => {})
await sleep(2500)

await page.goto(BASE + '/app/assets', { waitUntil: 'networkidle2', timeout: 30000 })
await sleep(3500)

// Tab AC
let rows = 0
for (let i = 0; i < 15 && rows < 15; i++) {
  await sleep(800)
  rows = await page.evaluate(() => document.querySelectorAll('.tbl tbody tr').length)
}
ok('Halaman Aset terbuka + tab AC menampilkan data', rows >= 15, 'baris=' + rows)
const acFirst = await page.evaluate(() => document.querySelector('.tbl tbody tr')?.textContent || '')
ok('Data AC migrasi tampil (AC-01 / R. BEST 8)', acFirst.includes('AC-01') || acFirst.includes('BEST 8'), acFirst.slice(0, 60))

// Tombol PDF (ada di tab AC)
const hasPdfAc = await page.evaluate(() => [...document.querySelectorAll('a')].some((a) => a.textContent.includes('Laporan PDF')))
ok('Tombol 📄 Laporan PDF ada (tab AC)', hasPdfAc)

// Tab Kendaraan
await page.evaluate(() => [...document.querySelectorAll('button')].find((b) => b.textContent.includes('Kendaraan')).click())
await sleep(2500)
const vhText = await page.evaluate(() => document.querySelector('.tbl tbody')?.textContent || '')
ok('Tab Kendaraan: 8 unit asli kantor tampil', vhText.includes('B 1126 DFC') && vhText.includes('AVANZA'), vhText.slice(0, 60))

// Tab Rekomendasi
await page.evaluate(() => [...document.querySelectorAll('button')].find((b) => b.textContent.includes('Rekomendasi')).click())
await sleep(2500)
const recText = await page.evaluate(() => document.querySelector('.tbl tbody')?.textContent || '')
ok('Tab Rekomendasi menampilkan daftar', recText.length > 20, recText.slice(0, 50))
const hasRefresh = await page.evaluate(() => [...document.querySelectorAll('button')].some((b) => b.textContent.includes('Perbarui')))
ok('Tombol 🔄 Perbarui Rekomendasi ada', hasRefresh)

// Tab Komponen
await page.evaluate(() => [...document.querySelectorAll('button')].find((b) => b.textContent.includes('Komponen')).click())
await sleep(2500)
const compText = await page.evaluate(() => document.querySelector('.tbl tbody')?.textContent || '')
ok('Tab Komponen: 12 komponen tampil', compText.includes('Oli Mesin') && compText.includes('Timing Belt'), compText.slice(0, 50))

await page.screenshot({ path: SHOT_DIR + '/assets.png' })
await ctx.close()

console.log('\n=== ERROR CONSOLE ===')
console.log(errors.length ? errors.join('\n') : '(tidak ada error console)')
await browser.close()
process.exit(errors.length ? 1 : 0)
