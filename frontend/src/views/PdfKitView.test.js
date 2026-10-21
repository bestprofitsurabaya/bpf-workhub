import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import PdfKitView from './PdfKitView.vue'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api', () => ({ api: apiMock }))

const MODES = {
  status: 'ok',
  modes: [
    { key: 'lossless', label: 'Lossless (aman)', hint: 'Struktur dirapikan', needs_target: false },
    { key: 'ringan', label: 'Ringan — 150 dpi', hint: 'Untuk scan 300 dpi', needs_target: false },
    { key: 'target', label: 'Target ukuran (otomatis)', hint: 'Berhenti saat target', needs_target: true },
  ],
  limits: { max_files: 10, max_file_mb: 100, max_total_mb: 250 },
}

const DONE_ITEM = {
  name: 'scan_berat.pdf', size_before: 2_000_000, size_after: 500_000, ratio_pct: 75,
  pages: 3, mode_used: 'ringan', text_kept: null, status: 'done',
  note: 'Hemat 75% (mode ringan)', error: '',
  outputs: [{ file: 'scan_berat_kompres.pdf', size: 500_000, mode: 'ringan' }],
}

const DONE_JOB = {
  id: 'pk000001', mode: 'ringan', target_mb: 0, user: 'it_sby', status: 'done',
  stage: 'Selesai', progress: 100, created_at: 1700000000,
  saved_bytes: 1_500_000, ratio_pct: 75, items: [DONE_ITEM],
}

const PROTECTED_JOB = {
  ...DONE_JOB, id: 'pk000002', saved_bytes: 0, ratio_pct: 0,
  items: [{
    ...DONE_ITEM, name: 'Kuitansi_Air_Minum.pdf', status: 'protected', size_after: 0,
    outputs: [], note: 'Dokumen terbitan sistem (WTR-20260904-10300556) terdaftar di registri '
      + 'integritas — dikompres akan mematahkan verifikasi keaslian. Dilewati.',
  }],
}

function apiRouter(overrides = {}) {
  return vi.fn(async (path, opts = {}) => {
    const url = path.split('?')[0]
    const table = {
      '/api/pdfkit/modes': MODES,
      '/api/pdfkit/jobs': { jobs: [DONE_JOB] },
      ...overrides,
    }
    if (url in table) {
      const v = table[url]
      return typeof v === 'function' ? v(path, opts) : v
    }
    throw new Error(`unmocked api path: ${path}`)
  })
}

/** Set berkas pada <input type="file"> (happy-dom). */
async function pickFiles(w, files) {
  const input = w.find('input[type="file"]')
  Object.defineProperty(input.element, 'files', { value: files, configurable: true })
  await input.trigger('change')
  await flushPromises()
}

const pdfFile = (name, size = 1024) =>
  new File([new Uint8Array(size)], name, { type: 'application/pdf' })

beforeEach(() => {
  apiMock.mockImplementation(apiRouter())
  vi.useFakeTimers({ shouldAdvanceTime: true })
  vi.spyOn(document, 'createElement')
})
afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('PdfKitView — pilih berkas & mode', () => {
  it('submit nonaktif sebelum ada berkas', async () => {
    const w = mount(PdfKitView)
    await flushPromises()
    expect(w.find('button.btn-primary').attributes('disabled')).toBeDefined()
  })

  it('mode dari API dirender & bisa dipilih', async () => {
    const w = mount(PdfKitView)
    await flushPromises()
    const tombol = w.findAll('.mode')
    expect(tombol.length).toBe(3)
    expect(tombol[0].text()).toContain('Lossless')
    await tombol[1].trigger('click')
    expect(tombol[1].classes()).toContain('on')
    expect(tombol[0].classes()).not.toContain('on')
  })

  it('input target ukuran hanya muncul di mode target', async () => {
    const w = mount(PdfKitView)
    await flushPromises()
    expect(w.find('input[type="number"]').exists()).toBe(false)
    await w.findAll('.mode')[2].trigger('click')
    expect(w.find('input[type="number"]').exists()).toBe(true)
  })

  it('berkas bukan PDF ditolak, PDF diterima & tampil ukurannya', async () => {
    const w = mount(PdfKitView)
    await flushPromises()
    await pickFiles(w, [new File(['x'], 'catatan.txt', { type: 'text/plain' })])
    expect(w.find('.b-err').text()).toContain('bukan PDF')
    expect(w.findAll('.picked-row').length).toBe(0)

    await pickFiles(w, [pdfFile('scan.pdf')])
    const rows = w.findAll('.picked-row')
    expect(rows.length).toBe(1)
    expect(rows[0].text()).toContain('scan.pdf')
    expect(rows[0].text()).toContain('KB')
  })

  it('berkas bisa dihapus dari daftar', async () => {
    const w = mount(PdfKitView)
    await flushPromises()
    await pickFiles(w, [pdfFile('a.pdf'), pdfFile('b.pdf')])
    expect(w.findAll('.picked-row').length).toBe(2)
    await w.findAll('.picked-row')[0].find('button').trigger('click')
    expect(w.findAll('.picked-row').length).toBe(1)
    expect(w.text()).toContain('b.pdf')
  })
})

describe('PdfKitView — submit', () => {
  it('mengirim FormData multipart berisi mode + berkas', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true, status: 201, json: async () => ({ job: { id: 'pk000009' } }),
    }))
    vi.stubGlobal('fetch', fetchMock)
    const w = mount(PdfKitView)
    await flushPromises()
    await pickFiles(w, [pdfFile('scan.pdf')])
    await w.find('button.btn-primary').trigger('click')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, opts] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/pdfkit/jobs')
    expect(opts.method).toBe('POST')
    expect(opts.body).toBeInstanceOf(FormData)
    expect(opts.body.get('mode')).toBe('ringan')
    expect(opts.body.getAll('files').length).toBe(1)
    expect(w.text()).toContain('pk000009')      // umpan balik ke pengguna
    expect(w.findAll('.picked-row').length).toBe(0)   // daftar berkas dikosongkan
  })

  it('pesan galat server ditampilkan (mis. total melebihi batas)', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: false, status: 400, json: async () => ({ msg: 'Total berkas 300 MB melebihi batas 250 MB' }),
    })))
    const w = mount(PdfKitView)
    await flushPromises()
    await pickFiles(w, [pdfFile('besar.pdf')])
    await w.find('button.btn-primary').trigger('click')
    await flushPromises()
    expect(w.find('.b-err').text()).toContain('melebihi batas')
  })
})

describe('PdfKitView — hasil', () => {
  it('menampilkan penghematan, ukuran sebelum→sesudah, dan tautan unduh', async () => {
    const w = mount(PdfKitView)
    await flushPromises()
    expect(w.text()).toContain('pk000001')
    expect(w.find('.save-pill').text()).toContain('Hemat 75%')
    const link = w.find('.out')
    expect(link.attributes('href')).toBe('/api/pdfkit/download/pk000001/scan_berat_kompres.pdf')
    expect(link.attributes('download')).toBe('scan_berat_kompres.pdf')
    expect(w.text()).toContain('1.91 MB')      // ukuran sebelum (2.000.000 byte)
    expect(w.text()).toContain('488 KB')       // ukuran sesudah (500.000 byte)
    expect(w.text()).toContain('mode ringan')
  })

  it('dokumen terbitan sistem ditandai Dilindungi tanpa tautan unduh', async () => {
    apiMock.mockImplementation(apiRouter({
      '/api/pdfkit/jobs': { jobs: [PROTECTED_JOB] },
    }))
    const w = mount(PdfKitView)
    await flushPromises()
    expect(w.text()).toContain('Dilindungi')
    expect(w.find('.it-protected').exists()).toBe(true)
    expect(w.find('.note-row').text()).toContain('registri integritas')
    expect(w.find('.out').exists()).toBe(false)     // tidak ada berkas hasil
  })

  it('tab filter menyaring job gagal/batal', async () => {
    apiMock.mockImplementation(apiRouter({
      '/api/pdfkit/jobs': { jobs: [DONE_JOB] },
    }))
    const w = mount(PdfKitView)
    await flushPromises()
    const tabGagal = w.findAll('.tab')[3]
    await tabGagal.trigger('click')
    expect(w.text()).not.toContain('pk000001')
    expect(w.findComponent({ name: 'EmptyState' }).exists()).toBe(true)
  })
})
