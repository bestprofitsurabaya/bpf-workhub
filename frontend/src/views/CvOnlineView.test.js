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

async function mountRole(role, { scope = 'MLG', branches } = {}) {
  authMock.role = role
  const forms = branches || [{
    branch_code: 'MLG', branch_name: 'Cabang Malang',
    form_path: '/app/cv-online-form?cabang=MLG&t=tok-mlg',
  }]
  apiMock.mockImplementation((path) => {
    if (path === '/api/cv-online') {
      return Promise.resolve({
        data: ROWS, stats: { total: 1, submitted: 1 }, total: 1, page: 1,
        scope_branch: scope,
      })
    }
    if (path === '/api/cv-online/meta') {
      return Promise.resolve({ options: { user: ['EF 1', 'EF 2'] } })
    }
    if (path === '/api/cv-online/branch-forms') {
      return Promise.resolve({ data: forms })
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

  // v2.115.0 — register lintas cabang: Admin Pusat bisa memilih cabang.
  it('Admin Pusat melihat filter Semua cabang + pilihan cabang', async () => {
    const w = await mountRole('admin', {
      scope: null,
      branches: [
        { branch_code: 'SBY', branch_name: 'Surabaya' },
        { branch_code: 'MLG', branch_name: 'Cabang Malang' },
      ],
    })
    const select = w.find('select[aria-label="Filter cabang"]')
    expect(select.exists()).toBe(true)
    expect(select.text()).toContain('Semua cabang')
    expect(select.text()).toContain('SBY')
    expect(select.text()).toContain('MLG')
  })

  it('role cabang tidak melihat filter cabang (tetap terkunci)', async () => {
    const w = await mountRole('traineer')
    expect(w.find('select[aria-label="Filter cabang"]').exists()).toBe(false)
  })

  it('cabang terpilih ikut terbawa ke tautan ekspor CSV', async () => {
    const w = await mountRole('admin', {
      scope: null,
      branches: [
        { branch_code: 'SBY', branch_name: 'Surabaya' },
        { branch_code: 'MLG', branch_name: 'Cabang Malang' },
      ],
    })
    await w.find('select[aria-label="Filter cabang"]').setValue('MLG')
    const exportLink = w.findAll('a').find((a) => a.text().includes('Ekspor CSV'))
    expect(exportLink.attributes('href')).toContain('branch=MLG')
  })

  it('menampilkan chip status & statistik antrean', async () => {
    const w = await mountRole('traineer')
    expect(w.text()).toContain('Menunggu')
    expect(w.text()).toContain('Terverifikasi')
    expect(w.text()).toContain('Hari Ini')
  })

  // v2.118.2 — Admin Pusat tidak punya satu cabang sesi; jangan tampilkan
  // tombol tautan yang lalu memunculkan "muat ulang halaman" yang menyesatkan.
  it('Admin Pusat tanpa cabang diminta memilih cabang (bukan "muat ulang")', async () => {
    const w = await mountRole('admin', {
      scope: null,
      branches: [
        { branch_code: 'SBY', branch_name: 'Surabaya', form_path: '/app/cv-online-form?cabang=SBY&t=tok-sby' },
        { branch_code: 'MLG', branch_name: 'Cabang Malang', form_path: '/app/cv-online-form?cabang=MLG&t=tok-mlg' },
      ],
    })
    expect(labels(w)).not.toContain('🔗 Salin Link')
    expect(w.text()).toContain('Pilih cabang untuk tautan form')
    expect(w.text()).not.toContain('muat ulang halaman')
  })

  it('Admin Pusat memilih cabang → tautan form mengikuti cabang itu', async () => {
    const w = await mountRole('admin', {
      scope: null,
      branches: [
        { branch_code: 'SBY', branch_name: 'Surabaya', form_path: '/app/cv-online-form?cabang=SBY&t=tok-sby' },
        { branch_code: 'MLG', branch_name: 'Cabang Malang', form_path: '/app/cv-online-form?cabang=MLG&t=tok-mlg' },
      ],
    })
    await w.find('select[aria-label="Filter cabang"]').setValue('MLG')
    await flushPromises()
    const link = w.findAll('a').find((a) => a.text().includes('Buka Form Publik'))
    expect(link).toBeTruthy()
    expect(link.attributes('href')).toContain('cabang=MLG')
  })
})
