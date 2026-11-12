import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import FirstWorkView from './FirstWorkView.vue'

const { apiMock, authMock } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  authMock: { role: 'traineer', user: { branch_name: 'Cabang Malang', branch_code: 'MLG' } },
}))
vi.mock('../api', () => ({ api: apiMock }))
vi.mock('../stores/auth', () => ({ useAuthStore: () => authMock }))

const ROWS = [
  {
    id: 7, registration_no: 'FW-20251111-0007', nama: 'Budi Santoso',
    nik: '3573010101990001', no_hp: '081234567890', pendidikan_norm: 'SMA',
    referrer_name: 'IFAH', submitted_at: '2026-11-11 09:00:00',
    status: 'submitted', status_label: 'Menunggu',
  },
]

async function mountRole(role) {
  authMock.role = role
  apiMock.mockImplementation((path) => {
    if (path === '/api/first-work') {
      return Promise.resolve({ data: ROWS, stats: { total: 1, submitted: 1 }, total: 1, page: 1, scope_branch: 'MLG' })
    }
    if (path === '/api/first-work/meta') return Promise.resolve({ referrers: [] })
    // v2.97.1: tautan form butuh entri ber-token untuk cabang sesi; mock kosong
    // membuat tombol "Buka Form Publik" tidak pernah dirender.
    if (path === '/api/first-work/branch-forms') {
      return Promise.resolve({
        branches: [{
          branch_code: 'MLG', branch_name: 'Cabang Malang',
          form_path: '/app/first-work-form?cabang=MLG&t=tok-mlg',
        }],
      })
    }
    return Promise.resolve({})
  })
  const w = mount(FirstWorkView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
  await flushPromises()
  return w
}

function labels(w) {
  return w.findAll('button, a').map((el) => el.text())
}

describe('FirstWorkView (Absensi FirstWork)', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('traineer melihat data & tautan form publik (path form, bukan halaman data)', async () => {
    const w = await mountRole('traineer')
    const txt = w.text()
    expect(txt).toContain('Budi Santoso')
    expect(txt).toContain('Menunggu')
    expect(labels(w)).toContain('↗ Buka Form Publik')
    expect(labels(w)).toContain('🔗 Salin Link')
    const link = w.findAll('a').find((a) => a.text().includes('Buka Form Publik'))
    expect(link.attributes('href')).toContain('/app/first-work-form')
  })

  it('admin juga melihat data & tautan form publik', async () => {
    const w = await mountRole('admin')
    expect(w.text()).toContain('Budi Santoso')
    expect(labels(w)).toContain('↗ Buka Form Publik')
  })

  for (const role of ['finance', 'ga_hr']) {
    it(`${role} hanya melihat data — tanpa tautan form`, async () => {
      const w = await mountRole(role)
      const txt = w.text()
      expect(txt).toContain('Budi Santoso')
      expect(txt).toContain('hanya lihat')
      expect(labels(w)).not.toContain('↗ Buka Form Publik')
      expect(labels(w)).not.toContain('🔗 Salin Link')
      expect(w.findAll('a').some((a) => (a.attributes('href') || '').includes('first-work-form'))).toBe(false)
    })
  }
})
