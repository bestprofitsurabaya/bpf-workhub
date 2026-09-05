import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import GaDashboard from './GaDashboard.vue'
import { useStepupStore } from '../../stores/stepup'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../../api', () => ({ api: apiMock }))

const STATS = { pending: 3, verified_ga: 2, os_finance: 1, archived: 5, today_tx: 4, today_nominal: 1500000 }
const QUEUE = [
  { id: 5, display_id: 'BBM-001', driver_name: 'RIVAN', nopol: 'L 1', nominal: 100000, ml_anomaly_flag: 0 },
  { id: 6, display_id: 'BBM-002', driver_name: 'BUDI', nopol: 'L 2', nominal: 200000, ml_anomaly_flag: 1 },
]
const CASH = [
  { status: 'DRAFT', total_amount: 150000 },
  { status: 'DRAFT', total_amount: 100000 },
  { status: 'GA_APPROVED', total_amount: 75000 },
]
const TRIPS = [{ id: 1 }, { id: 2 }, { id: 3 }]

async function mountView() {
  apiMock.mockImplementation((path) => {
    if (path === '/api/stats') return Promise.resolve(STATS)
    if (path.startsWith('/api/queue')) return Promise.resolve(QUEUE)
    if (path === '/api/cash/history') return Promise.resolve(CASH)
    if (path.startsWith('/api/trips')) return Promise.resolve({ data: TRIPS })
    return Promise.resolve({ status: 'success' })
  })
  const w = mount(GaDashboard)
  await flushPromises()
  return w
}

describe('GaDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setActivePinia(createPinia())
  })
  afterEach(() => vi.unstubAllGlobals())

  it('menampilkan kartu statistik & kasbon menunggu approve GA', async () => {
    const w = await mountView()
    expect(w.text()).toContain('Antrean GA')
    expect(w.text()).toContain('Verified GA')
    expect(w.text()).toContain('3')
    expect(w.text()).toContain('Rp 250.000') // 150.000 + 100.000 DRAFT
  })

  it('menampilkan antrean klaim & laporan perjalanan pending', async () => {
    const w = await mountView()
    expect(w.text()).toContain('BBM-001')
    expect(w.text()).toContain('RIVAN')
    expect(w.text()).toContain('L 1')
    expect(w.text()).toContain('3') // trips pending
    expect(w.text()).toContain('⚠️ ML')
  })

  it('approve memanggil /api/queue/approve-ga setelah konfirmasi', async () => {
    const w = await mountView()
    vi.stubGlobal('confirm', vi.fn(() => true))
    await w.findAll('button').find((b) => b.text().includes('Approve')).trigger('click')
    await flushPromises()
    expect(global.confirm).toHaveBeenCalled()
    expect(apiMock).toHaveBeenCalledWith('/api/queue/approve-ga/5', { method: 'POST' })
  })

  it('approve ditolak 428 STEPUP_REQUIRED: modal PIN terbuka, lalu retry setelah PIN', async () => {
    const w = await mountView()
    vi.stubGlobal('confirm', vi.fn(() => true))
    const stepup = useStepupStore()

    // Percobaan approve pertama ditolak server (belum ada grant step-up)
    const stepupErr = new Error('Verifikasi PIN ulang diperlukan untuk aksi ini.')
    stepupErr.status = 428
    stepupErr.data = { code: 'STEPUP_REQUIRED', msg: stepupErr.message }
    apiMock
      .mockRejectedValueOnce(stepupErr)                 // approve-ga → 428
      .mockResolvedValueOnce({ status: 'success' })     // /api/step-up → sukses

    await w.findAll('button').find((b) => b.text().includes('Approve')).trigger('click')
    await flushPromises()

    // Modal step-up terbuka; aksi belum di-retry
    expect(stepup.open).toBe(true)
    const approveCallsBefore = apiMock.mock.calls.filter(([p]) => p === '/api/queue/approve-ga/5')
    expect(approveCallsBefore.length).toBe(1)

    // User memasukkan PIN → grant diterbitkan → approve di-retry otomatis
    await stepup.submit('123456')
    await flushPromises()

    expect(apiMock).toHaveBeenCalledWith('/api/step-up', { method: 'POST', body: { pin: '123456' } })
    const approveCalls = apiMock.mock.calls.filter(([p]) => p === '/api/queue/approve-ga/5')
    expect(approveCalls.length).toBe(2) // 428 lalu retry sukses
    expect(stepup.open).toBe(false)
  })

  it('klaim ber-flag anomali punya tombol Verifikasi (bukan Approve)', async () => {
    const w = await mountView()
    const rows = w.findAll('tbody tr')
    const flagRow = rows.find((r) => r.text().includes('BBM-002'))
    const btnTexts = flagRow.findAll('button').map((b) => b.text())
    expect(btnTexts.some((t) => t.includes('Verifikasi'))).toBe(true)
    expect(btnTexts.some((t) => t.includes('Approve'))).toBe(false)
  })

  it('verifikasi anomali: wajib centang konfirmasi sebelum kirim', async () => {
    const w = await mountView()
    const rows = w.findAll('tbody tr')
    await rows.find((r) => r.text().includes('BBM-002')).findAll('button').find((b) => b.text().includes('Verifikasi')).trigger('click')
    await flushPromises()
    expect(w.text()).toContain('Saya sudah memeriksa foto bukti')
    const submitBtn = w.findAll('button').find((b) => b.text().includes('Verifikasi & Setujui'))
    expect(submitBtn.attributes('disabled')).toBeDefined() // belum centang
    await w.find('input[type="checkbox"]').setValue(true)
    await submitBtn.trigger('click')
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/queue/verify/6', {
      method: 'POST',
      body: expect.objectContaining({ confirm_anomaly: '1' }),
    })
  })

  it('tolak: tombol terkunci tanpa alasan, lalu mengirim alasan', async () => {
    const w = await mountView()
    await w.findAll('button').find((b) => b.text().includes('Tolak')).trigger('click')
    await flushPromises()
    expect(w.text()).toContain('Alasan penolakan')
    const submitBtn = w.findAll('button').find((b) => b.text().includes('Tolak & Kirim'))
    expect(submitBtn.attributes('disabled')).toBeDefined() // alasan wajib
    const ta = w.find('textarea')
    await ta.setValue('Foto tidak sesuai')
    await submitBtn.trigger('click')
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/queue/reject/5', {
      method: 'POST',
      body: expect.objectContaining({ reason: 'Foto tidak sesuai' }),
    })
  })
})
