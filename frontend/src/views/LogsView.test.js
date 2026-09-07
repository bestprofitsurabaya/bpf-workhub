import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import LogsView from './LogsView.vue'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api', () => ({ api: apiMock }))

const now = new Date()
const LOGS = [
  { id: 1, action: 'approve_ga', user_type: 'ga', user_name: 'GA1', created_at: now.toISOString(), transaction_id: 1, ip_address: '1.1.1.1' },
  { id: 2, action: 'payout', user_type: 'finance', user_name: 'FIN1', created_at: new Date(now.getTime() - 864e5).toISOString(), transaction_id: 2, ip_address: '2.2.2.2' },
  { id: 3, action: 'approve_ga', user_type: 'ga', user_name: 'GA2', created_at: now.toISOString(), transaction_id: 3, ip_address: '3.3.3.3' },
]

describe('LogsView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMock.mockResolvedValue(LOGS)
  })

  it('merender seluruh log + badge hari ini & total', async () => {
    const w = mount(LogsView)
    await flushPromises()
    expect(w.text()).toContain('GA1')
    expect(w.text()).toContain('FIN1')
    expect(w.text()).toContain('Approve Ga') // label aksi dibersihkan
    expect(w.text()).toContain('Hari ini: 2')
    expect(w.text()).toContain('Total: 3 / 3')
  })

  it('filter aksi menyaring baris dan memperbarui badge total', async () => {
    const w = mount(LogsView)
    await flushPromises()
    const select = w.findAll('select')[1] // [0]=Cabang, [1]=Aksi, [2]=Peran
    await select.setValue('approve_ga')
    expect(w.findAll('tbody tr').length).toBe(2)
    expect(w.text()).toContain('Total: 2 / 3')
  })

  it('filter peran menyaring baris', async () => {
    const w = mount(LogsView)
    await flushPromises()
    const selects = w.findAll('select')
    await selects[2].setValue('finance')
    expect(w.findAll('tbody tr').length).toBe(1)
    expect(w.text()).toContain('FIN1')
  })

  it('menampilkan pesan kosong saat tidak ada log', async () => {
    apiMock.mockResolvedValue([])
    const w = mount(LogsView)
    await flushPromises()
    expect(w.text()).toContain('Tidak ada data dengan filter ini.')
  })
})

describe('LogsView — detail snapshot (v2.37.3)', () => {
  const DETAIL = {
    id: 1,
    action: 'water_purchase_delete',
    user_type: 'finance',
    user_name: 'FIN1',
    created_at: '2026-09-07T13:00:00',
    transaction_id: null,
    ip_address: '2.2.2.2',
    branch_code: 'SBY',
    old_data: { display_id: 'WTR-SBY-20260907-0016', status: 'verified', items: [{ brand: 'AQUA', quantity: 3 }] },
    new_data: null,
    user_agent: 'Mozilla/5.0 E2E',
  }

  beforeEach(() => {
    vi.clearAllMocks()
    // Setiap GET /api/audit-logs/<id> → detail dgn id yang sesuai.
    apiMock.mockImplementation((path) => {
      if (path.startsWith('/api/audit-logs/')) {
        return Promise.resolve({ ...DETAIL, id: Number(path.split('/').pop()) })
      }
      return Promise.resolve(LOGS)
    })
  })

  it('klik 🔍 memuat & menampilkan snapshot old_data + new_data', async () => {
    const w = mount(LogsView)
    await flushPromises()
    await w.findAll('button').find((b) => b.text() === '🔍').trigger('click')
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/audit-logs/1')
    expect(w.text()).toContain('Data Lama')
    expect(w.text()).toContain('WTR-SBY-20260907-0016')
  })

  it('kunci detail mengikuti entri yang diklik (bukan selalu id pertama)', async () => {
    const w = mount(LogsView)
    await flushPromises()
    // entri kedua (id=2) → GET /api/audit-logs/2
    const btns = w.findAll('button').filter((b) => b.text() === '🔍')
    await btns[1].trigger('click')
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/audit-logs/2')
    expect(w.text()).toContain('Detail Log #2')
  })

  it('entri tanpa snapshot menampilkan pesan', async () => {
    apiMock.mockImplementation((path) => {
      if (path === '/api/audit-logs/1') return Promise.resolve({ ...LOGS[0], old_data: null, new_data: null })
      return Promise.resolve(LOGS)
    })
    const w = mount(LogsView)
    await flushPromises()
    await w.findAll('button').find((b) => b.text() === '🔍').trigger('click')
    await flushPromises()
    expect(w.text()).toContain('tidak menyimpan snapshot')
  })

  it('gagal memuat detail → pesan error di modal, list tetap utuh', async () => {
    apiMock.mockImplementation((path) => {
      if (path === '/api/audit-logs/1') return Promise.reject(new Error('DB error'))
      return Promise.resolve(LOGS)
    })
    const w = mount(LogsView)
    await flushPromises()
    await w.findAll('button').find((b) => b.text() === '🔍').trigger('click')
    await flushPromises()
    expect(w.text()).toContain('DB error')
    expect(w.text()).toContain('GA1') // list tetap tampil
  })

  it('tombol tutup menutup modal detail', async () => {
    const w = mount(LogsView)
    await flushPromises()
    await w.findAll('button').find((b) => b.text() === '🔍').trigger('click')
    await flushPromises()
    expect(w.text()).toContain('Data Lama')
    await w.findAll('button').find((b) => b.text() === 'Tutup').trigger('click')
    expect(w.text()).not.toContain('Data Lama')
  })
})
