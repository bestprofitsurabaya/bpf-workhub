import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
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

async function mountView() {
  apiMock.mockResolvedValue(LINKS)
  const w = mount(RecruitmentLinksView)
  await flushPromises()
  return w
}

describe('RecruitmentLinksView', () => {
  beforeEach(() => vi.clearAllMocks())

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
  })
})
