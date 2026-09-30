import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import TranscoderView from './TranscoderView.vue'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api', () => ({ api: apiMock }))

const DONE_JOB = {
  id: 'tc000001', user: 'it_sby', status: 'done', stage: 'Selesai',
  progress: 100, created_at: 1700000000, finished_at: 1700000600,
  urls: ['https://youtu.be/a1'],
  formats: ['mp3', 'mp4'],
  items: [{
    url: 'https://youtu.be/a1', title: 'Video Uji', status: 'done',
    progress: 100, error: '',
    outputs: [
      { format: 'mp3', label: 'MP3 192 kbps', kind: 'audio', file: 'Video_Uji.mp3', size: 1048576 },
      { format: 'mp4', label: 'MP4 720p', kind: 'video', file: 'Video_Uji.mp4', size: 73400320 },
    ],
  }],
}

const RUNNING_JOB = {
  ...DONE_JOB, id: 'tc000002', status: 'transcoding', progress: 42,
  stage: 'Membuat MP4 720p…',
  items: [{ ...DONE_JOB.items[0], status: 'transcoding', outputs: [] }],
}

function apiRouter(overrides = {}) {
  return vi.fn(async (path, opts = {}) => {
    const url = path.split('?')[0]
    const table = {
      '/api/transcoder/jobs': { jobs: [DONE_JOB] },
      ...overrides,
    }
    if (url in table) {
      const v = table[url]
      return typeof v === 'function' ? v(path, opts) : v
    }
    throw new Error(`unmocked api path: ${path}`)
  })
}

const fillForm = async (w, urls = 'https://youtu.be/a1') => {
  await w.find('textarea').setValue(urls)
}

beforeEach(() => {
  apiMock.mockImplementation(apiRouter())
  vi.useFakeTimers({ shouldAdvanceTime: true })
  // elemen unduhan tidak boleh benar-benar diklik di test
  vi.spyOn(document, 'createElement')
})
afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('TranscoderView — form submit', () => {
  it('tombol submit nonaktif sebelum isi link & format', () => {
    const w = mount(TranscoderView)
    expect(w.find('button.btn-primary').attributes('disabled')).toBeDefined()
  })

  it('aktif setelah link + pilih format, kirim payload benar', async () => {
    apiMock.mockImplementation(apiRouter({
      '/api/transcoder/jobs': (path, opts) => {
        if (opts?.method === 'POST') {
          expect(opts.body).toEqual({
            urls: ['https://youtu.be/a1', 'https://youtu.be/b2'],
            formats: ['mp3'],
          })
          return { status: 'ok', job: { id: 'tc000009' } }
        }
        return { jobs: [DONE_JOB] }
      },
    }))
    const w = mount(TranscoderView)
    await flushPromises()

    await fillForm(w, 'https://youtu.be/a1\nhttps://youtu.be/b2')
    const chip = w.findAll('.chip').find(c => c.text().includes('MP3'))
    await chip.trigger('click')

    const btn = w.find('button.btn-primary')
    expect(btn.attributes('disabled')).toBeUndefined()
    expect(btn.text()).toContain('2 link')
    await btn.trigger('click')
    await flushPromises()

    const post = apiMock.mock.calls.find(([, o]) => o?.method === 'POST')
    expect(post).toBeTruthy()
  })

  it('counter link menampilkan jumlah', async () => {
    const w = mount(TranscoderView)
    await flushPromises()
    await fillForm(w, 'https://youtu.be/a1, https://youtu.be/b2, https://youtu.be/c3')
    expect(w.text()).toContain('3/10 link')
  })
})

describe('TranscoderView — daftar job & hasil', () => {
  it('menampilkan job selesai + tombol unduh per format', async () => {
    const w = mount(TranscoderView)
    await flushPromises()

    expect(w.text()).toContain('tc000001')
    expect(w.text()).toContain('Video Uji')
    const links = w.findAll('a.out')
    expect(links.length).toBe(2)
    expect(links[0].attributes('href')).toBe('/api/transcoder/download/tc000001/Video_Uji.mp3')
    expect(links[0].text()).toContain('1.0 MB')
  })

  it('job berjalan menampilkan progress', async () => {
    apiMock.mockImplementation(apiRouter({ '/api/transcoder/jobs': { jobs: [RUNNING_JOB] } }))
    const w = mount(TranscoderView)
    await flushPromises()

    expect(w.find('.fill').exists()).toBe(true)
    expect(w.find('.fill').attributes('style')).toContain('42%')
    expect(w.text()).toContain('Membuat MP4 720p…')
    // job jalan punya tombol batalkan, tidak ada tombol unduh semua
    expect(w.text()).toContain('Batalkan')
    expect(w.text()).not.toContain('Unduh semua')
  })

  it('filter tab menyaring job', async () => {
    apiMock.mockImplementation(apiRouter({ '/api/transcoder/jobs': { jobs: [DONE_JOB, RUNNING_JOB] } }))
    const w = mount(TranscoderView)
    await flushPromises()
    expect(w.findAll('.job').length).toBe(2)

    const doneTab = w.findAll('.tab').find(t => t.text() === 'Selesai')
    await doneTab.trigger('click')
    expect(w.findAll('.job').length).toBe(1)
    expect(w.text()).toContain('tc000001')
  })

  it('hapus job manggil API DELETE', async () => {
    global.confirm = vi.fn(() => true)
    apiMock.mockImplementation(apiRouter({
      '/api/transcoder/jobs': (path, opts) => {
        if (opts?.method === 'DELETE') return { status: 'ok' }
        return { jobs: [DONE_JOB] }
      },
    }))
    const w = mount(TranscoderView)
    await flushPromises()
    const del = w.findAll('button').find(b => b.text().includes('Hapus'))
    await del.trigger('click')
    await flushPromises()
    const call = apiMock.mock.calls.find(([p, o]) => p.includes('/jobs/tc000001') && o?.method === 'DELETE')
    expect(call).toBeTruthy()
  })

  it('cancel konfirmasi dulu — bila ditolak, API tidak dipanggil', async () => {
    apiMock.mockImplementation(apiRouter({ '/api/transcoder/jobs': { jobs: [RUNNING_JOB] } }))
    global.confirm = vi.fn(() => false)
    const w = mount(TranscoderView)
    await flushPromises()
    const cancel = w.findAll('button').find(b => b.text().includes('Batalkan'))
    await cancel.trigger('click')
    await flushPromises()
    expect(apiMock.mock.calls.filter(([p]) => p.includes('/cancel')).length).toBe(0)
  })
})
