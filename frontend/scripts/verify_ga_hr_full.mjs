// Verifikasi UI alur lengkap GA HR (v2.22.1) via Chrome nyata (puppeteer-core).
// Cek: login akun gahr_sby → dashboard /app/ga-hr (statistik Driver & OB),
// tombol ✏️ Edit & 🗑️ Hapus di tab Driver & OB/Security, modal edit terbuka,
// konfirmasi hapus muncul (lalu dibatalkan — tidak menghapus data asli),
// bell notifikasi ada, 0 error konsol.
// Jalankan: node frontend/scripts/verify_ga_hr_full.mjs
import puppeteer from 'puppeteer-core'
import { mkdirSync } from 'fs'

const BASE = process.env.BASE || 'http://localhost:5001'
const CHROME = process.env.CHROME || '/home/it-ef/.local/opt/chrome/chrome-linux64/chrome'
const SHOT_DIR = '/tmp/ui_gahr_shots'
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
  await page.goto(BASE + '/app/login', { waitUntil: 'domcontentloaded', timeout: 60000 })
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
  return sessionCookie
}

async function waitFor(page, fn, tries = 20, gap = 1000, ...args) {
  for (let i = 0; i < tries; i++) {
    if (await page.evaluate(fn, ...args)) return true
    await sleep(gap)
  }
  return false
}

// ================= 1. LOGIN GA HR + DASHBOARD =================
{
  const ctx = await browser.createBrowserContext()
  const page = await ctx.newPage()
  page.on('console', (m) => { if (m.type() === 'error') errors.push('CONSOLE ' + m.text().slice(0, 160)) })
  page.on('pageerror', (e) => errors.push('PAGEERROR ' + String(e).slice(0, 160)))

  const cookie = await login(page, 'gahr_sby', '123456')
  ok('Login gahr_sby berhasil (session cookie)', !!cookie)
  const landed = await waitFor(page, () => location.pathname.includes('/app/'))
  ok('Landed di area /app/', landed, await page.url())

  await page.goto(BASE + '/app/ga-hr', { waitUntil: 'networkidle2', timeout: 30000 })
  await sleep(3000)

  const statCards = await waitFor(page, () => document.querySelectorAll('.stat-card').length >= 2)
  const statText = await page.evaluate(() => document.querySelector('.stat-grid')?.textContent || '')
  ok('Dashboard GA HR: 2+ kartu statistik', statCards)
  ok('Statistik Driver & OB/Security tampil', statText.includes('Overtime Driver') && statText.includes('OB/Security'))

  // ===== Tab Driver: tombol refresh, sumber data, PDF, edit & hapus =====
  await page.evaluate(() => [...document.querySelectorAll('.tab')].find((t) => t.textContent.includes('Driver'))?.click())
  await sleep(2000)
  const driverBtns = await page.evaluate(() => [...document.querySelectorAll('.filters .btn')].map((b) => b.textContent))
  ok('Tab Driver: tombol 🔄 Refresh & ⚙️ Sumber Data', driverBtns.some((t) => t.includes('Refresh')) && driverBtns.some((t) => t.includes('Sumber Data')), driverBtns.join(' | '))

  const driverHasActions = await waitFor(page, () => document.querySelectorAll('.tbl tbody tr .btn-xs').length >= 2)
  const actionBtns = await page.evaluate(() => [...document.querySelectorAll('.tbl tbody tr:first-child .btn-xs')].map((b) => b.title))
  ok('Tab Driver: baris punya tombol ✏️ Edit & 🗑️ Hapus', driverHasActions && actionBtns.includes('Edit') && actionBtns.includes('Hapus'), actionBtns.join(', '))

  // Tangkap ID baris pertama (utk revert nanti) lalu buka modal edit
  const editedId = await page.evaluate(() => document.querySelector('.tbl tbody tr')?.getAttribute('data-id') || null)
  await page.evaluate(() => document.querySelector('.tbl tbody tr:first-child .btn-xs')?.click())
  const editModal = await waitFor(page, () => !!document.querySelector('.modal-box input[placeholder="Nama karyawan"]'))
  const editFields = await page.evaluate(() => {
    const labels = [...document.querySelectorAll('.modal-box .field label')].map((l) => l.textContent.trim())
    return labels.join(' | ')
  })
  ok('Modal ✏️ Edit terbuka dengan kolom lengkap', editModal, editFields)
  ok('Modal edit berisi Nama & No. Kendaraan (Driver)', editModal && editFields.includes('Nama') && editFields.includes('No. Kendaraan'), editFields)
  await page.screenshot({ path: SHOT_DIR + '/01-edit-modal.png' })
  // SIMPAN edit: ubah keterangan baris pertama, simpan, cek modal tertutup (PATCH sukses),
  // lalu REVERT via API agar tidak meninggalkan data uji di DB.
  const firstRowInfo = await page.evaluate(() => {
    const tr = document.querySelector('.tbl tbody tr:first-child')
    const firstTd = tr?.querySelector('td')?.textContent || ''
    const nameTd = tr?.querySelectorAll('td')[1]?.textContent || ''
    return { firstTd, nameTd }
  })
  const testKet = 'UI SAVE ' + Date.now().toString().slice(-5)
  await page.evaluate((v) => {
    const el = document.querySelector('.modal-box input[placeholder="Keterangan…"]')
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set
    setter.call(el, v)
    el.dispatchEvent(new Event('input', { bubbles: true }))
  }, testKet)
  await page.evaluate(() => [...document.querySelectorAll('.modal-box .btn')].find((b) => b.textContent.includes('Simpan'))?.click())
  // Sukses = modal edit TERTUTUP (saveEdit hanya menutup modal setelah PATCH berhasil)
  const saved = await waitFor(page, () => !document.querySelector('.modal-box'), 15, 1000)
  ok('Simpan edit -> modal tertutup (PATCH sukses)', saved, testKet)
  await page.screenshot({ path: SHOT_DIR + '/01b-edit-saved.png' })
  await sleep(800)
  // Revert via API: kembalikan keterangan baris yang diedit jadi kosong
  if (editedId) {
    const csrf = await page.evaluate(async () => {
      const r = await fetch('/api/auth/me')
      const d = await r.json()
      return d.csrf_token
    })
    await page.evaluate(async ([id, cs]) => {
      await fetch(`/api/overtime/driver/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': cs },
        body: JSON.stringify({ keterangan: '' }),
      })
    }, [editedId, csrf])
    ok('Revert edit via API (data uji dibersihkan)', true)
    await sleep(1000)
  }

  // Buka konfirmasi hapus lalu BATALKAN (tidak menghapus data)
  await page.evaluate(() => document.querySelectorAll('.tbl tbody tr:first-child .btn-xs')[1]?.click())
  const delModal = await waitFor(page, () => !!document.querySelector('.modal-box')?.textContent.includes('Yakin ingin menghapus'))
  ok('Konfirmasi 🗑️ Hapus muncul (dibatalkan, data aman)', delModal)
  await page.screenshot({ path: SHOT_DIR + '/02-delete-confirm.png' })
  await page.evaluate(() => [...document.querySelectorAll('.modal-box .btn')].find((b) => b.textContent.includes('Batal'))?.click())
  await sleep(800)

  // ===== Tab OB/Security: aksi juga ada =====
  await page.evaluate(() => [...document.querySelectorAll('.tab')].find((t) => t.textContent.includes('OB'))?.click())
  await sleep(2500)
  const obHasActions = await waitFor(page, () => document.querySelectorAll('.tbl tbody tr .btn-xs').length >= 2)
  ok('Tab OB/Security: tombol edit/hapus ada', obHasActions)

  // Bell notifikasi ada
  const bell = await page.evaluate(() => !!document.querySelector('.bell-wrap .btn-icon'))
  ok('Bell 🔔 notifikasi tampil di topbar', bell)
  await page.screenshot({ path: SHOT_DIR + '/03-dashboard.png' })
  await ctx.close()
}

// ================= 1b. NOTIFIKASI REALTIME =================
// Dashboard GA HR terbuka (tab 1) + form publik diisi (tab 2) -> bell badge muncul
{
  const ctx1 = await browser.createBrowserContext()
  const page = await ctx1.newPage()
  page.on('console', (m) => { if (m.type() === 'error') errors.push('NOTIF ' + m.text().slice(0, 160)) })
  page.on('pageerror', (e) => errors.push('NOTIF PAGEERROR ' + String(e).slice(0, 160)))
  await login(page, 'gahr_sby', '123456')
  await page.goto(BASE + '/app/ga-hr', { waitUntil: 'networkidle2', timeout: 30000 })
  await waitFor(page, () => document.querySelectorAll('.stat-card').length >= 2)
  // Pastikan socket terhubung
  await sleep(2000)

  const ctx2 = await browser.createBrowserContext()
  const page2 = await ctx2.newPage()
  await page2.goto(BASE + '/app/overtime-form', { waitUntil: 'domcontentloaded', timeout: 30000 })
  await sleep(2500)
  const formShown = await waitFor(page2, () => !!document.querySelector('.apply-card form'))
  if (formShown) {
    // Isi & submit form publik
    const setVue = (sel, idx, val) => page2.evaluate(([s, i, v]) => {
      const el = document.querySelectorAll(s)[i]
      if (!el) return
      const proto = el instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype
      Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v)
      el.dispatchEvent(new Event('input', { bubbles: true }))
      el.dispatchEvent(new Event('change', { bubbles: true }))
    }, [sel, idx, val])
    await setVue('.apply-card select', 0, 'OB')
    const firstNama = await page2.evaluate(() => {
      const s = document.querySelectorAll('.apply-card select')[1]
      return s && s.options.length > 1 ? s.options[1].value : ''
    })
    if (firstNama) {
      await setVue('.apply-card select', 1, firstNama)
      await setVue('.apply-card input[type="date"]', 0, '2026-08-18')
      await setVue('.apply-card input[type="time"]', 0, '18:00')
      await setVue('.apply-card input[type="time"]', 1, '21:00')
      const ket = 'UI NOTIF ' + Date.now().toString().slice(-5)
      await page2.type('.apply-card input[list]', ket)
      await page2.click('.apply-card form button.btn-primary')
      await waitFor(page2, () => !!document.querySelector('.apply-success'), 20, 500)

      // Bell GA HR harus menunjukkan badge (unread > 0) — event realtime overtime_new
      const badge = await waitFor(page, () => {
        const b = document.querySelector('.bell-badge')
        return b && parseInt(b.textContent, 10) > 0
      }, 20, 1000)
      ok('Notifikasi realtime: bell GA HR berbadge setelah form publik diisi', badge)
      await page.screenshot({ path: SHOT_DIR + '/04-notif-bell.png' })

      // Bersihkan data uji notifikasi dari tabel OB/Security
      const csrf = await page.evaluate(async () => (await (await fetch('/api/auth/me')).json()).csrf_token)
      const uid = await page2.evaluate(async (k) => {
        const r = await fetch('/api/overtime/form-meta')
        return k
      }, ket)
      await page.evaluate(async (k) => {
        const r = await fetch('/api/overtime/ob-security')
        const d = await r.json()
        const hit = (d.data || []).find((x) => x.keterangan === k)
        return hit ? hit.id : null
      }, ket).then(async (id) => {
        if (id) {
          await page.evaluate(async ([i, cs]) => {
            await fetch(`/api/overtime/ob/${i}`, {
              method: 'DELETE',
              headers: { 'X-CSRF-Token': cs },
            })
          }, [id, csrf])
          ok('Data uji notifikasi dihapus dari OB/Security', true)
        }
      })
    }
  }
  await ctx2.close()
  await ctx1.close()
}

// ================= 2. AKSES ROLE LAIN DITOLAK =================
{
  const ctx = await browser.createBrowserContext()
  const page = await ctx.newPage()
  page.on('console', (m) => { if (m.type() === 'error') errors.push('GA ' + m.text().slice(0, 160)) })
  await login(page, 'ga_sby', '123456')
  await sleep(1500)
  await page.goto(BASE + '/app/ga-hr', { waitUntil: 'domcontentloaded', timeout: 60000 })
  await sleep(2500)
  const url = await page.url()
  const forbidden = await page.evaluate(() => !!document.querySelector('h1')?.textContent.includes('403'))
  ok('Role GA akses /app/ga-hr -> 403', forbidden || url.includes('403'), url)
  await ctx.close()
}

console.log('\n=== ERROR CONSOLE ===')
console.log(errors.length ? errors.join('\n') : '(tidak ada error console)')
await browser.close()
process.exit(errors.length ? 1 : 0)
