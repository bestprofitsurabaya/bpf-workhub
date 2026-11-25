import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import FirstWorkView from './FirstWorkView.vue'

const { apiMock, authMock } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  authMock: { role: 'traineer', user: { branch_name: 'Cabang Malang', branch_code: 'MLG' } },
}))
vi.mock('../api', () => ({ api: apiMock }))
vi.mock('../stores/auth', () => ({ useAuthStore: () => authMock }))

const DEMO_ROW = {
  tempat_lahir: 'Surabaya', tanggal_lahir: '1995-01-19',
  jenis_kelamin: 'Laki-laki', golongan_darah: 'O',
  alamat: 'Jl. Contoh No. 12', rt_rw: '03/04', kel_desa: 'Keputih',
  kecamatan: 'Sukolilo', agama: 'Islam', status_perkawinan: 'Belum Menikah',
  pekerjaan: 'Karyawan Swasta', kewarganegaraan: 'WNI',
  berlaku_hingga: 'SEUMUR HIDUP',
}

const ROWS = [
  {
    id: 7, registration_no: 'FW-20251111-0007', nama: 'Budi Santoso',
    nik: '3573010101990001', no_hp: '081234567890', pendidikan_norm: 'SMA',
    referrer_name: 'IFAH', submitted_at: '2026-11-11 09:00:00',
    status: 'submitted', status_label: 'Menunggu', ...DEMO_ROW,
  },
]

async function mountRole(role, { scope = 'MLG', branches, embedded = false } = {}) {
  authMock.role = role
  const forms = branches || [{
    branch_code: 'MLG', branch_name: 'Cabang Malang',
    form_path: '/app/first-work-form?cabang=MLG&t=tok-mlg',
  }]
  apiMock.mockImplementation((path) => {
    if (path === '/api/first-work') {
      return Promise.resolve({ data: ROWS, stats: { total: 1, submitted: 1 }, total: 1, page: 1, scope_branch: scope })
    }
    if (String(path).startsWith('/api/first-work/7')) {
      return Promise.resolve({ data: { ...ROWS[0], events: [] } })
    }
    if (path === '/api/first-work/meta') return Promise.resolve({ referrers: [] })
    // v2.97.1: tautan form butuh entri ber-token untuk cabang sesi; mock kosong
    // membuat tombol "Buka Form Publik" tidak pernah dirender.
    if (path === '/api/first-work/branch-forms') {
      return Promise.resolve({ branches: forms })
    }
    return Promise.resolve({})
  })
  const w = mount(FirstWorkView, {
    props: { embedded },
    global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
  })
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
  })

  it('role cabang tidak melihat filter cabang', async () => {
    const w = await mountRole('traineer')
    expect(w.find('select[aria-label="Filter cabang"]').exists()).toBe(false)
  })

  it('daftar & detail menampilkan 13 field demografi (Rilis B Task 2)', async () => {
    const w = await mountRole('traineer')
    // Ringkasan di tabel: tempat/tanggal lahir, jenis kelamin, golongan darah.
    expect(w.text()).toContain('Surabaya')
    expect(w.text()).toContain('1995-01-19')

    await w.findAll('button').find((b) => b.text() === 'Detail').trigger('click')
    await flushPromises()
    const detailText = w.text()
    for (const label of ['Tempat Lahir', 'Tanggal Lahir', 'Jenis Kelamin',
      'Golongan Darah', 'Alamat', 'RT/RW', 'Kel/Desa', 'Kecamatan', 'Agama',
      'Status Perkawinan', 'Pekerjaan', 'Kewarganegaraan', 'Berlaku Hingga']) {
      expect(detailText, label).toContain(label)
    }
    expect(detailText).toContain('Jl. Contoh No. 12')
    expect(detailText).toContain('SEUMUR HIDUP')
  })

  it('cabang terpilih ikut terbawa ke tautan ekspor CSV', async () => {
    const w = await mountRole('admin', {
      scope: null,
      branches: [
        { branch_code: 'SBY', branch_name: 'Surabaya' },
        { branch_code: 'MLG', branch_name: 'Cabang Malang' },
      ],
    })
    await w.find('select[aria-label="Filter cabang"]').setValue('SBY')
    const exportLink = w.findAll('a').find((a) => a.text().includes('Ekspor CSV'))
    expect(exportLink.attributes('href')).toContain('branch=SBY')
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

  // v2.118.2 — Admin Pusat (semua cabang) diminta memilih cabang, bukan
  // disuruh "muat ulang halaman" saat menekan Salin/QR.
  it('Admin Pusat tanpa cabang diminta memilih cabang (bukan "muat ulang")', async () => {
    const w = await mountRole('admin', {
      scope: null,
      branches: [
        { branch_code: 'SBY', branch_name: 'Surabaya', form_path: '/app/first-work-form?cabang=SBY&t=tok-sby' },
        { branch_code: 'MLG', branch_name: 'Cabang Malang', form_path: '/app/first-work-form?cabang=MLG&t=tok-mlg' },
      ],
    })
    expect(labels(w)).not.toContain('🔗 Salin Link')
    expect(labels(w)).not.toContain('▦ QR')
    expect(w.text()).toContain('Pilih cabang untuk tautan form')
    expect(w.text()).not.toContain('muat ulang halaman')
  })

  it('Admin Pusat memilih cabang → tautan form mengikuti cabang itu', async () => {
    const w = await mountRole('admin', {
      scope: null,
      branches: [
        { branch_code: 'SBY', branch_name: 'Surabaya', form_path: '/app/first-work-form?cabang=SBY&t=tok-sby' },
        { branch_code: 'MLG', branch_name: 'Cabang Malang', form_path: '/app/first-work-form?cabang=MLG&t=tok-mlg' },
      ],
    })
    await w.find('select[aria-label="Filter cabang"]').setValue('MLG')
    await flushPromises()
    const link = w.findAll('a').find((a) => a.text().includes('Buka Form Publik'))
    expect(link).toBeTruthy()
    expect(link.attributes('href')).toContain('cabang=MLG')
  })

  it('embedded menyembunyikan PageHeader beserta tombol aksinya', async () => {
    const normal = await mountRole('traineer')
    expect(normal.find('.page-header').exists()).toBe(true)
    expect(labels(normal)).toContain('↗ Buka Form Publik')
    normal.unmount()

    const embedded = await mountRole('traineer', { embedded: true })
    expect(embedded.find('.page-header').exists()).toBe(false)
    expect(labels(embedded)).not.toContain('↗ Buka Form Publik')
    expect(embedded.text()).toContain('Budi Santoso')
    embedded.unmount()
  })
})
