import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import QRCode from 'qrcode'
import RecruitmentLinksView from './RecruitmentLinksView.vue'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api', () => ({ api: apiMock }))
vi.mock('qrcode', () => ({ default: { toDataURL: vi.fn(() => Promise.resolve('data:image/png;base64,x')) } }))

const LINKS = { data: [
  { branch_code: 'SBY', branch_name: 'Surabaya',
    portal_path: '/app/recruitment-portal?token=tok-sby', active: true },
  { branch_code: 'MLG', branch_name: 'Malang',
    portal_path: '/app/recruitment-portal?token=tok-mlg', active: true },
] }

// w.text() tidak memuat atribut href; pola ini dipakai untuk href dan HTML penuh.
const LEGACY = /cv-online-form|first-work-form|salin link cv|salin link firstwork/i

async function mountView() {
  apiMock.mockResolvedValue(LINKS)
  const w = mount(RecruitmentLinksView)
  await flushPromises()
  return w
}

describe('RecruitmentLinksView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    QRCode.toDataURL.mockImplementation(() => Promise.resolve('data:image/png;base64,x'))
  })
  afterEach(() => vi.unstubAllGlobals())

  it('menampilkan satu link portal per cabang', async () => {
    const w = await mountView()
    expect(w.text()).toContain('Surabaya')
    expect(w.text()).toContain('Malang')
    expect(w.findAll('[data-portal-link]')).toHaveLength(2)
    expect(w.text()).toContain('/app/recruitment-portal?token=tok-sby')
  })

  it('tidak menampilkan tombol salin link CV atau FirstWork', async () => {
    const w = await mountView()
    const text = w.text()
    expect(text).not.toContain('cv-online-form')
    expect(text).not.toContain('first-work-form')
    expect(text).not.toContain('Salin Link CV')
    expect(text).not.toContain('Salin Link FirstWork')

    const anchors = w.findAll('a[href]')
    expect(anchors.length).toBeGreaterThan(0)
    for (const anchor of anchors) {
      expect(anchor.attributes('href') || '').not.toMatch(LEGACY)
    }
    expect(w.html()).not.toMatch(LEGACY)
  })

  it('menyalin URL absolut ke clipboard', async () => {
    const writeText = vi.fn(() => Promise.resolve())
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    const w = await mountView()
    await w.find('button[data-copy="SBY"]').trigger('click')
    await flushPromises()
    expect(writeText).toHaveBeenCalledWith(
      window.location.origin + '/app/recruitment-portal?token=tok-sby')
  })

  it('QR dibuat lokal dan modal menampilkan URL', async () => {
    const w = await mountView()
    await w.find('button[data-qr="SBY"]').trigger('click')
    await flushPromises()
    expect(w.text()).toContain('QR Portal Rekrutmen SBY')
    expect(QRCode.toDataURL).toHaveBeenCalledWith(
      window.location.origin + '/app/recruitment-portal?token=tok-sby',
      { width: 420, margin: 2 })
    expect(w.find('img.qr-image').attributes('src')).toBe('data:image/png;base64,x')
  })

  it('QR tidak tertukar bila modal dibuka ulang sebelum QR selesai', async () => {
    const pending = new Map()
    QRCode.toDataURL.mockImplementation((url) => new Promise((resolve) => {
      pending.set(url, () => resolve('data:image/png;base64,' + url))
    }))
    const sbyUrl = window.location.origin + '/app/recruitment-portal?token=tok-sby'
    const mlgUrl = window.location.origin + '/app/recruitment-portal?token=tok-mlg'
    const mlgQr = 'data:image/png;base64,' + mlgUrl

    const w = await mountView()
    await w.find('button[data-qr="SBY"]').trigger('click')
    await w.find('button[data-qr="MLG"]').trigger('click')
    const dialog = () => w.find('[role="dialog"]')

    // MLG selesai lebih dulu; SBY sengaja diselesaikan terakhir.
    pending.get(mlgUrl)()
    await flushPromises()
    expect(dialog().text()).toContain('QR Portal Rekrutmen MLG')
    expect(dialog().find('.qr-url').text()).toBe(mlgUrl)
    expect(dialog().find('img.qr-image').attributes('src')).toBe(mlgQr)

    pending.get(sbyUrl)()
    await flushPromises()
    expect(dialog().text()).toContain('QR Portal Rekrutmen MLG')
    expect(dialog().text()).not.toContain(sbyUrl)
    expect(dialog().find('.qr-url').text()).toBe(mlgUrl)
    expect(dialog().find('img.qr-image').attributes('src')).toBe(mlgQr)
  })

  it('membatalkan QR lama saat modal ditutup', async () => {
    let resolveQr
    QRCode.toDataURL.mockImplementationOnce(() => new Promise((resolve) => { resolveQr = resolve }))
    const w = await mountView()
    await w.find('button[data-qr="SBY"]').trigger('click')
    await w.find('[role="dialog"] button[aria-label="Tutup"]').trigger('click')
    resolveQr('data:image/png;base64,stale')
    await flushPromises()
    expect(w.find('[role="dialog"]').exists()).toBe(false)
    expect(w.find('img.qr-image').exists()).toBe(false)
  })

  it('cabang tanpa token dinonaktifkan dan tidak memicu salin/QR', async () => {
    const writeText = vi.fn(() => Promise.resolve())
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    apiMock.mockResolvedValue({ data: [
      { branch_code: 'MED', branch_name: 'Medan', portal_path: '', active: false },
      { branch_code: 'PDM', branch_name: 'Padang',
        portal_path: '/app/recruitment-portal?token=tok-pdm', active: false },
    ] })
    const w = mount(RecruitmentLinksView)
    await flushPromises()

    const cards = w.findAll('[data-portal-link]')
    expect(cards).toHaveLength(2)
    for (const card of cards) {
      expect(card.text()).toContain('Nonaktif')
      expect(card.find('.badge-warn').exists()).toBe(true)
      expect(card.text()).toContain('Belum ada token; hubungi Admin.')
      expect(card.find('a[href]').exists()).toBe(false)
      expect(card.find('button[data-copy]').exists()).toBe(false)
      expect(card.find('button[data-qr]').exists()).toBe(false)
    }
    expect(writeText).not.toHaveBeenCalled()
    expect(QRCode.toDataURL).not.toHaveBeenCalled()
    expect(w.find('[role="dialog"]').exists()).toBe(false)
  })
})
