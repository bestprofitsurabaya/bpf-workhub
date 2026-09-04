// ============================================================
// REKAM VIDEO WALKTHROUGH PER PERAN — screenshot berkala (andal)
// Ambil serangkaian screenshot saat berinteraksi, lalu gabung
// dengan efek zoom (Ken Burns), kartu judul, transisi fade, dan
// keterangan adegan via scripts/make_videos.sh
//
// Jalankan:  node scripts/record.mjs [role1 role2 ...]
// Hasil:     /tmp/record/<role>/sNN.png + captions.json
// ============================================================
import puppeteer from 'puppeteer-core'
import { mkdirSync, rmSync, writeFileSync } from 'fs'

const BASE = process.env.BASE || 'http://localhost:5001'
const CHROME = process.env.CHROME_PATH || '/home/it-ef/.local/opt/chrome/chrome-linux64/chrome'
const OUT = '/tmp/record'
mkdirSync(OUT, { recursive: true })

// ------------------------------------------------------------
// Definisi adegan per peran.
// Setiap scene: caption teks (tampil di video) + aksi opsional:
//   goto:  navigasi path          tab:  klik tab driver (0-3)
//   click: klik tombol (berisi teks)   fill: isi input lalu change (deteksi area)
//   wait:  jeda ekstra (ms)
// ------------------------------------------------------------
const ROLES = {
  admin: {
    user: 'admin', home: '/app/dashboard',
    title: 'Admin',
    subtitle: 'Dashboard · Analytics · Users · Settings',
    scenes: [
      { caption: 'Ringkasan seluruh operasi — klaim, kasbon, air minum' },
      { caption: 'Analytics — tren nominal & efisiensi armada', goto: '/app/analytics' },
      { caption: 'Manajemen User — akun & PIN per peran', goto: '/app/users' },
      { caption: 'Pengaturan — driver, kendaraan & BBM', goto: '/app/settings' },
    ],
  },
  ob: {
    user: 'ob_faisol_sby', home: '/app/water',
    title: 'OB — Air Minum',
    subtitle: 'Faisol · bukti foto sebelum & sesudah',
    scenes: [
      { caption: 'Daftar pengajuan air minum OB (Faisol)' },
      { caption: 'Form pengajuan — wajib unggah 2 foto', click: 'Ajukan Pembelian' },
    ],
  },
  finance: {
    user: 'finance_sby', home: '/app/finance',
    title: 'Finance',
    subtitle: 'Verifikasi air minum · rekap · kasbon',
    scenes: [
      { caption: 'Dashboard Finance — rekap per OB, jenis & merk' },
      { caption: 'Antrean verifikasi air minum (WTR-DEMO-01)', goto: '/app/water' },
      { caption: 'Modal verifikasi — remark wajib untuk jejak audit', click: 'Verifikasi' },
      { caption: 'Kasbon — persetujuan Finance & verifikasi LPJ', goto: '/app/cash' },
    ],
  },
  ga: {
    user: 'ga_sby', home: '/app/ga',
    title: 'GA',
    subtitle: 'Antrean klaim BBM · kasbon · trip',
    scenes: [
      { caption: 'Dashboard GA — antrean klaim + verifikasi anomali ML' },
      { caption: 'Kasbon — approve GA lalu diteruskan ke Finance', goto: '/app/cash' },
      { caption: 'Analytics — data klaim & efisiensi armada', goto: '/app/analytics' },
    ],
  },
  marketing: {
    user: 'marketing_yusie_sby', home: '/app/marketing',
    title: 'Marketing',
    subtitle: 'Input appointment · deteksi area otomatis',
    scenes: [
      { caption: 'Marketing Hub — form input + ringkasan harian' },
      {
        caption: 'Isi form — deteksi area otomatis 📍 dari alamat',
        fill: [
          { sel: 'input[placeholder*="Nama calon nasabah"]', val: 'Toko Sumber Berkah' },
          { sel: 'input[placeholder*="Anggota tim yang memprospek"]', val: 'Ahmad' },
          { sel: 'input[placeholder*="Alamat calon nasabah"]', val: 'Jl. Darmo Permai III No. 12, Surabaya', change: true },
        ],
      },
    ],
  },
  chief: {
    user: 'chief_driver_sby', home: '/app/chief-driver',
    title: 'Chief Driver',
    subtitle: 'Board penugasan · saran load-balancing',
    scenes: [
      { caption: 'Board — kendaraan belum ditugaskan + saran driver otomatis' },
      { caption: 'Ringkasan per marketing anggota & export Excel', scrollY: 600 },
    ],
  },
  driver: {
    user: 'wicak', home: '/app/driver',
    title: 'Driver PWA',
    subtitle: 'BBM · Kasbon · Trip · OT · Rapor',
    scenes: [
      { caption: 'Profil & status — tab BBM, form klaim + foto struk' },
      { caption: '💰 Kasbon — kode unik harian & riwayat', tab: 1 },
      { caption: '🗺️ Trip — jadwal appointment saya', tab: 2 },
      { caption: '⏰ Overtime — submit dengan foto watermark + GPS detail', tab: 3 },
      { caption: '📊 Rapor — performa km/L', tab: 4 },
    ],
  },
  receptionist: {
    user: 'receptionist_sby', home: '/app/receptionist',
    title: 'Receptionist',
    subtitle: 'Verifikasi pelamar · kehadiran interview',
    scenes: [
      { caption: 'Daftar pelamar kerja — filter & verifikasi' },
      { caption: 'Detail pelamar — kehadiran interview & training', goto: '/app/receptionist' },
    ],
  },
  traineer: {
    user: 'traineer_sby', home: '/app/traineer',
    title: 'Traineer / Upline',
    subtitle: 'Pantau kehadiran rekrutan',
    scenes: [
      { caption: 'Rekrutan saya — kehadiran H1-H4 & status' },
    ],
  },
  ga_hr: {
    user: 'gahr_sby', home: '/app/ga-hr',
    title: 'GA HR — Overtime',
    subtitle: 'Driver & OB/Security · foto bukti · GPS',
    scenes: [
      { caption: 'Dashboard GA HR — statistik overtime Driver & OB/Security' },
      { caption: 'Data overtime Driver — sinkron Google Sheet + filter sumber', goto: '/app/ga-hr' },
      { caption: 'Tab OB & Security — paritas penuh: Refresh, PDF, Detail/Excel', click: 'OB & Security' },
      { caption: 'Viewer foto bukti 📷 — foto mulai & selesai tiap catatan', click: '📷' },
    ],
  },
}
const only = process.argv.slice(2)

const browser = await puppeteer.launch({
  executablePath: CHROME, headless: 'new',
  args: ['--no-sandbox', '--disable-gpu'],
  defaultViewport: { width: 1440, height: 900 },
})

async function loginPage(user, pin, home) {
  const ctx = await browser.createBrowserContext()
  const p = await ctx.newPage()
  let sess = null
  const onResp = (r) => {
    if (r.url().includes('/api/auth/login') && r.status() === 200) {
      const m = (r.headers()['set-cookie'] || '').match(/session=([^;]+)/)
      if (m) sess = m[1]
    }
  }
  p.on('response', onResp)
  await p.goto(BASE + '/app/login', { waitUntil: 'domcontentloaded' })
  for (let i = 0; i < 3; i++) {
    try { await p.waitForSelector('input[autocomplete="username"]', { timeout: 12000 }); break }
    catch (e) { if (i === 2) throw e; await p.goto(BASE + '/app/login', { waitUntil: 'domcontentloaded' }) }
  }
  await p.type('input[autocomplete="username"]', user)
  await p.type('input[autocomplete="current-password"]', pin)
  await p.click('button.login-btn')
  const t0 = Date.now()
  while (!sess && Date.now() - t0 < 15000) await new Promise((r) => setTimeout(r, 200))
  p.off('response', onResp)
  if (!sess) throw new Error('login gagal ' + user)
  const cdp = await p.createCDPSession()
  await cdp.send('Network.setCookie', { name: 'session', value: sess, url: BASE, path: '/', httpOnly: true, secure: false, sameSite: 'Lax' })
  await p.goto(BASE + home, { waitUntil: 'domcontentloaded' })
  await new Promise((r) => setTimeout(r, 2500))
  return { p, ctx }
}

/** Klik tombol yang teksnya mengandung `text` (anti selektor rapuh). */
async function clickByText(p, text) {
  const ok = await p.evaluate((t) => {
    const b = [...document.querySelectorAll('button')].find((x) => x.textContent.includes(t))
    if (!b) return false
    b.click(); return true
  }, text)
  if (!ok) throw new Error('tombol tidak ditemukan: ' + text)
}

/** Isi input ala Vue (native setter + event input/change). */
async function fillInput(p, sel, val, withChange) {
  await p.evaluate(([s, v, ch]) => {
    const el = document.querySelector(s)
    if (!el) return
    const proto = el.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v)
    el.dispatchEvent(new Event('input', { bubbles: true }))
    if (ch) el.dispatchEvent(new Event('change', { bubbles: true }))
  }, [sel, val, !!withChange])
}

async function record(role) {
  const cfg = ROLES[role]
  const dir = `${OUT}/${role}`
  rmSync(dir, { recursive: true, force: true }) // bersihkan hasil run lama
  mkdirSync(dir, { recursive: true })
  console.log('🎬 merekam', role, '...')
  const { p, ctx } = await loginPage(cfg.user, '123456', cfg.home)
  const meta = { title: cfg.title, subtitle: cfg.subtitle, scenes: [] }
  let n = 0

  const cap = async (scene, extraWait = 0) => {
    if (extraWait) await new Promise((r) => setTimeout(r, extraWait))
    await p.screenshot({ path: `${dir}/s${String(++n).padStart(2, '0')}.png` })
    meta.scenes.push({ file: `s${String(n).padStart(2, '0')}.png`, caption: scene.caption })
    console.log(`  ${meta.scenes.length}. ${scene.caption}`)
  }

  for (const scene of cfg.scenes) {
    try {
      if (scene.goto) { await p.goto(BASE + scene.goto, { waitUntil: 'domcontentloaded' }); await new Promise((r) => setTimeout(r, 1400)) }
      if (scene.click) { await clickByText(p, scene.click); await new Promise((r) => setTimeout(r, 900)) }
      if (scene.fill) {
        for (const f of scene.fill) await fillInput(p, f.sel, f.val, f.change)
        await new Promise((r) => setTimeout(r, 1200)) // tunggu preview area
      }
      if (scene.tab !== undefined) {
        await p.evaluate((i) => { document.querySelectorAll('.d-nav-item')[i]?.click() }, scene.tab)
        await new Promise((r) => setTimeout(r, 900))
      }
      if (scene.scrollY) { await p.evaluate((y) => window.scrollTo(0, y), scene.scrollY); await new Promise((r) => setTimeout(r, 700)) }
      await cap(scene, 700)
    } catch (e) {
      console.log('  ⚠ skip adegan:', scene.caption, '—', String(e).slice(0, 80))
      try { await cap(scene, 300) } catch (e2) { console.log('  ✗ gagal total:', String(e2).slice(0, 80)) }
    }
  }

  writeFileSync(`${dir}/captions.json`, JSON.stringify(meta, null, 2))
  console.log(`  ${role}: ${n} screenshot + captions.json`)
  await ctx.close().catch(() => {})
}

for (const role of Object.keys(ROLES)) {
  if (only.length && !only.includes(role)) continue
  try { await record(role) } catch (e) { console.log('❌', role, String(e).slice(0, 100)) }
}

await browser.close()
console.log('Selesai — screenshot di', OUT)
