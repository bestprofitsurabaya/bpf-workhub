import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import AdminDashboard from './AdminDashboard.vue'
import { useAuthStore } from '../../stores/auth'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../../api', () => ({ api: apiMock }))

const STATS = { pending: 3, verified_ga: 2, os_finance: 1, archived: 5, today_tx: 2, today_nominal: 100000 }

const TX = (id, status, anomaly = false) => ({
  id, display_id: `BPF-${id}`, driver_name: `DRV${id}`, nopol: 'L 1 AB', bbm_type: 'PERTALITE',
  nominal: 150000, liter: 15, odo_km: 1000, ml_anomaly_flag: anomaly, created_at: '2026-08-11 10:00:00', status,
})

const DETAIL = (id) => ({
  id, display_id: `BPF-${id}`, driver_name: `DRV${id}`, nopol: 'L 1 AB', vehicle_type: 'AVANZA',
  bbm_type: 'PERTALITE', nominal: 150000, liter: 15, price_per_liter: 10000, odo_km: 1000,
  km_per_liter: 10, spbu_type: 'rekanan', status: 'pending', ml_anomaly_flag: false,
  is_mypertamina_error: false, rejection_reason: null, gps_address: 'Jl. Test', jumlah_appointment: 0,
  created_at: '2026-08-11 10:00:00', photos: [{ label: 'Struk', url: '/uploads/STRUK_1.jpg' }],
})

const CROSS = { health_score: 85, budget_usage_percent: 30, odo_diff: 120, flags: [], recommendation: 'AMAN', avg_3months: { avg_kml: 10, tx_count: 5 } }

function mockApi() {
  apiMock.mockImplementation((path, opts = {}) => {
    if (path === '/api/stats') return Promise.resolve(STATS)
    if (path === '/api/queue') {
      const tab = opts.params?.tab || 'ga'
      if (tab === 'ga') return Promise.resolve([TX(1, 'pending'), TX(2, 'pending')])
      if (tab === 'finance') return Promise.resolve([TX(3, 'verified_ga')])
      return Promise.resolve([TX(4, 'os_finance')])
    }
    if (path.startsWith('/api/transactions/detail/')) {
      const id = Number(path.split('/').pop())
      return Promise.resolve(DETAIL(id))
    }
    if (path.startsWith('/api/cross-check/')) return Promise.resolve(CROSS)
    return Promise.resolve({ status: 'success', msg: 'ok' })
  })
}

async function mountWith(role) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore()
  auth.user = { role, full_name: 'User ' + role, user_name: role }
  mockApi()
  const w = mount(AdminDashboard, {
    global: {
      plugins: [pinia],
      stubs: { 'router-link': { template: '<a><slot /></a>' } },
    },
  })
  await flushPromises()
  await flushPromises()
  return w
}

const btnByText = (w, text) => w.findAll('button').find((b) => b.text() === text)
const confirmYes = async (w) => {
  const btn = btnByText(w, 'Ya, lanjutkan')
  expect(btn).toBeTruthy()
  await btn.trigger('click')
  await flushPromises()
}

describe('AdminDashboard', () => {
  beforeEach(() => { vi.clearAllMocks();  })
  afterEach(() => { vi.unstubAllGlobals() })

  it('role ga melihat kartu statistik GA + antrean GA dengan tombol aksi', async () => {
    const w = await mountWith('ga')
    expect(w.text()).toContain('Klaim menunggu verifikasi GA')
    expect(w.text()).toContain('Antrean Kerja')
    expect(w.text()).toContain('BPF-1')
    expect(btnByText(w, '✅ Setujui')).toBeTruthy()
    expect(btnByText(w, '❌ Tolak')).toBeTruthy()
  })

  it('role finance melihat kartu finance + tab Finance & Konfirmasi Driver (bukan GA)', async () => {
    const w = await mountWith('finance')
    expect(w.text()).toContain('Klaim siap dicairkan Finance')
    expect(w.text()).not.toContain('Klaim menunggu verifikasi GA')
    expect(w.text()).toContain('💰 Finance')
    expect(w.text()).toContain('🤝 Konfirmasi Driver')
  })

  it('klik Approve (✅) memanggil /api/queue/approve-ga/<id>', async () => {
    const w = await mountWith('ga')
    await btnByText(w, '✅ Setujui').trigger('click')
    await flushPromises()
    await confirmYes(w)
    expect(apiMock).toHaveBeenCalledWith('/api/queue/approve-ga/1', { method: 'POST' })
  })

  it('klik Tolak (❌) meminta alasan lalu memanggil /api/queue/reject/<id>', async () => {
    const w = await mountWith('ga')
    await btnByText(w, '❌ Tolak').trigger('click')
    await flushPromises()
    await w.find('textarea').setValue('alasan uji')
    await btnByText(w, 'Tolak klaim').trigger('click')
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/queue/reject/1', { method: 'POST', body: { reason: 'alasan uji' } })
  })

  it('role finance: tab Finance tombol Cairkan (💰) memanggil /api/queue/payout', async () => {
    const w = await mountWith('finance')
    await w.findAll('button').find((b) => b.text().includes('💰 Finance')).trigger('click')
    await flushPromises()
    await flushPromises()
    expect(w.text()).toContain('BPF-3')
    await btnByText(w, '💰 Cairkan').trigger('click')
    await flushPromises()
    await confirmYes(w)
    expect(apiMock).toHaveBeenCalledWith('/api/queue/payout/3', { method: 'POST' })
  })

  it('role finance: tab Konfirmasi Driver tombol Arsipkan (📦) memanggil /api/queue/archive', async () => {
    const w = await mountWith('finance')
    await w.findAll('button').find((b) => b.text().includes('Konfirmasi Driver')).trigger('click')
    await flushPromises()
    await flushPromises()
    expect(w.text()).toContain('BPF-4')
    await btnByText(w, '📦 Arsipkan').trigger('click')
    await flushPromises()
    await confirmYes(w)
    expect(apiMock).toHaveBeenCalledWith('/api/queue/archive/4', { method: 'POST' })
  })

  it('transaksi ber-flag anomali ML tidak bisa di-approve cepat — tersedia tombol 🛡 Verifikasi (langsung di SPA)', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const auth = useAuthStore()
    auth.user = { role: 'ga', full_name: 'GA', user_name: 'ga' }
    apiMock.mockImplementation((path, opts = {}) => {
      if (path === '/api/stats') return Promise.resolve(STATS)
      if (path === '/api/queue') return Promise.resolve([TX(9, 'pending', true)])
      if (path.startsWith('/api/transactions/detail/')) return Promise.resolve({ ...DETAIL(9), ml_anomaly_flag: true })
      if (path.startsWith('/api/cross-check/')) return Promise.resolve(CROSS)
      return Promise.resolve({ status: 'success', msg: 'ok' })
    })
    const w = mount(AdminDashboard, {
      global: { plugins: [pinia], stubs: { 'router-link': { template: '<a><slot /></a>' } } },
    })
    await flushPromises()
    await flushPromises()
    // Tanpa tautan klasik: tombol approve cepat TIDAK muncul, diganti verifikasi dari SPA
    expect(w.text()).not.toContain('Wajib klasik')
    expect(btnByText(w, '✅ Setujui')).toBeFalsy()
    expect(btnByText(w, '🛡 Verifikasi')).toBeTruthy()
  })

  it('klik tombol 🛡 Verifikasi di baris membuka modal langsung ke form verifikasi anomali', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const auth = useAuthStore()
    auth.user = { role: 'ga', full_name: 'GA', user_name: 'ga' }
    apiMock.mockImplementation((path, opts = {}) => {
      if (path === '/api/stats') return Promise.resolve(STATS)
      if (path === '/api/queue') return Promise.resolve([TX(10, 'pending', true)])
      if (path.startsWith('/api/transactions/detail/')) return Promise.resolve({ ...DETAIL(10), ml_anomaly_flag: true })
      if (path.startsWith('/api/cross-check/')) return Promise.resolve(CROSS)
      return Promise.resolve({ status: 'success', msg: 'ok' })
    })
    const w = mount(AdminDashboard, {
      global: { plugins: [pinia], stubs: { 'router-link': { template: '<a><slot /></a>' } } },
    })
    await flushPromises(); await flushPromises()
    await btnByText(w, '🛡 Verifikasi').trigger('click')
    await flushPromises(); await flushPromises()
    expect(w.text()).toContain('🛡 Verifikasi Mendalam (Anomali ML)')
    expect(btnByText(w, '✅ Simpan Verifikasi')).toBeTruthy()
  })

  it('klik Detail (👁) membuka modal dengan foto & cross-check, lalu aksi Approve dari modal', async () => {
    const w = await mountWith('ga')
    await btnByText(w, '👁 Detail').trigger('click')
    await flushPromises()
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/transactions/detail/1')
    expect(apiMock).toHaveBeenCalledWith('/api/cross-check/1')
    expect(w.text()).toContain('Foto Bukti')
    expect(w.text()).toContain('Health Score')
    expect(w.text()).toContain('85')
    await btnByText(w, '✅ Setujui').trigger('click')
    await flushPromises()
    await confirmYes(w)
    expect(apiMock).toHaveBeenCalledWith('/api/queue/approve-ga/1', { method: 'POST' })
  })

  it('role admin melihat tombol Hapus (🗑 Hapus) di modal yang memanggil /api/queue/delete', async () => {
    const w = await mountWith('admin')
    await btnByText(w, '👁 Detail').trigger('click')
    await flushPromises()
    await flushPromises()
    await btnByText(w, '🗑 Hapus').trigger('click')
    await flushPromises()
    await confirmYes(w)
    expect(apiMock).toHaveBeenCalledWith('/api/queue/delete/1', { method: 'POST' })
  })

  it('P2: kartu Perlu Tindakan membuka tab antrean terkait', async () => {
    const w = await mountWith('admin')
    expect(w.text()).toContain('Perlu Tindakan Hari Ini')
    const card = w.findAll('.action-card').find((b) => b.text().includes('Klaim siap dicairkan Finance'))
    expect(card).toBeTruthy()
    await card.trigger('click')
    await flushPromises()
    await flushPromises()
    expect(w.text()).toContain('BPF-3')
  })

  it('P2: tabel antrean diringkas menjadi 6 kolom tanpa ODO/liter', async () => {
    const w = await mountWith('ga')
    const heads = w.find('#antrean-kerja thead').findAll('th')
    expect(heads.length).toBe(6)
    expect(w.find('#antrean-kerja thead').text()).not.toContain('ODO')
    expect(w.find('#antrean-kerja thead').text()).not.toContain('Liter')
  })

  it('transaksi anomali: modal menampilkan 🛡 Verifikasi Anomali — tanpa konfirmasi tidak mengirim API', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const auth = useAuthStore()
    auth.user = { role: 'ga', full_name: 'GA', user_name: 'ga' }
    apiMock.mockImplementation((path, opts = {}) => {
      if (path === '/api/stats') return Promise.resolve(STATS)
      if (path === '/api/queue') return Promise.resolve([{ ...TX(7, 'pending', true) }])
      if (path.startsWith('/api/transactions/detail/')) return Promise.resolve({ ...DETAIL(7), ml_anomaly_flag: true })
      if (path.startsWith('/api/cross-check/')) return Promise.resolve(CROSS)
      return Promise.resolve({ status: 'success', msg: 'ok' })
    })
    const fetchMock = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({ status: 'success', msg: 'ok' }) }))
    vi.stubGlobal('fetch', fetchMock)
    const w = mount(AdminDashboard, {
      global: { plugins: [pinia], stubs: { 'router-link': { template: '<a><slot /></a>' } } },
    })
    await flushPromises(); await flushPromises()
    await btnByText(w, '👁 Detail').trigger('click')
    await flushPromises(); await flushPromises()
    // Tombol approve cepat TIDAK muncul untuk anomali; ada tombol verifikasi khusus
    expect(btnByText(w, '✅ Setujui')).toBeFalsy()
    await btnByText(w, '🛡 Verifikasi Anomali').trigger('click')
    await flushPromises()
    await btnByText(w, '✅ Simpan Verifikasi').trigger('click')
    await flushPromises()
    expect(fetchMock).not.toHaveBeenCalled()
    expect(w.text()).toContain('Centang konfirmasi')
  })

  it('verifikasi anomali dengan konfirmasi mengirim FormData ke /api/queue/verify/<id>', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const auth = useAuthStore()
    auth.user = { role: 'ga', full_name: 'GA', user_name: 'ga' }
    apiMock.mockImplementation((path, opts = {}) => {
      if (path === '/api/stats') return Promise.resolve(STATS)
      if (path === '/api/queue') return Promise.resolve([{ ...TX(8, 'pending', true) }])
      if (path.startsWith('/api/transactions/detail/')) return Promise.resolve({ ...DETAIL(8), ml_anomaly_flag: true })
      if (path.startsWith('/api/cross-check/')) return Promise.resolve(CROSS)
      return Promise.resolve({ status: 'success', msg: 'ok' })
    })
    const fetchMock = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({ status: 'success', msg: 'ok' }) }))
    vi.stubGlobal('fetch', fetchMock)
    const w = mount(AdminDashboard, {
      global: { plugins: [pinia], stubs: { 'router-link': { template: '<a><slot /></a>' } } },
    })
    await flushPromises(); await flushPromises()
    await btnByText(w, '👁 Detail').trigger('click')
    await flushPromises(); await flushPromises()
    await btnByText(w, '🛡 Verifikasi Anomali').trigger('click')
    await flushPromises()
    await w.find('input[type="checkbox"]').setValue(true)
    await btnByText(w, '✅ Simpan Verifikasi').trigger('click')
    await flushPromises(); await flushPromises()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, opts] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/queue/verify/8')
    expect(opts.method).toBe('POST')
    expect(opts.body).toBeInstanceOf(FormData)
  })

  it('Edit (✏️ Edit) membuka form perbaikan dan mengirim /api/queue/modify/<id>', async () => {
    const w = await mountWith('ga')
    await btnByText(w, '👁 Detail').trigger('click')
    await flushPromises(); await flushPromises()
    await btnByText(w, '✏️ Edit').trigger('click')
    await flushPromises()
    expect(w.text()).toContain('Perbaiki Data Transaksi')
    await btnByText(w, '💾 Simpan Perubahan').trigger('click')
    await flushPromises()
    const call = apiMock.mock.calls.find(([p]) => p.startsWith('/api/queue/modify/'))
    expect(call).toBeTruthy()
    expect(call[0]).toBe('/api/queue/modify/1')
    expect(call[1].method).toBe('POST')
    expect(call[1].body.nominal).toBe(150000)
    expect(call[1].body.odo_km).toBe(1000)
  })

  it('tombol Unverify muncul untuk status verified_ga dan memanggil /api/queue/unverify', async () => {
    const w = await mountWith('ga')
    // baris ke-2 dibuat verified_ga via detail modal dengan status override
    apiMock.mockImplementation((path, opts = {}) => {
      if (path === '/api/stats') return Promise.resolve(STATS)
      if (path === '/api/queue') return Promise.resolve([{ ...TX(5, 'verified_ga') }])
      if (path.startsWith('/api/transactions/detail/')) return Promise.resolve({ ...DETAIL(5), status: 'verified_ga' })
      if (path.startsWith('/api/cross-check/')) return Promise.resolve(CROSS)
      return Promise.resolve({ status: 'success', msg: 'ok' })
    })
    await btnByText(w, '👁 Detail').trigger('click')
    await flushPromises()
    await flushPromises()
    await btnByText(w, '↩️ Unverify').trigger('click')
    await flushPromises()
    await confirmYes(w)
    expect(apiMock).toHaveBeenCalledWith('/api/queue/unverify/5', { method: 'POST' })
  })
})
