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
