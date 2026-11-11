import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ReceptionistView from './ReceptionistView.vue'

const { apiMock, authMock } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  authMock: { role: 'receptionist', user: { branch_name: 'Cabang Malang', branch_code: 'MLG' } },
}))
vi.mock('../../api', () => ({ api: apiMock }))
vi.mock('../../stores/auth', () => ({ useAuthStore: () => authMock }))
vi.mock('../../stores/realtime', () => ({
  useRealtimeStore: () => ({ receptionistSeq: 0 }),
}))
vi.mock('../../stores/stepup', () => ({
  useStepupStore: () => ({
    open: false, label: '', busy: false, err: '',
    require: (fn) => fn(),
    submit: vi.fn(),
    cancel: vi.fn(),
  }),
}))

const APPLICANTS = [
  {
    id: 1, display_id: 'PLM-0001', nama_lengkap: 'Andi Wijaya', pendidikan: 'SMA',
    no_hp: '081234567890', upline: 'BELA', user_field: 'TEAM A', posisi: 'STAFF',
    interview_at: '2026-11-01 09:00:00', status: 'interview',
    verified_by: 'receptionist_sby',
    attendance: { interview: { attended_at: '2026-11-01 09:05:00' } },
  },
]

async function mountView(role, { ho = false } = {}) {
  authMock.role = role
  authMock.isHoAdmin = ho
  authMock.user = role === 'traineer'
    ? { branch_name: 'Cabang Malang', branch_code: 'MLG' }
    : { branch_name: 'Cabang Surabaya', branch_code: 'SBY' }
  const rows = ho
    ? [
        { ...APPLICANTS[0], branch_code: 'SBY', branch_name: 'Cabang Surabaya' },
        { ...APPLICANTS[0], id: 2, display_id: 'PLM-0002', nama_lengkap: 'Budi Santoso', branch_code: 'MLG', branch_name: 'Cabang Malang' },
      ]
    : APPLICANTS
  const branches = ho
    ? [{ code: 'SBY', name: 'Cabang Surabaya' }, { code: 'MLG', name: 'Cabang Malang' }]
    : []
  const branchSummary = ho
    ? [
        { code: 'SBY', name: 'Cabang Surabaya', total: 3023, interview: 2384, training: 613, lulus: 0, resigned: 26, rejected: 0, first_work_pending: 1831 },
        { code: 'MLG', name: 'Cabang Malang', total: 0, interview: 0, training: 0, lulus: 0, resigned: 0, rejected: 0, first_work_pending: 0 },
      ]
    : []
  apiMock.mockImplementation((path) => {
    if (path === '/api/applicants') {
      return Promise.resolve({ data: rows, stats: { total: rows.length, interview: rows.length }, scope_branch: ho ? null : 'MLG', aggregate: ho, branches, branch_summary: branchSummary })
    }
    if (path === '/api/applicants/meta') {
      return Promise.resolve({ uplines: ['BELA'], users: ['TEAM A'], user_options: [{ id: 1, name: 'TEAM A' }], statuses: [], branches })
    }
    if (path === '/api/receptionist/realtime-sync') return Promise.resolve({ synced: false })
    return Promise.resolve({ status: 'success', msg: 'ok' })
  })
  const w = mount(ReceptionistView, {
    global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
  })
  await flushPromises()
  return w
}

describe('ReceptionistView (Rekrutmen)', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('receptionist melihat tombol pengelolaan & kolom aksi', async () => {
    const w = await mountView('receptionist')
    const txt = w.text()
    expect(txt).toContain('Rekrutmen')
    expect(txt).toContain('Andi Wijaya')
    expect(txt).toContain('Aksi')
    for (const label of ['Sync Sheet', 'Input Pelamar', 'Kelola User', 'Laporan PDF']) {
      expect(w.findAll('button, a').some((el) => el.text().includes(label))).toBe(true)
    }
    expect(apiMock).toHaveBeenCalledWith('/api/receptionist/realtime-sync', { method: 'POST' })
  })

  it('traineer hanya melihat data (tanpa tombol pengelolaan)', async () => {
    const w = await mountView('traineer')
    const txt = w.text()
    expect(txt).toContain('Mode lihat saja')
    expect(txt).toContain('Andi Wijaya')
    expect(txt).not.toContain('Aksi')
    for (const label of ['Sync Sheet', 'Input Pelamar', 'Kelola User', 'Laporan PDF']) {
      expect(w.findAll('button, a').some((el) => el.text().includes(label))).toBe(false)
    }
    // tombol aksi baris (edit/verifikasi/kehadiran/hapus) tidak dirender
    expect(w.findAll('button').some((b) => ['✏️', '✅', '🎯', '🚪', '🏁', '🧑‍💼', '✕', '🗑'].includes(b.text()))).toBe(false)
    // traineer tidak memicu sync realtime receptionist (endpoint terlarang)
    expect(apiMock).not.toHaveBeenCalledWith('/api/receptionist/realtime-sync', { method: 'POST' })
  })

  it('admin pusat melihat agregat semua cabang (tanpa aksi tulis)', async () => {
    const w = await mountView('admin', { ho: true })
    const txt = w.text()
    expect(txt).toContain('Mode agregat semua cabang')
    expect(txt).toContain('Cabang')
    // kolom cabang + kedua baris cabang tampil
    expect(txt).toContain('SBY')
    expect(txt).toContain('Cabang Malang')
    expect(txt).toContain('Budi Santoso')
    // tetap read-only di tampilan agregat
    expect(txt).not.toContain('Aksi')
    for (const label of ['Sync Sheet', 'Input Pelamar', 'Kelola User', 'Laporan PDF']) {
      expect(w.findAll('button, a').some((el) => el.text().includes(label))).toBe(false)
    }
  })

  it('admin pusat melihat ringkasan per cabang (pelamar & antrean FirstWork)', async () => {
    const w = await mountView('admin', { ho: true })
    const txt = w.text()
    expect(txt).toContain('Ringkasan per cabang')
    expect(txt).toContain('3.023')
    expect(txt).toContain('1.831')
    const rows = w.findAll('.sum-row')
    expect(rows.length).toBe(2)
    expect(rows[0].text()).toContain('SBY')
  })

  it('klik baris ringkasan cabang memfilter daftar pelamar', async () => {
    const w = await mountView('admin', { ho: true })
    const row = w.findAll('.sum-row').find((r) => r.text().includes('MLG'))
    await row.trigger('click')
    await flushPromises()
    const call = apiMock.mock.calls.filter((c) => c[0] === '/api/applicants').pop()
    expect(call[1].params.branch).toBe('MLG')
  })

  it('admin pusat bisa memfilter satu cabang', async () => {
    const w = await mountView('admin', { ho: true })
    const select = w.findAll('select').find((s) => s.text().includes('Semua cabang'))
    await select.setValue('MLG')
    await flushPromises()
    const call = apiMock.mock.calls.filter((c) => c[0] === '/api/applicants').pop()
    expect(call[1].params.branch).toBe('MLG')
  })

  it('filter pencarian dikirim sebagai parameter API', async () => {
    const w = await mountView('receptionist')
    const input = w.find('input[placeholder="Ketik lalu Enter…"]')
    await input.setValue('andi')
    await input.trigger('keyup.enter')
    await flushPromises()
    const call = apiMock.mock.calls.filter((c) => c[0] === '/api/applicants').pop()
    expect(call[1].params.search).toBe('andi')
  })
})
