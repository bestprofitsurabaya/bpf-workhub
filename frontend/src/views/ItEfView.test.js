import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ItEfView from './ItEfView.vue'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api', () => ({ api: apiMock }))

const SITES = [{ name: 'TestSite', wp_url: 'https://example.com' }]
const DUPLICATES = [
  { title: 'Harga Emas Naik', count: 3, post_ids: [1, 2, 3], dates: [] },
  { title: 'IHSG Menguat', count: 2, post_ids: [4, 5], dates: [] },
]

function apiRouter(overrides = {}) {
  return vi.fn(async (path, opts = {}) => {
    const url = path.split('?')[0]
    const table = {
      '/api/scraper/sites': SITES,
      '/api/scraper/analytics': { total_articles: 0, by_site: {}, by_date: {} },
      '/api/scraper/schedule': { optimal_time: '', published_today: 0, can_publish: true, daily_limit: 10 },
      '/api/scraper/history': { history: [] },
      '/api/scraper/settings': { daily_limit: 10 },
      '/api/scraper/duplicates': { ok: true, duplicates: DUPLICATES, total_posts: 5 },
      '/api/scraper/duplicates/delete-all': { ok: true, deleted: 25, total_posts: 25, truncated: false },
      '/api/scraper/log': [],
      ...overrides,
    }
    if (url in table) {
      const v = table[url]
      // Function-valued entries are called lazily (lets tests return rejections
      // without creating unhandled promise rejections at table-build time).
      return typeof v === 'function' ? v(path, opts) : v
    }
    throw new Error(`unmocked api path: ${path}`)
  })
}

async function mountSeoTab(overrides = {}) {
  apiMock.mockImplementation(apiRouter({
    '/api/scraper/duplicates': { ok: true, duplicates: DUPLICATES, total_posts: 5 },
    ...overrides,
  }))
  const w = mount(ItEfView)
  await flushPromises()
  // switch to SEO tab
  const seoTab = w.findAll('button').find(b => b.text().includes('SEO'))
  await seoTab.trigger('click')
  // pick site + run duplicate check so the summary is populated
  await w.findAll('select')[0].setValue('TestSite')
  const checkBtn = w.findAll('button').find(b => b.text().includes('Check'))
  await checkBtn.trigger('click')
  await flushPromises()
  return w
}

const deleteAllCalls = () => apiMock.mock.calls.filter(([p]) => p.startsWith('/api/scraper/duplicates/delete-all'))
const logCalls = () => apiMock.mock.calls.filter(([p]) => p.startsWith('/api/scraper/log'))

describe('ItEfView — Hapus Semua (delete-all) double-confirm flow', () => {
  beforeEach(() => {
    vi.stubGlobal('confirm', vi.fn(() => true))
    vi.stubGlobal('prompt', vi.fn(() => 'HAPUS SEMUA'))
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('confirm #1 menampilkan ringkasan duplikat + peringatan permanen', async () => {
    const w = await mountSeoTab()
    const btn = w.findAll('button').find(b => b.text().includes('Hapus Semua'))
    await btn.trigger('click')

    expect(window.confirm).toHaveBeenCalledTimes(1)
    const text = window.confirm.mock.calls[0][0]
    expect(text).toContain('TestSite')
    expect(text).toContain('PERMANEN')
    // summary from last duplicate check: 5 posts in 2 groups
    expect(text).toContain('5 post dalam 2 grup duplikat')
    // confirm #2 never shown because #1 was accepted then flow continued
    expect(window.prompt).toHaveBeenCalledTimes(1)
  })

  it('membatalkan di confirm #1 → tidak ada request delete-all', async () => {
    vi.stubGlobal('confirm', vi.fn(() => false))
    const w = await mountSeoTab()
    const btn = w.findAll('button').find(b => b.text().includes('Hapus Semua'))
    await btn.trigger('click')

    expect(window.prompt).not.toHaveBeenCalled()
    expect(deleteAllCalls()).toHaveLength(0)
  })

  it('token salah di prompt #2 → tidak ada request delete-all', async () => {
    vi.stubGlobal('prompt', vi.fn(() => 'hapus semua post'))
    const w = await mountSeoTab()
    const btn = w.findAll('button').find(b => b.text().includes('Hapus Semua'))
    await btn.trigger('click')

    expect(window.confirm).toHaveBeenCalledTimes(1)
    expect(window.prompt).toHaveBeenCalledTimes(1)
    expect(deleteAllCalls()).toHaveLength(0)
  })

  it('token valid → POST delete-all dengan confirm token + site', async () => {
    const w = await mountSeoTab()
    const btn = w.findAll('button').find(b => b.text().includes('Hapus Semua'))
    await btn.trigger('click')
    await flushPromises()

    const calls = deleteAllCalls()
    expect(calls).toHaveLength(1)
    expect(calls[0][1].method).toBe('POST')
    expect(calls[0][1].body).toEqual({ site_name: 'TestSite', confirm: 'HAPUS SEMUA' })
  })

  it('sukses → pesan ringkasan 25/25 + duplikat dicek ulang + log direfresh', async () => {
    const w = await mountSeoTab()
    const btn = w.findAll('button').find(b => b.text().includes('Hapus Semua'))
    await btn.trigger('click')
    await flushPromises()

    expect(w.text()).toContain('Hapus semua selesai: 25/25 post dihapus')
    // re-check duplicates after deletion
    expect(apiMock.mock.calls.filter(([p]) => p.startsWith('/api/scraper/duplicates')).length).toBeGreaterThanOrEqual(2)
    // activity log refreshed so the DELETE_ALL entry shows up
    expect(logCalls().length).toBeGreaterThanOrEqual(1)
  })

  it('server menolak (cap) → pesan error dari server', async () => {
    const w = await mountSeoTab({
      // Lazily-created rejection: an eagerly-created rejected Promise here would
      // stay unhandled until the await, tripping Vitest's unhandled-rejection guard.
      '/api/scraper/duplicates/delete-all': () => Promise.reject(new Error('Site memiliki 600 post (> cap 500).')),
    })
    const btn = w.findAll('button').find(b => b.text().includes('Hapus Semua'))
    await btn.trigger('click')
    await flushPromises()

    expect(w.text()).toContain('Site memiliki 600 post (> cap 500).')
  })
})

describe('ItEfView — activity log modal (siapa menghapus apa)', () => {
  const LOGS = [
    { ts: '2026-09-12T03:00:00', level: 'WARNING', category: 'DELETE_ALL',
      msg: "Hapus semua: 24/25 post dihapus dari site 'TestSite'",
      user: 'it_sby',
      extra: { user: 'it_sby', site: 'TestSite', deleted: 24, total_posts: 25, failed: 1 } },
    { ts: '2026-09-12T02:00:00', level: 'INFO', category: 'UPLOAD', msg: 'Upload finished', user: 'admin' },
  ]

  beforeEach(() => {
    apiMock.mockImplementation(apiRouter({ '/api/scraper/log': LOGS }))
  })
  afterEach(() => vi.clearAllMocks())

  async function openLog() {
    const w = mount(ItEfView)
    await flushPromises()
    const logBtn = w.findAll('button').find(b => b.text().includes('📝'))
    await logBtn.trigger('click')
    await flushPromises()
    return w
  }

  it('menampilkan entri DELETE_ALL dengan aktor & detail', async () => {
    const w = await openLog()
    expect(w.text()).toContain('DELETE_ALL')
    expect(w.text()).toContain("Hapus semua: 24/25 post dihapus dari site 'TestSite'")
    expect(w.text()).toContain('it_sby')
    expect(w.text()).toContain('deleted=24')
  })

  it('filter kategori menyaring entri log', async () => {
    const w = await openLog()
    const catSelect = w.findAll('select').find(s => s.text().includes('Semua kategori'))
    await catSelect.setValue('DELETE_ALL')
    expect(w.text()).toContain('Hapus semua: 24/25')
    expect(w.text()).not.toContain('Upload finished')
  })
})

describe('ItEfView — cleanup duplikat (bulk keep-terbaru) + proteksi keep_ids', () => {
  beforeEach(() => {
    vi.stubGlobal('confirm', vi.fn(() => true))
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  const cleanupCalls = () => apiMock.mock.calls.filter(([p]) => p.startsWith('/api/scraper/duplicates/cleanup'))
  const deleteCalls = () => apiMock.mock.calls.filter(([p]) => p.startsWith('/api/scraper/duplicates/delete'))

  it('tombol cleanup → loop sampai remaining=0, pesan total terhapus', async () => {
    let round = 0
    const w = await mountSeoTab({
      '/api/scraper/duplicates/cleanup': () => {
        round++
        return round < 3 ? { ok: true, deleted: 2, remaining: 5 } : { ok: true, deleted: 1, remaining: 0 }
      },
    })
    const btn = w.findAll('button').find(b => b.text().includes('Simpan Terbaru'))
    await btn.trigger('click')
    await flushPromises()

    expect(cleanupCalls().length).toBe(3)
    for (const [, opts] of cleanupCalls()) expect(opts.body.site_name).toBe('TestSite')
    expect(w.text()).toContain('Cleanup selesai: 5 duplikat dihapus')
  })

  it('server error → pesan error, loop berhenti', async () => {
    const w = await mountSeoTab({
      '/api/scraper/duplicates/cleanup': () => Promise.reject(new Error('boom')),
    })
    const btn = w.findAll('button').find(b => b.text().includes('Simpan Terbaru'))
    await btn.trigger('click')
    await flushPromises()

    expect(cleanupCalls().length).toBe(1)
    expect(w.text()).toContain('boom')
  })

  it('hapus per-grup hanya mengirim duplikat (keep_ids terlindungi)', async () => {
    const w = await mountSeoTab({
      // DUPLICATES[0]: count 3 → post_ids [1,2,3]; keep #1, kirim [2,3]
      '/api/scraper/duplicates/delete': { ok: true, deleted: 2, failed: 0, protected: [1] },
    })
    const btns = w.findAll('button').filter(b => b.text().includes('Hapus 2 duplikat'))
    expect(btns.length).toBeGreaterThan(0)
    await btns[0].trigger('click')
    await flushPromises()

    const calls = deleteCalls()
    expect(calls).toHaveLength(1)
    expect(calls[0][1].body).toEqual({ site_name: 'TestSite', post_ids: [2, 3], keep_ids: [1] })
  })

  it('grup single-post tidak mengirim request hapus', async () => {
    const w = await mountSeoTab({
      '/api/scraper/duplicates': { ok: true, duplicates: [{ title: 'Sendirian', count: 1, post_ids: [7], dates: [] }], total_posts: 1 },
    })
    // grup count=1 tidak merender tombol hapus per-grup (pola "Hapus N duplikat")
    const btns = w.findAll('button').filter(b => /Hapus \d+ duplikat/.test(b.text()))
    expect(btns.length).toBe(0)
    expect(deleteCalls()).toHaveLength(0)
  })
})
