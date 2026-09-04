// Verifikasi UI fitur Rute Canggih (v2.15) via Chrome nyata (puppeteer-core).
// Cek: input jam kunjungan di Marketing Hub + tombol/modal Atur Rute Otomatis
// di board Chief Driver (termasuk baris penghematan BBM).
// Jalankan: node frontend/scripts/verify_route_ui.mjs
import puppeteer from 'puppeteer-core'
import { mkdirSync } from 'fs'

const BASE = process.env.BASE || 'http://localhost:5001'
const CHROME = process.env.CHROME || '/home/it-ef/.local/opt/chrome/chrome-linux64/chrome'
const SHOT_DIR = '/tmp/ui_route_shots'
mkdirSync(SHOT_DIR, { recursive: true })

const browser = await puppeteer.launch({
  executablePath: CHROME, headless: 'new',
  args: ['--no-sandbox', '--disable-gpu'],
  defaultViewport: { width: 1440, height: 900 },
})
const errors = []
const ok = (name, cond, extra = '') =>
  console.log((cond ? '✅' : '❌') + ' ' + name + (cond ? '' : ' GAGAL') + (extra ? ' — ' + extra : ''))

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
  // Tunggu SPA selesai login & pindah ke halaman rumah role (jangan diinterupsi
  // oleh navigasi berikutnya sebelum alur login selesai — hindari race).
  try {
    await page.waitForFunction(() => !location.pathname.endsWith('/login'), { timeout: 15000 })
  } catch {
    // fallback: beberapa sesi sudah login — biarkan guard router mengarahkan
  }
  // Tunggu cookie sesi dari Set-Cookie
  let sessionCookie = null
  const t0 = Date.now()
  while (!sessionCookie && Date.now() - t0 < 12000) {
    const cookies = await page.cookies(BASE + '/')
    sessionCookie = (cookies.find((c) => c.name === 'session') || {}).value || null
    if (!sessionCookie) await new Promise((r) => setTimeout(r, 250))
  }
  if (sessionCookie) {
    // HTTP lokal: cookie Secure tidak otomatis tersimpan — set manual via CDP
    const cdp = await page.createCDPSession()
    await cdp.send('Network.setCookie', {
      name: 'session', value: sessionCookie, url: BASE,
      path: '/', httpOnly: true, secure: false, sameSite: 'Lax',
    })
  }
  return sessionCookie
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

// Setiap peran pakai browser context (incognito) terpisah agar cookie sesi
// tidak bocor antar login (pola yang sama dengan gladi resik v2.14).

// ================= 1. MARKETING — form jam kunjungan =================
{
  const ctx = await browser.createBrowserContext()
  const page = await ctx.newPage()
  page.on('console', (m) => { if (m.type() === 'error') errors.push('MKT ' + m.text().slice(0, 160)) })
  page.on('pageerror', (e) => errors.push('MKT PAGEERROR: ' + String(e).slice(0, 160)))
  await login(page, 'marketing_yusie_sby', '123456')
  await page.goto(BASE + '/app/marketing', { waitUntil: 'networkidle2', timeout: 30000 })
  await sleep(3000)
  let hasJam = false
  let hasTimeInput = false
  for (let i = 0; i < 15 && !hasJam; i++) {
    hasJam = await page.evaluate(() => {
      const labels = [...document.querySelectorAll('label')].map((l) => l.textContent)
      return labels.some((t) => t.includes('Jam Kunjungan'))
    })
    hasTimeInput = await page.evaluate(() => !!document.querySelector('input[type="time"]'))
    if (!hasJam) await sleep(1000)
  }
  ok('Marketing Hub: ada label "Jam Kunjungan"', hasJam)
  ok('Marketing Hub: ada input type=time', hasTimeInput)
  await page.screenshot({ path: SHOT_DIR + '/01-marketing-form.png' })
  await ctx.close()
}

// ================= 2. CHIEF DRIVER — Atur Rute Otomatis =================
{
  const ctx = await browser.createBrowserContext()
  const page = await ctx.newPage()
  page.on('console', (m) => { if (m.type() === 'error') errors.push('CD ' + m.text().slice(0, 160)) })
  page.on('pageerror', (e) => errors.push('CD PAGEERROR: ' + String(e).slice(0, 160)))
  await login(page, 'driver', '123456')
  await page.goto(BASE + '/app/chief-driver', { waitUntil: 'networkidle2', timeout: 30000 })
  await sleep(3000)
  let btn = false
  for (let i = 0; i < 15 && !btn; i++) {
    btn = await page.evaluate(() => {
      const b = [...document.querySelectorAll('button')].find((x) => x.textContent.includes('Atur Rute Otomatis'))
      if (b) { b.click(); return true }
      return false
    })
    if (!btn) await sleep(1000)
  }
  ok('Board Chief Driver: tombol "⚡ Atur Rute Otomatis" ada & diklik', btn)

  // Tunggu modal + hasil plan (bisa lambat saat geocoding cache panas)
  let modalShown = false
  for (let i = 0; i < 30 && !modalShown; i++) {
    await sleep(1000)
    modalShown = await page.evaluate(() => !!document.querySelector('.modal-box'))
  }
  ok('Modal "Atur Rute Otomatis" terbuka', modalShown)
  await page.screenshot({ path: SHOT_DIR + '/02-route-modal-loading.png' })

  // Tunggu isi plan (role-chip per driver atau teks penghematan)
  let hasPlan = false
  for (let i = 0; i < 30 && !hasPlan; i++) {
    await sleep(1000)
    hasPlan = await page.evaluate(() => {
      const box = document.querySelector('.modal-box')
      return box && (box.querySelector('.role-chip') || box.textContent.includes('Hemat'))
    })
  }
  const modalText = await page.evaluate(() => document.querySelector('.modal-box')?.textContent || '')
  const hasDrivers = modalText.includes('kunjungan')
  const hasTotal = modalText.includes('Total Jarak')
  // Bandingkan banner penghematan dengan nilai API (data-agnostik):
  // savings > 0 -> banner harus tampil; savings = 0 -> banner boleh tidak ada.
  const apiPlan = await page.evaluate(async () => {
    const r = await fetch('/api/appointments/route-plan?date=' + new Date().toISOString().slice(0, 10))
    const d = await r.json()
    return { savings: d.totals?.savings_percent ?? 0, km: d.totals?.km, baseline: d.totals?.baseline_km }
  }).catch(() => null)
  const banner = modalText.match(/Hemat ([\d.]+)%[^\n]{0,80}/)
  const bannerShown = !!banner
  const bannerCorrect = apiPlan
    ? (apiPlan.savings > 0 ? bannerShown && parseFloat(banner[1]) === apiPlan.savings
                            : !bannerShown)
    : true
  ok('Modal menampilkan rute per driver', hasDrivers)
  ok('Banner penghematan BBM benar (API ' + (apiPlan?.savings ?? '?') + '%)', bannerCorrect,
    banner ? banner[0] : 'tanpa banner (savings 0%)')
  ok('Modal menampilkan statistik total', hasTotal)
  await page.screenshot({ path: SHOT_DIR + '/03-route-modal-plan.png' })

  // Tutup modal (Esc) — aksesibilitas
  await page.keyboard.press('Escape')
  await sleep(400)
  const closed = await page.evaluate(() => !document.querySelector('.modal-box'))
  ok('Modal tertutup dengan Esc', closed)
  await ctx.close()
}

console.log('\n=== ERROR CONSOLE ===')
console.log(errors.length ? errors.join('\n') : '(tidak ada error console)')
await browser.close()
process.exit(errors.length ? 1 : 0)
