import { describe, it, expect } from 'vitest'
import router from './index'

// Regresi: form publik FirstWork dulu memakai path yang sama dengan halaman data,
// sehingga menu "Absensi FirstWork" membuka form, bukan daftar data.
describe('path Absensi FirstWork', () => {
  it('/first-work menampilkan halaman data, bukan form publik', () => {
    const route = router.resolve('/first-work')
    expect(route.name).toBe('first-work')
    expect(route.meta.roles).toEqual(expect.arrayContaining(['traineer', 'finance', 'ga_hr', 'admin']))
  })

  it('form publik punya path sendiri dan tetap tanpa login', () => {
    const route = router.resolve('/first-work-form')
    expect(route.name).toBe('first-work-form')
    expect(route.meta.public).toBe(true)
  })
})

// v2.113.0 — Registrasi CV Online: halaman data kini menjadi tab di hub;
// tautan lama tetap terdaftar sebagai redirect ke tab CV. Form publik di path
// terpisah dan tanpa login.
describe('form publik lama', () => {
  it('/apply dialihkan ke portal rekrutmen', async () => {
    const { setActivePinia, createPinia } = await import('pinia')
    setActivePinia(createPinia())
    await router.push('/apply')
    expect(router.currentRoute.value.name).toBe('recruitment-portal')
    expect(router.currentRoute.value.meta.public).toBe(true)
  })
})

describe('path Registrasi CV Online', () => {
  it('/cv-online tetap terdaftar dan mengarah ke tab CV di hub', () => {
    const route = router.resolve('/cv-online')
    // Redirect diproses sebelum guard; otorisasi diverifikasi di rute hub.
    expect(route.meta.roles).toBeUndefined()
    expect(route.matched.map((m) => JSON.stringify(m.redirect || ''))
      .some((s) => s.includes('cv'))).toBe(true)
  })

  it('form publik punya path sendiri dan tetap tanpa login', () => {
    const route = router.resolve('/cv-online-form')
    expect(route.name).toBe('cv-online-form')
    expect(route.meta.public).toBe(true)
  })
})

// Rilis A (Task 6) — dashboard kasus rekrutmen untuk staff; URL lama kini
// menjadi tab Kasus di hub. Otorisasi berada pada meta peran hub, bukan record
// redirect (lihat navigation test di firstWorkGuard.test.js).
describe('path Dashboard kasus rekrutmen', () => {
  it('/recruitment-cases tetap terdaftar dan mengarah ke tab Kasus', () => {
    const route = router.resolve('/recruitment-cases')
    expect(route.meta.roles).toBeUndefined()
    expect(route.meta.public).toBeFalsy()
    expect(route.matched.map((m) => JSON.stringify(m.redirect || ''))
      .some((s) => s.includes('kasus'))).toBe(true)
  })
})

describe('hub rekrutmen', () => {
  it('/recruitment memakai gabungan peran staff rekrutmen', () => {
    const route = router.resolve('/recruitment')
    expect(route.name).toBe('recruitment')
    expect(route.meta.roles).toEqual(expect.arrayContaining(
      ['receptionist', 'traineer', 'finance', 'ga_hr', 'admin']))
  })

  it('rute lama tetap terdaftar dan mengarah ke tab yang tepat', () => {
    for (const [path, tab] of [['/receptionist', 'pelamar'],
      ['/recruitment-cases', 'kasus'], ['/cv-online', 'cv']]) {
      const r = router.resolve(path)
      expect(r.matched.length).toBeGreaterThan(0)
      const redirects = r.matched.map((m) => JSON.stringify(m.redirect || ''))
      expect(redirects.some((s) => s.includes(tab))).toBe(true)
    }
  })

  it('/traineer lama mengarah ke tab Pelamar di hub', () => {
    const record = router.getRoutes().find((r) => r.path === '/traineer')
    expect(record).toBeTruthy()
    expect(JSON.stringify(record.redirect)).toContain('pelamar')
  })
})

// v2.113.1 — audit menu "Laporan & Analisis": tiga tautan lama tetap hidup
// sebagai redirect ke tab Laporan di /cash (bookmark & tautan beredar tidak
// putus), tetapi tidak lagi tampil sebagai menu terpisah di sidebar.
// v2.113.2 — periode lama (`start_date`/`end_date`, `from`/`to`) dipetakan ke
// `start`/`end` yang dibaca context bar /cash; dulu periode bookmark hilang.
describe('tautan laporan lama', () => {
  it.each([
    ['rekap', 'rekap'],
    ['analytics', 'analisis'],
    ['expenses', 'realisasi'],
  ])('/%s dialihkan ke /cash tab Laporan (view %s)', (name, view) => {
    const record = router.getRoutes().find((r) => r.name === name)
    expect(record).toBeTruthy()
    expect(typeof record.redirect).toBe('function')
    expect(record.redirect({ query: { start: '2026-11-01' } })).toEqual({
      path: '/cash',
      query: { tab: 'laporan', view, start: '2026-11-01' },
    })
  })

  it('memetakan periode lama start_date/end_date dan from/to ke start/end', () => {
    const find = (name) => router.getRoutes().find((r) => r.name === name)
    expect(find('rekap').redirect({
      query: { start_date: '2026-11-01', end_date: '2026-11-30', driver: 'Budi' },
    })).toEqual({
      path: '/cash',
      query: {
        tab: 'laporan', view: 'rekap',
        start: '2026-11-01', end: '2026-11-30', driver: 'Budi',
      },
    })
    expect(find('expenses').redirect({
      query: { from: '2026-01-01', to: '2026-01-31' },
    }).query).toEqual({
      tab: 'laporan', view: 'realisasi', start: '2026-01-01', end: '2026-01-31',
    })
  })

  it('tab & view tidak bisa dibelokkan oleh query lama', () => {
    const record = router.getRoutes().find((r) => r.name === 'rekap')
    expect(record.redirect({ query: { tab: 'bbm', view: 'analisis' } }).query)
      .toMatchObject({ tab: 'laporan', view: 'rekap' })
  })
})
