import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore, ROLE_META } from './auth'

describe('ROLE_META (ISO/IEC 27001 — hak akses per peran)', () => {
  it('memetakan setiap role ke home dashboard masing-masing', () => {
    expect(ROLE_META.admin.home).toBe('/dashboard')
    expect(ROLE_META.ga.home).toBe('/ga')
    expect(ROLE_META.finance.home).toBe('/finance')
    expect(ROLE_META.marketing.home).toBe('/marketing')
    expect(ROLE_META.chief_driver.home).toBe('/chief-driver')
  })

  it('semua role memiliki label, warna dan ikon', () => {
    for (const meta of Object.values(ROLE_META)) {
      expect(meta.label).toBeTruthy()
      expect(meta.color).toBeTruthy()
      expect(meta.icon).toBeTruthy()
    }
  })
})

describe('useAuthStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('menyediakan aksi yang dipakai LoginView (kontrak anti-regresi)', () => {
    // Regresi 27 Agu 2026: aksi login hilang dari store (refactor username
    // per-cabang) tapi LoginView tetap memanggil auth.login() → runtime error
    // "login is not a function". Test ini gagal di unit-test bila aksi hilang.
    const auth = useAuthStore()
    expect(typeof auth.login).toBe('function')
    expect(typeof auth.bootstrap).toBe('function')
    expect(typeof auth.logout).toBe('function')
  })

  it('login menyimpan user + csrf token', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true, status: 200,
      json: async () => ({ status: 'success', user: { role: 'ga', user_name: 'ga1', full_name: 'GA Satu' }, csrf_token: 'tok123' }),
    })
    const auth = useAuthStore()
    const d = await auth.login('ga1', '1234')
    expect(auth.user.role).toBe('ga')
    expect(auth.role).toBe('ga')
    expect(auth.isAuthenticated).toBe(true)
    expect(auth.meta.label).toBe('GA Officer')
    expect(localStorage.getItem('bpf_csrf')).toBe('tok123')
    expect(d.user.full_name).toBe('GA Satu')
  })

  it('bootstrap pulihkan sesi dari /api/auth/me', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true, status: 200,
      json: async () => ({ authenticated: true, user: { role: 'admin', user_name: 'admin' }, csrf_token: 't' }),
    })
    const auth = useAuthStore()
    const ok = await auth.bootstrap()
    expect(ok).toBe(true)
    expect(auth.role).toBe('admin')
  })

  it('bootstrap tanpa sesi -> tidak terautentikasi', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true, status: 200,
      json: async () => ({ authenticated: false, csrf_token: 't' }),
    })
    const auth = useAuthStore()
    expect(await auth.bootstrap()).toBe(false)
    expect(auth.isAuthenticated).toBe(false)
  })

  it('logout membersihkan user & csrf token', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({}) })
    const auth = useAuthStore()
    auth.user = { role: 'finance', user_name: 'fin' }
    localStorage.setItem('bpf_csrf', 'x')
    await auth.logout()
    expect(auth.isAuthenticated).toBe(false)
    expect(localStorage.getItem('bpf_csrf')).toBeNull()
  })
})
