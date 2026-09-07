import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import WaterView from './WaterView.vue'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api', () => ({ api: apiMock }))
vi.mock('../stores/auth', () => ({
  useAuthStore: () => ({ role: 'finance' }),
}))
vi.mock('../stores/stepup', () => ({
  useStepupStore: () => ({
    open: false, label: '', busy: false, err: '',
    require: (fn) => fn(),
    submit: vi.fn(),
    cancel: vi.fn(),
  }),
}))

// Status fitur edit/hapus (v2.37.0) — default nonaktif; test masing-masing
// mengubah via mock api di bawah.
let editEnabled = false

const TYPES = [
  { id: 1, name: 'Gelas', brands: [{ id: 1, type_id: 1, brand: 'VIT' }] },
  { id: 2, name: 'Botol', brands: [{ id: 2, type_id: 2, brand: 'Le Minerale' }] },
  { id: 3, name: 'Galon', brands: [{ id: 3, type_id: 3, brand: 'AQUA' }] },
]
const PURCHASES = [
  { id: 1, display_id: 'WTR-20260812-0001', ob_name: 'BUDI', purchase_date: '2026-08-12', status: 'pending', created_at: '2026-08-12T09:30:00', items: [{ drink_type: 'Galon', brand: 'AQUA', satuan: 'galon', quantity: 3 }] },
  { id: 2, display_id: 'WTR-20260812-0002', ob_name: 'SITI', purchase_date: '2026-08-12', status: 'verified', created_at: '2026-08-12T10:00:00', items: [{ drink_type: 'Botol', brand: 'Le Minerale', satuan: 'dus', quantity: 2 }], remark: 'OK', verified_by: 'RINA' },
]

async function mountView() {
  apiMock.mockImplementation((path, opts) => {
    if (path === '/api/water/brands') return Promise.resolve({ types: TYPES, brands: [] })
    if (path === '/api/water/purchases') {
      // v2.37.4: backend kirim { purchases, range, filters }
      return Promise.resolve({ purchases: PURCHASES, range: {}, filters: {} })
    }
    if (path === '/api/water/edit-enabled') return Promise.resolve({ enabled: editEnabled })
    if (path.startsWith('/api/water/purchases/')) return Promise.resolve(PURCHASES[0])
    return Promise.resolve({ status: 'success' })
  })
  const w = mount(WaterView)
  await flushPromises()
  return w
}

describe('WaterView', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('menampilkan daftar pengajuan dengan status', async () => {
    const w = await mountView()
    expect(w.text()).toContain('WTR-20260812-0001')
    expect(w.text()).toContain('WTR-20260812-0002')
    expect(w.text()).toContain('Menunggu Verifikasi')
    expect(w.text()).toContain('Terverifikasi')
  })

  it('finance melihat tombol verifikasi & tolak untuk pengajuan pending', async () => {
    const w = await mountView()
    const btns = w.findAll('button').map((b) => b.text())
    expect(btns).toContain('✅ Verifikasi')
    expect(btns).toContain('✖ Tolak')
    expect(btns).toContain('📄 PDF')
  })

  it('finance melihat master merk per tipe', async () => {
    const w = await mountView()
    expect(w.text()).toContain('Master Merk Air Minum')
    expect(w.text()).toContain('AQUA')
    expect(w.text()).toContain('Le Minerale')
  })

  it('detail menampilkan remark verifikasi (pengajuan terverifikasi)', async () => {
    apiMock.mockImplementation((path) => {
      if (path === '/api/water/brands') return Promise.resolve({ types: TYPES, brands: [] })
      if (path === '/api/water/purchases') return Promise.resolve({ purchases: PURCHASES, range: {}, filters: {} })
      if (path === '/api/water/purchases/2') return Promise.resolve(PURCHASES[1])
      return Promise.resolve(PURCHASES[0])
    })
    const w = mount(WaterView)
    await flushPromises()
    // Buka detail pengajuan TERVERIFIKASI (indeks 1) — punya remark
    const detailBtns = w.findAll('button').filter((b) => b.text() === '👁️ Detail')
    await detailBtns[1].trigger('click')
    await flushPromises()
    expect(w.text()).toContain('Remark')
    expect(w.text()).toContain('OK')
  })

  it('fitur nonaktif: tidak ada tombol edit/hapus', async () => {
    editEnabled = false
    const w = await mountView()
    const btns = w.findAll('button').map((b) => b.text())
    expect(btns).not.toContain('✏️ Edit')
    expect(btns).not.toContain('🗑️')
  })

  it('fitur aktif: tombol edit & hapus tampil untuk pending & verified', async () => {
    editEnabled = true
    const w = await mountView()
    const btns = w.findAll('button').map((b) => b.text())
    expect(btns).toContain('✏️ Edit')
    expect(btns.filter((t) => t === '🗑️').length).toBe(PURCHASES.length)
  })

  it('modal edit membuka form terisi & PUT ke endpoint edit', async () => {
    editEnabled = true
    const w = await mountView()
    await w.findAll('button').find((b) => b.text() === '✏️ Edit').trigger('click')
    await flushPromises()
    expect(w.text()).toContain('Edit Pengajuan')
    await w.findAll('button').find((b) => b.text() === '💾 Simpan Perubahan').trigger('click')
    await flushPromises()
    const putCall = apiMock.mock.calls.find((c) => c[0] === '/api/water/purchases/1' && c[1]?.method === 'PUT')
    expect(putCall).toBeTruthy()
    expect(putCall[1].body.items[0]).toEqual(expect.objectContaining({ brand: 'AQUA', quantity: 3 }))
  })

  it('hapus memanggil DELETE dengan konfirmasi', async () => {
    vi.stubGlobal('confirm', vi.fn(() => true))
    editEnabled = true
    const w = await mountView()
    await w.findAll('button').find((b) => b.text() === '🗑️').trigger('click')
    await flushPromises()
    expect(global.confirm).toHaveBeenCalled()
    expect(apiMock).toHaveBeenCalledWith('/api/water/purchases/1', { method: 'DELETE' })
    vi.unstubAllGlobals()
  })
})

describe('WaterView — bukti foto di verifikasi (v2.37.2)', () => {
  const DETAIL_FOTO = {
    ...PURCHASES[0],
    foto_before: 'WTR_BEFORE_TEST_1.jpeg',
    foto_after: 'WTR_AFTER_TEST_1.jpeg',
  }

  function mockWithFoto() {
    apiMock.mockImplementation((path) => {
      if (path === '/api/water/brands') return Promise.resolve({ types: TYPES, brands: [] })
      if (path === '/api/water/purchases') return Promise.resolve(PURCHASES)
      if (path === '/api/water/purchases/1') return Promise.resolve(DETAIL_FOTO)
      return Promise.resolve({ status: 'success' })
    })
  }

  async function openVerify(w) {
    await w.findAll('button').find((b) => b.text() === '✅ Verifikasi').trigger('click')
    await flushPromises()
  }

  beforeEach(() => { vi.clearAllMocks() })

  it('modal verifikasi menampilkan bukti foto sebelum & sesudah diisi', async () => {
    mockWithFoto()
    const w = mount(WaterView)
    await flushPromises()
    await openVerify(w)
    expect(w.find('img[alt="Bukti sebelum diisi"]').exists()).toBe(true)
    expect(w.find('img[alt="Bukti sesudah diisi"]').exists()).toBe(true)
  })

  it('openVerify menarik detail via GET /api/water/purchases/<id>', async () => {
    mockWithFoto()
    const w = mount(WaterView)
    await flushPromises()
    await openVerify(w)
    expect(apiMock).toHaveBeenCalledWith('/api/water/purchases/1')
  })

  it('klik bukti foto membuka lightbox perbesar, ✖ menutupnya', async () => {
    mockWithFoto()
    const w = mount(WaterView)
    await flushPromises()
    await openVerify(w)
    expect(w.find('img[alt="Preview bukti"]').exists()).toBe(false)
    await w.find('img[alt="Bukti sebelum diisi"]').trigger('click')
    expect(w.find('img[alt="Preview bukti"]').exists()).toBe(true)
    await w.findAll('button').find((b) => b.text() === '✖ Tutup').trigger('click')
    expect(w.find('img[alt="Preview bukti"]').exists()).toBe(false)
  })

  it('detail pengajuan: foto bisa diklik untuk perbesar', async () => {
    mockWithFoto()
    const w = mount(WaterView)
    await flushPromises()
    await w.findAll('button').find((b) => b.text() === '👁️ Detail').trigger('click')
    await flushPromises()
    expect(w.find('img[alt="Sebelum"]').exists()).toBe(true)
    await w.find('img[alt="Sebelum"]').trigger('click')
    expect(w.find('img[alt="Preview bukti"]').exists()).toBe(true)
  })

  it('gambar rusak → fallback "Foto gagal dimuat", bukan gambar kosong', async () => {
    mockWithFoto()
    const w = mount(WaterView)
    await flushPromises()
    await openVerify(w)
    const img = w.find('img[alt="Bukti sebelum diisi"]')
    await img.trigger('error')
    expect(w.text()).toContain('⚠️ Foto gagal dimuat')
    expect(w.find('img[alt="Bukti sebelum diisi"]').exists()).toBe(false)
  })

  it('detail gagal dimuat → verifikasi tetap bisa dibuka (foto tidak wajib)', async () => {
    apiMock.mockImplementation((path) => {
      if (path === '/api/water/brands') return Promise.resolve({ types: TYPES, brands: [] })
      if (path === '/api/water/purchases') return Promise.resolve({ purchases: PURCHASES, range: {}, filters: {} })
      if (path === '/api/water/purchases/1') return Promise.reject(new Error('db down'))
      return Promise.resolve({ status: 'success' })
    })
    const w = mount(WaterView)
    await flushPromises()
    await openVerify(w)
    expect(w.find('img[alt="Bukti sebelum diisi"]').exists()).toBe(false)
    expect(w.text()).toContain('Remark') // form verifikasi tetap tampil
  })
})

describe('WaterView — filter rentang tanggal (v2.37.4)', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('load awal mengirim rentang bulan berjalan + status all', async () => {
    const w = await mountView()
    const call = apiMock.mock.calls.find((c) => c[0] === '/api/water/purchases')
    expect(call).toBeTruthy()
    const p = call[1]?.params || {}
    const now = new Date()
    const first = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`
    expect(p.from).toBe(first)
    expect(p.status).toBe('all')
    // to = akhir bulan berjalan
    const last = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate()
    expect(p.to.endsWith(String(last).padStart(2, '0'))).toBe(true)
  })

  it('ganti rentang & status lalu Tampilkan → params ikut berubah', async () => {
    const w = await mountView()
    // @change="load" memicu loading=true → v-else unmounted sesaat; flush agar
    // filter bar kembali ter-mount sebelum mencari elemen berikutnya.
    const inputs = w.findAll('input[type="date"]')
    await inputs[0].setValue('2026-08-01'); await flushPromises()
    await inputs[1].setValue('2026-08-31'); await flushPromises()
    const sel = w.findAll('select')[0] // satu-satunya select saat modal tertutup
    await sel.setValue('pending'); await flushPromises()
    await w.findAll('button').find((b) => b.text() === '🔍 Tampilkan').trigger('click')
    await flushPromises()
    const calls = apiMock.mock.calls.filter((c) => c[0] === '/api/water/purchases')
    const last = calls[calls.length - 1]
    expect(last[1].params).toEqual({ from: '2026-08-01', to: '2026-08-31', status: 'pending', q: '' })
  })

  it('q terisi & Enter → pencarian dikirim ke backend', async () => {
    const w = await mountView()
    const qInput = w.findAll('input').find((i) => i.attributes('placeholder')?.includes('No. dokumen'))
    await qInput.setValue('AQUA')
    await qInput.trigger('keyup.enter')
    await flushPromises()
    const calls = apiMock.mock.calls.filter((c) => c[0] === '/api/water/purchases')
    expect(calls[calls.length - 1][1].params.q).toBe('AQUA')
  })

  it('tombol ↺ Bulan ini mengembalikan rentang default & memuat ulang', async () => {
    const w = await mountView()
    const inputs = w.findAll('input[type="date"]')
    await inputs[0].setValue('2026-01-01'); await flushPromises()
    await w.findAll('button').find((b) => b.text().includes('Bulan ini')).trigger('click')
    await flushPromises()
    const now = new Date()
    const first = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`
    const calls = apiMock.mock.calls.filter((c) => c[0] === '/api/water/purchases')
    expect(calls[calls.length - 1][1].params.from).toBe(first)
  })

  it('backend array (kompat lama) tetap dirender', async () => {
    apiMock.mockImplementation((path) => {
      if (path === '/api/water/brands') return Promise.resolve({ types: TYPES, brands: [] })
      if (path === '/api/water/purchases') return Promise.resolve(PURCHASES)
      return Promise.resolve({ status: 'success' })
    })
    const w = await mountView()
    expect(w.text()).toContain('WTR-20260812-0001')
  })
})
