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

// v2.113.0 — Registrasi CV Online: halaman data hanya untuk traineer/GA-HR/admin,
// form publik di path terpisah dan tanpa login.
describe('path Registrasi CV Online', () => {
  it('/cv-online menampilkan halaman data untuk traineer, ga_hr, admin', () => {
    const route = router.resolve('/cv-online')
    expect(route.name).toBe('cv-online')
    expect(route.meta.roles).toEqual(['traineer', 'ga_hr', 'admin'])
  })

  it('form publik punya path sendiri dan tetap tanpa login', () => {
    const route = router.resolve('/cv-online-form')
    expect(route.name).toBe('cv-online-form')
    expect(route.meta.public).toBe(true)
  })
})

// Rilis A (Task 6) — dashboard kasus rekrutmen untuk staff.
describe('path Dashboard kasus rekrutmen', () => {
  it('/recruitment-cases hanya untuk traineer, ga_hr, admin', () => {
    const route = router.resolve('/recruitment-cases')
    expect(route.name).toBe('recruitment-cases')
    expect(route.meta.roles).toEqual(['traineer', 'ga_hr', 'admin'])
    expect(route.meta.public).toBeFalsy()
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
