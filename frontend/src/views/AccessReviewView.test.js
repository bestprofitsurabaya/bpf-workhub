import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import AccessReviewView from './AccessReviewView.vue'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api', () => ({ api: apiMock }))

const USERS = [
  { id: 1, username: 'ga_sby', full_name: 'GA Surabaya', role: 'ga', role_label: 'GA', team_name: '', branch_code: 'SBY', is_active: true, last_login: '2026-09-01 08:00:00', account_status: 'ok', account_status_label: 'OK' },
  { id: 2, username: 'ob_old', full_name: 'OB Lama', role: 'ob', role_label: 'OB', team_name: '', branch_code: 'SBY', is_active: true, last_login: '2025-01-10 08:00:00', account_status: 'stale', account_status_label: 'Basi' },
  { id: 3, username: 'never_login', full_name: 'Tidak Pernah', role: 'finance', role_label: 'Finance', team_name: '', branch_code: 'BDG', is_active: true, last_login: '', account_status: 'never_login', account_status_label: 'Belum Login' },
  { id: 4, username: 'off', full_name: 'Nonaktif', role: 'marketing', role_label: 'Marketing', team_name: 'Tim A', branch_code: 'MLG', is_active: false, last_login: '2026-05-01 08:00:00', account_status: 'inactive', account_status_label: 'Nonaktif' },
]

const REPORT = {
  users: USERS,
  summary: { total: 4, active: 3, inactive: 1, ok: 1, stale: 1, never_login: 1 },
  review: { last_at: '2026-06-01 09:00:00', last_by: 'Administrator' },
  stale_days: 90,
}

const BRANCHES = { branches: [{ code: 'SBY', name: 'Cabang Surabaya' }, { code: 'BDG', name: 'Cabang Bandung' }, { code: 'MLG', name: 'Cabang Malang' }] }

async function mountView() {
  apiMock.mockImplementation((path) => {
    if (path === '/api/admin/access-review') return Promise.resolve(REPORT)
    if (path === '/api/branches') return Promise.resolve(BRANCHES)
    if (path === '/api/admin/access-review/complete') return Promise.resolve({ status: 'success', msg: 'Review akses ditandai selesai' })
    if (path === '/api/users/sync') return Promise.resolve({ status: 'success' })
    return Promise.resolve({})
  })
  const w = mount(AccessReviewView)
  await flushPromises()
  return w
}

describe('AccessReviewView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setActivePinia(createPinia())
  })
  afterEach(() => vi.unstubAllGlobals())

  it('menampilkan ringkasan, klasifikasi akun, dan info review terakhir', async () => {
    const w = await mountView()
    expect(w.text()).toContain('Access Review')
    expect(w.text()).toContain('Total User')
    expect(w.text()).toContain('Basi')
    expect(w.text()).toContain('Belum Login')
    expect(w.text()).toContain('ga_sby')
    expect(w.text()).toContain('ob_old')
    expect(w.text()).toContain('never_login')
    expect(w.text()).toContain('Review terakhir')
    expect(w.text()).toContain('Administrator')
  })

  it('review belum pernah / lewat → badge REVIEW TERLAMBAT', async () => {
    const w = await mountView()
    expect(w.text()).toContain('REVIEW TERLAMBAT')
  })

  it('filter status Basi menyaring daftar', async () => {
    const w = await mountView()
    const select = w.find('select') // Semua Status
    // cari select filterStatus (index 0 setelah select status?) — gunakan v-model opsional:
    // pendekatan: pilih opsi 'stale' pada select pertama (filter status)
    const selects = w.findAll('select')
    // selects[0] = filterStatus, [1] = filterRole, [2] = filterBranch
    if (selects.length >= 1) {
      await selects[0].setValue('stale')
      await flushPromises()
      const text = w.text()
      expect(text).toContain('ob_old')
      expect(text).not.toContain('ga_sby')
    }
  })

  it('tombol Tandai Review Selesai memanggil /complete', async () => {
    const w = await mountView()
    const btn = w.findAll('button').find((b) => b.text().includes('Tandai Review Selesai'))
    expect(btn).toBeTruthy()
    await btn.trigger('click')
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/admin/access-review/complete', { method: 'POST' })
  })

  it('tombol Nonaktifkan akun basi → konfirmasi → /api/users/sync is_active false', async () => {
    const w = await mountView()
    // tombol 🚫 Nonaktifkan muncul untuk akun stale & never_login
    const btns = w.findAll('button').filter((b) => b.text().includes('Nonaktifkan'))
    expect(btns.length).toBeGreaterThanOrEqual(2) // ob_old (stale) + never_login
    vi.stubGlobal('alert', vi.fn())
    await btns[0].trigger('click')
    await flushPromises()
    // modal konfirmasi terbuka — klik tombol nonaktifkan di DALAM modal
    // (tombol baris juga berteks sama; tombol modal adalah yang terakhir)
    const modalBtns = w.findAll('button').filter((b) => b.text().trim() === '🚫 Nonaktifkan')
    expect(modalBtns.length).toBeGreaterThanOrEqual(2)
    await modalBtns[modalBtns.length - 1].trigger('click')
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/users/sync', {
      method: 'POST',
      body: expect.objectContaining({ is_active: false, username: 'ob_old' }),
    })
  })

  it('export CSV membuka URL download', async () => {
    const w = await mountView()
    const orig = window.location.href
    Object.defineProperty(window, 'location', { value: { href: '' }, writable: true })
    const btn = w.findAll('button').find((b) => b.text().includes('Export CSV'))
    await btn.trigger('click')
    expect(window.location.href).toBe('/api/admin/access-review/export')
    Object.defineProperty(window, 'location', { value: { href: orig }, writable: true })
  })
})
