import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import RecruitmentCasesView from './RecruitmentCasesView.vue'

const { apiMock, authMock } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  authMock: { role: 'traineer', user: { full_name: 'Petugas', branch_code: 'MLG' } },
}))
vi.mock('../api', () => ({ api: apiMock }))
vi.mock('../stores/auth', () => ({ useAuthStore: () => authMock }))

const CASES = [
  {
    case_id: 'RC-a1b2c3d4e5f6',
    nik_masked: '****0001',
    nama: 'Andi Saputra',
    first_branch: 'SBY',
    status: 'AKTIF',
    branches: [
      { branch_code: 'JKT', first_seen_at: '2026-11-21 11:00:00', last_seen_at: '2026-11-21 11:00:00' },
      { branch_code: 'SBY', first_seen_at: '2026-11-20 10:00:00', last_seen_at: '2026-11-21 09:00:00' },
    ],
    steps: [
      { id: 11, step_type: 'CV', status: 'SELESAI', branch_code: 'SBY', exception_reason: '', completed_at: '2026-11-20 10:05:00' },
      { id: 12, step_type: 'TRAINING', status: 'PENDING', branch_code: 'JKT', exception_reason: '', completed_at: null },
      { id: 13, step_type: 'TKD', status: 'BELUM', branch_code: 'JKT', exception_reason: '', completed_at: null },
      { id: 14, step_type: 'FIRSTWORK', status: 'DIKECUALIKAN', branch_code: 'JKT', exception_reason: 'Tidak hadir', completed_at: '2026-11-21 11:00:00' },
    ],
  },
]

let caseCalls
let postCalls

async function mountRole(role = 'traineer') {
  authMock.role = role
  caseCalls = []
  postCalls = []
  apiMock.mockImplementation((path, opts = {}) => {
    if (path === '/api/recruitment/cases') {
      caseCalls.push(opts.params || {})
      return Promise.resolve({ data: CASES })
    }
    if (String(path).startsWith('/api/recruitment/steps/')) {
      postCalls.push({ path, opts })
      return Promise.resolve({ status: 'success' })
    }
    return Promise.resolve({})
  })
  const w = mount(RecruitmentCasesView)
  await flushPromises()
  return w
}

async function openDetail(w) {
  const detailBtn = w.findAll('button').find((b) => b.text() === 'Detail')
  expect(detailBtn).toBeTruthy()
  await detailBtn.trigger('click')
  await flushPromises()
}

describe('RecruitmentCasesView (Dashboard kasus staff)', () => {
  beforeEach(() => { vi.clearAllMocks() })
  afterEach(() => { vi.unstubAllGlobals() })

  it('menampilkan daftar kasus dengan NIK termasker saja (tanpa NIK penuh)', async () => {
    const w = await mountRole()
    const txt = w.text()

    expect(txt).toContain('RC-a1b2c3d4e5f6')
    expect(txt).toContain('****0001')
    expect(txt).toContain('Andi Saputra')
    expect(txt).toContain('SBY')
    expect(txt).toContain('AKTIF')
    expect(txt).not.toContain('3573010101990001')
  })

  it('filter NIK/nama, cabang, dan status dikirim ke API dengan nama parameter yang benar', async () => {
    const w = await mountRole()

    await w.find('input[aria-label="Cari NIK atau nama"]').setValue('3573 0101 0199 0001')
    await w.find('select[aria-label="Filter cabang"]').setValue('SBY')
    await w.find('select[aria-label="Filter status"]').setValue('AKTIF')
    await w.find('form').trigger('submit')
    await flushPromises()

    expect(caseCalls.at(-1)).toEqual({
      nik: '3573 0101 0199 0001', branch_code: 'SBY', status: 'AKTIF',
    })
  })

  it('detail menampilkan empat kolom langkah, status/cabang tiap langkah, dan riwayat cabang', async () => {
    const w = await mountRole()
    await openDetail(w)
    const txt = w.text()

    for (const type of ['CV', 'TRAINING', 'TKD', 'FIRSTWORK']) {
      expect(w.find(`.rc-step-col[data-step-type="${type}"]`).exists()).toBe(true)
    }
    expect(txt).toContain('PENDING')
    expect(txt).toContain('BELUM')
    expect(txt).toContain('Tidak hadir')
    expect(txt).toContain('Cabang asal: SBY')
    expect(txt).toContain('Cabang saat ini: JKT')
    expect(txt).toContain('SBY')
  })

  it('tombol exception hanya untuk langkah BELUM/PENDING dan hanya untuk staff', async () => {
    const w = await mountRole('traineer')
    await openDetail(w)

    const buttons = w.findAll('button[data-step-type]')
    expect(buttons.map((b) => b.attributes('data-step-type'))).toEqual(['TRAINING', 'TKD'])

    for (const role of ['ga_hr', 'admin']) {
      const staff = await mountRole(role)
      await openDetail(staff)
      expect(staff.findAll('button[data-step-type]').length).toBe(2)
    }

    const nonStaff = await mountRole('finance')
    await openDetail(nonStaff)
    expect(nonStaff.findAll('button[data-step-type]').length).toBe(0)
  })

  it('exception mengirim alasan via prompt lalu memuat ulang daftar kasus', async () => {
    const prompt = vi.fn(() => 'Tidak memenuhi syarat')
    vi.stubGlobal('prompt', prompt)
    const w = await mountRole()
    await openDetail(w)

    await w.find('button[data-step-type="TRAINING"]').trigger('click')

    expect(prompt).toHaveBeenCalled()
    expect(postCalls).toEqual([{
      path: '/api/recruitment/steps/12/exception',
      opts: { method: 'POST', body: { reason: 'Tidak memenuhi syarat' } },
    }])
    // POST sukses → daftar dimuat ulang agar status/langkah terlihat segar.
    expect(caseCalls.length).toBe(2)
  })

  it('exception dibatalkan bila alasan kosong', async () => {
    vi.stubGlobal('prompt', vi.fn(() => '   '))
    const w = await mountRole()
    await openDetail(w)

    await w.find('button[data-step-type="TKD"]').trigger('click')

    expect(postCalls).toEqual([])
    expect(caseCalls.length).toBe(1)
    expect(w.text()).toContain('Alasan wajib diisi')
  })

  it('form bukti hanya untuk TRAINING/TKD, bisa dibuka dan ditutup', async () => {
    const w = await mountRole()
    await openDetail(w)

    const toggles = w.findAll('button[data-evidence-step]')
    expect(toggles.map((b) => b.attributes('data-evidence-step'))).toEqual(['s12', 's13'])
    expect(w.find('[data-evidence-form="s12"]').exists()).toBe(false)

    await w.find('button[data-evidence-step="s12"]').trigger('click')
    expect(w.find('[data-evidence-form="s12"]').exists()).toBe(true)
    expect(w.find('button[data-evidence-step="s12"]').text()).toContain('Tutup bukti')

    await w.find('button[data-evidence-step="s12"]').trigger('click')
    expect(w.find('[data-evidence-form="s12"]').exists()).toBe(false)
  })

  it('form bukti mengirim POST evidence lengkap lalu memuat ulang daftar', async () => {
    const w = await mountRole()
    await openDetail(w)
    await w.find('button[data-evidence-step="s12"]').trigger('click')
    const form = w.find('[data-evidence-form="s12"]')

    await form.find('input[type="date"]').setValue('2026-11-24')
    await form.find('textarea').setValue('Lulus pelatihan')
    await form.find('input[data-field="file_url"]').setValue('https://x/bukti.pdf')
    await form.find('input[data-field="score"]').setValue('88')
    await form.find('button[data-save-evidence]').trigger('click')
    await flushPromises()

    expect(postCalls).toEqual([{
      path: '/api/recruitment/steps/12/evidence',
      opts: {
        method: 'POST',
        body: {
          date: '2026-11-24', note: 'Lulus pelatihan',
          file_url: 'https://x/bukti.pdf', score: '88',
        },
      },
    }])
    expect(caseCalls.length).toBe(2)
    expect(w.text()).toContain('Bukti berhasil disimpan')
  })

  it('bukti tanpa tanggal ditolak di sisi klien tanpa POST', async () => {
    const w = await mountRole()
    await openDetail(w)
    await w.find('button[data-evidence-step="s13"]').trigger('click')
    const form = w.find('[data-evidence-form="s13"]')
    await form.find('textarea').setValue('Catatan tanpa tanggal')

    await form.find('button[data-save-evidence]').trigger('click')
    await flushPromises()

    expect(postCalls).toEqual([])
    expect(caseCalls.length).toBe(1)
    expect(w.text()).toContain('Tanggal bukti wajib diisi')
  })

  it('langkah TRAINING/TKD yang belum ada tetap punya form bukti (lazy create)', async () => {
    const original = CASES[0].steps
    CASES[0].steps = original.filter((s) => s.step_type !== 'TKD')
    try {
      const w = await mountRole()
      await openDetail(w)
      const key = 'mRC-a1b2c3d4e5f6|TKD'
      expect(w.find(`button[data-evidence-step="${key}"]`).exists()).toBe(true)

      await w.find(`button[data-evidence-step="${key}"]`).trigger('click')
      const form = w.find(`[data-evidence-form="${key}"]`)
      await form.find('input[type="date"]').setValue('2026-11-24')
      await form.find('textarea').setValue('Ujian TKD selesai')
      await form.find('button[data-save-evidence]').trigger('click')
      await flushPromises()

      expect(postCalls).toEqual([{
        path: '/api/recruitment/steps/0/evidence',
        opts: {
          method: 'POST',
          body: {
            date: '2026-11-24', note: 'Ujian TKD selesai',
            case_id: 'RC-a1b2c3d4e5f6', step_type: 'TKD',
          },
        },
      }])
      expect(caseCalls.length).toBe(2)
    } finally {
      CASES[0].steps = original
    }
  })

  it('form bukti tidak muncul untuk non-staff', async () => {
    const w = await mountRole('finance')
    await openDetail(w)

    expect(w.findAll('button[data-evidence-step]').length).toBe(0)
  })
})
