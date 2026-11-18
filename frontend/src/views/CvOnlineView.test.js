import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import CvOnlineView from './CvOnlineView.vue'

const { apiMock, authMock } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  authMock: { role: 'traineer', user: { branch_name: 'Cabang Malang', branch_code: 'MLG' } },
}))
vi.mock('../api', () => ({ api: apiMock }))
vi.mock('../stores/auth', () => ({ useAuthStore: () => authMock }))

const ROWS = [
  {
    id: 7, registration_no: 'CV-MLG-261117-001', nama: 'Budi Santoso',
    tempat_lahir: 'Surabaya', tanggal_lahir: '1995-01-19',
    user_ef: 'EF 1', domisili: 'JAWA TIMUR', no_hp: '081234567890',
    no_hp_norm: '081234567890', pendidikan_terakhir: 'S1',
    pengalaman_status: 'sudah', pengalaman_lama: '1 - 2 Tahun',
    submitted_at: '2026-11-17 09:00:00', status: 'submitted',
  },
]

async function mountRole(role) {
  authMock.role = role
  apiMock.mockImplementation((path) => {
    if (path === '/api/cv-online') {
      return Promise.resolve({
        data: ROWS, stats: { total: 1, submitted: 1 }, total: 1, page: 1,
        scope_branch: 'MLG',
      })
    }
    if (path === '/api/cv-online/meta') {
      return Promise.resolve({ options: { user: ['EF 1', 'EF 2'] } })
    }
    if (path === '/api/cv-online/branch-forms') {
      return Promise.resolve({
        data: [{
          branch_code: 'MLG', branch_name: 'Cabang Malang',
          form_path: '/app/cv-online-form?cabang=MLG&t=tok-mlg',
        }],
      })
    }
    return Promise.resolve({})
  })
  const w = mount(CvOnlineView)
  await flushPromises()
  return w
}

function labels(w) {
  return w.findAll('button, a').map((el) => el.text())
}

describe('CvOnlineView (Registrasi CV Online)', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('traineer melihat data & tautan form publik', async () => {
    const w = await mountRole('traineer')
    const txt = w.text()
    expect(txt).toContain('Budi Santoso')
    expect(txt).toContain('Menunggu')
    expect(txt).toContain('CV-MLG-261117-001')
    expect(labels(w)).toContain('↗ Buka Form Publik')
    const link = w.findAll('a').find((a) => a.text().includes('Buka Form Publik'))
    expect(link.attributes('href')).toContain('/app/cv-online-form')
  })

  it('ga_hr hanya melihat (tanpa tombol form/verifikasi)', async () => {
    const w = await mountRole('ga_hr')
    expect(w.text()).toContain('Budi Santoso')
    expect(w.text()).toContain('GA/HR')
    expect(labels(w)).not.toContain('↗ Buka Form Publik')
  })

  it('menampilkan chip status & statistik antrean', async () => {
    const w = await mountRole('traineer')
    expect(w.text()).toContain('Menunggu')
    expect(w.text()).toContain('Terverifikasi')
    expect(w.text()).toContain('Hari Ini')
  })
})
