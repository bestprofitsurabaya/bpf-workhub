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
