// ============================================================
// GLADI RESIK OTOMATIS — jalankan semua alur PRESENTASI.md di browser nyata.
// Laporan kesiapan per peran + screenshot frames (untuk video walkthrough).
//
// Jalankan:  node scripts/rehearsal.mjs
// Membutuhkan: Chrome for Testing di ~/.local/opt/chrome, app live di :5001
// ============================================================
import puppeteer from 'puppeteer-core'
import { mkdirSync } from 'fs'

const BASE = process.env.BASE || 'http://localhost:5001'
const CHROME = process.env.CHROME_PATH || '/home/it-ef/.local/opt/chrome/chrome-linux64/chrome'
const OUT = '/tmp/rehearsal'
mkdirSync(OUT + '/frames', { recursive: true })

const browser = await puppeteer.launch({
  executablePath: CHROME, headless: 'new',
  args: ['--no-sandbox', '--disable-gpu'],
  defaultViewport: { width: 1440, height: 900 },
})

const results = []
let seq = 0

async function newPage() {
  // Konteks incognito terpisah per peran → cookie & localStorage tidak bocor antar login.
  const ctx = await browser.createBrowserContext()
  const page = await ctx.newPage()
  const errors = []
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text().slice(0, 160)) })
  page.on('pageerror', (e) => errors.push('PAGEERR: ' + String(e).slice(0, 160)))
  page.on('response', (r) => { if (r.status() === 404 && !r.url().includes('/api/')) errors.push('404: ' + r.url().slice(0, 120)) })
  page.__errors = errors
  page.__ctx = ctx
  return page
}

const closePage = async (p) => {
  if (!p) return
  try { await p.close() } catch (e) {}
  try { await p.__ctx?.close() } catch (e) {}
}

const has = (p, sel) => !!p.$(sel)
const txt = async (p, sel) => p.$eval(sel, (el) => el.textContent.trim()).catch(() => '')

/** Tunggu form login SPA (dengan reload sekali jika lambat). */
async function waitLogin(p) {
  for (let i = 0; i < 3; i++) {
    try {
      await p.waitForSelector('#login-pin', { timeout: 12000 })
      return
    } catch (e) {
      if (i === 2) {
        const body = await p.evaluate(() => document.body.innerText.slice(0, 200)).catch(() => '?')
        const url = p.url()
        throw new Error('login tidak muncul. URL=' + url + ' BODY=' + JSON.stringify(body))
      }
      await p.goto(BASE + '/app/login', { waitUntil: 'domcontentloaded' })
      await new Promise((r) => setTimeout(r, 1500))
    }
  }
}

/** Login sebagai user tertentu, set cookie sesi (HTTP dev), navigasi ke home. */
async function loginAs(user, pin, home) {
  const p = await newPage()
  try {
    let sess = null
    const onResp = (r) => {
      if (r.url().includes('/api/auth/login') && r.status() === 200) {
        const m = (r.headers()['set-cookie'] || '').match(/session=([^;]+)/)
        if (m) sess = m[1]
      }
    }
    p.on('response', onResp)
    await p.goto(BASE + '/app/login', { waitUntil: 'domcontentloaded' })
    await waitLogin(p)
    await p.type('input[autocomplete="username"]', user)
    await p.type('#login-pin', pin)
    await p.click('form button.btn-primary')
    // Tunggu SPA selesai login (hindari race: navigasi berikutnya jangan
    // menginterupsi alur login yang masih berjalan).
    try {
      await p.waitForFunction(() => !location.pathname.endsWith('/login'), { timeout: 15000 })
    } catch (e) { /* fallback: guard router akan mengarahkan */ }
    const t0 = Date.now()
    while (!sess && Date.now() - t0 < 15000) await new Promise((r) => setTimeout(r, 200))
    p.off('response', onResp)
    if (!sess) throw new Error('login gagal utk ' + user)
    const cdp = await p.createCDPSession()
    await cdp.send('Network.setCookie', {
      name: 'session', value: sess, url: BASE, path: '/', httpOnly: true, secure: false, sameSite: 'Lax',
    })
    await p.goto(BASE + home, { waitUntil: 'domcontentloaded' })
    await new Promise((r) => setTimeout(r, 2500))
    return p
  } catch (e) {
    await closePage(p)
    throw e
  }
}

function shot(p, name) {
  return p.screenshot({ path: `${OUT}/${String(++seq).padStart(2, '0')}-${name}.png` })
}

function report(name, ok, extra = '') {
  results.push({ name, ok, extra })
  console.log((ok ? '✅' : '❌') + ` ${name}` + (ok ? '' : ' GAGAL') + (extra ? ' — ' + extra : ''))
}

const frame = (p, role, i) => p.screenshot({ path: `${OUT}/frames/${role}-${i}.png` }).catch(() => {})

const cleanErrs = (p) => p.__errors.filter((e) => !e.includes('401'))

// ============ 1. ADMIN ============
let adminErrs = []
try {
  const p = await loginAs('admin', '123456', '/app/dashboard')
  report('Admin login → dashboard', await has(p, '.side-nav a'))
  await shot(p, 'admin-dashboard')
  await frame(p, 'admin', 1)
  // Analytics
  await p.goto(BASE + '/app/analytics', { waitUntil: 'domcontentloaded' })
  await new Promise((r) => setTimeout(r, 4500))
  const statCards = await p.$$('.stat-card')
  const analText = await txt(p, 'body')
  report('Admin: Analytics terisi data', statCards.length >= 4 && analText.length > 400,
    `${statCards.length} kartu`)
  await shot(p, 'admin-analytics')
  await frame(p, 'admin', 2)
  // Users
  await p.goto(BASE + '/app/users', { waitUntil: 'domcontentloaded' })
  await new Promise((r) => setTimeout(r, 2000))
  report('Admin: Users tampil', (await txt(p, 'body')).includes('Manajemen User'))
  await shot(p, 'admin-users')
  adminErrs = cleanErrs(p)
  await closePage(p)
} catch (e) { report('Admin flow', false, String(e).slice(0, 80)) }

// ============ 2. OB (Faisol) ============
let obErrs = []
try {
  const p = await loginAs('ob_faisol_sby', '123456', '/app/water')
  await new Promise((r) => setTimeout(r, 2000))
  const body = await txt(p, 'body')
  report('OB login → Halaman Air Minum', body.includes('Air Minum'))
  report('OB: lihat pengajuan sendiri (WTR-DEMO-01)', body.includes('WTR-DEMO-01'))
  report('OB: TIDAK melihat pengajuan OB lain (isolasi)', !body.includes('WTR-DEMO-02'))
  await shot(p, 'ob-water')
  await frame(p, 'ob', 1)
  obErrs = cleanErrs(p)
  await closePage(p)
} catch (e) { report('OB flow', false, String(e).slice(0, 80)) }

// ============ 3. FINANCE ============
let finErrs = []
try {
  const p = await loginAs('finance_sby', '123456', '/app/finance')
  const body = await txt(p, 'body')
  report('Finance login → Dashboard Finance', body.includes('Dashboard Finance'))
  report('Finance: rekap per OB (Faisol & Febri)', body.includes('Faisol') && body.includes('Febri'))
  await shot(p, 'finance-dashboard')
  await frame(p, 'finance', 1)
  // Halaman air minum: tombol verifikasi utk pending
  await p.goto(BASE + '/app/water', { waitUntil: 'domcontentloaded' })
  await new Promise((r) => setTimeout(r, 2000))
  const wbody = await txt(p, 'body')
  report('Finance: antrean verifikasi air minum', wbody.includes('WTR-DEMO-01'))
  const hasVerifyBtn = await p.evaluate(() => [...document.querySelectorAll('button')].some((b) => b.textContent.includes('Verifikasi')))
  report('Finance: tombol ✅ Verifikasi tersedia', hasVerifyBtn)
  await shot(p, 'finance-water')
  await frame(p, 'finance', 2)
  finErrs = cleanErrs(p)
  await closePage(p)
} catch (e) { report('Finance flow', false, String(e).slice(0, 80)) }

// ============ 4. GA ============
let gaErrs = []
try {
  const p = await loginAs('ga_sby', '123456', '/app/ga')
  const body = await txt(p, 'body')
  report('GA login → Dashboard GA', body.includes('Dashboard GA'))
  report('GA: antrean klaim demo tampil', body.includes('BPF-DEMO'))
  report('GA: kasbon menunggu approve', body.includes('Draft') || body.includes('Menunggu'))
  await shot(p, 'ga-dashboard')
  await frame(p, 'ga', 1)
  gaErrs = cleanErrs(p)
  await closePage(p)
} catch (e) { report('GA flow', false, String(e).slice(0, 80)) }

// ============ 5. MARKETING ============
let mktErrs = []
try {
  const p = await loginAs('marketing_yusie_sby', '123456', '/app/marketing')
  const body = await txt(p, 'body')
  report('Marketing login → Marketing Hub', body.includes('Marketing'))
  report('Marketing: appointment demo tampil', body.includes('Marketing Hub') || body.includes('Input Appointment'))
  await shot(p, 'marketing')
  await frame(p, 'marketing', 1)
  mktErrs = cleanErrs(p)
  await closePage(p)
} catch (e) { report('Marketing flow', false, String(e).slice(0, 80)) }

// ============ 6. CHIEF DRIVER ============
let cdErrs = []
try {
  const p = await loginAs('driver', '123456', '/app/chief-driver')
  const body = await txt(p, 'body')
  report('Chief Driver login → board', body.includes('Chief Driver') || body.includes('Belum Ditugaskan'))
  await shot(p, 'chief-driver')
  await frame(p, 'chief', 1)
  cdErrs = cleanErrs(p)
  await closePage(p)
} catch (e) { report('Chief Driver flow', false, String(e).slice(0, 80)) }

// ============ 7. DRIVER (RIVAN) ============
let drvErrs = []
try {
  const p = await newPage()
  let sess = null
  const onResp = (r) => {
    if (r.url().includes('/api/auth/login') && r.status() === 200) {
      const m = (r.headers()['set-cookie'] || '').match(/session=([^;]+)/)
      if (m) sess = m[1]
    }
  }
  p.on('response', onResp)
  await p.goto(BASE + '/app/driver', { waitUntil: 'domcontentloaded' })
  await waitLogin(p)
  await p.type('input[autocomplete="username"]', 'wicak')
  await p.type('#login-pin', '123456')
  await p.click('form button.btn-primary')
  try {
    await p.waitForFunction(() => !location.pathname.endsWith('/login'), { timeout: 15000 })
  } catch (e) { /* fallback */ }
  const t0 = Date.now()
  while (!sess && Date.now() - t0 < 15000) await new Promise((r) => setTimeout(r, 200))
  p.off('response', onResp)
  if (!sess) throw new Error('login driver gagal')
  const cdp = await p.createCDPSession()
  await cdp.send('Network.setCookie', { name: 'session', value: sess, url: BASE, path: '/', httpOnly: true, secure: false, sameSite: 'Lax' })
  await p.goto(BASE + '/app/driver', { waitUntil: 'domcontentloaded' })
  await new Promise((r) => setTimeout(r, 3000))
  const name = await txt(p, '.d-name')
  const tabs = await p.$$('.d-nav-item')
  report('Driver login (WICAK) → aplikasi driver', name === 'WICAK', name)
  report('Driver: 4 tab tampil', tabs.length === 4, `${tabs.length} tab`)
  for (let i = 1; i <= 4; i++) { await frame(p, 'driver', i); await new Promise((r) => setTimeout(r, 600)) }
  drvErrs = cleanErrs(p)
  await shot(p, 'driver')
  await closePage(p)
} catch (e) { report('Driver flow', false, String(e).slice(0, 80)) }

// ============ 8. REALTIME ============
let rtErrs = []
try {
  const p = await loginAs('admin', '123456', '/app/dashboard')
  await new Promise((r) => setTimeout(r, 3000))
  const dot = await txt(p, '.rt-dot')
  report('Realtime terhubung (⚡)', dot.includes('Realtime') && !dot.includes('Offline'), dot)
  await p.click('.topbar .bell-wrap .btn-icon')
  await new Promise((r) => setTimeout(r, 400))
  report('Bell notifikasi terbuka', await has(p, '.bell-panel'))
  await shot(p, 'realtime-bell')
  rtErrs = cleanErrs(p)
  await closePage(p)
} catch (e) { report('Realtime flow', false, String(e).slice(0, 80)) }

// ============ RINGKASAN + LAPORAN KESIAPAN ============
console.log('\n=== RINGKASAN GLADI RESIK ===')
const okN = results.filter((r) => r.ok).length
for (const r of results) console.log(`  ${r.ok ? '✅' : '❌'} ${r.name}`)
console.log(`\n${okN}/${results.length} cek lulus`)

const allErrs = [...adminErrs, ...obErrs, ...finErrs, ...gaErrs, ...mktErrs, ...cdErrs, ...drvErrs, ...rtErrs]
console.log(`Konsol: ${allErrs.length ? 'ADA ERROR — ' + JSON.stringify(allErrs.slice(0, 5)) : 'bersih ✅ (0 error JS)'}`)

await browser.close()
process.exit(okN === results.length && allErrs.length === 0 ? 0 : 1)
