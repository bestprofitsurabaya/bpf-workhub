import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import CashView from './CashView.vue'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api', () => ({ api: apiMock }))

describe('CashView — satu halaman operasional BBM/kasbon/SPBU', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setActivePinia(createPinia())
    apiMock.mockImplementation((path) => {
      if (path === '/api/cash/daily-code') return Promise.resolve({ code: '321', manual_mode: true })
      if (path === '/api/cash/pending-lpj') return Promise.resolve([])
      if (path === '/api/cash/history') return Promise.resolve([])
      return Promise.resolve([])
    })
  })

  const mountView = () => mount(CashView, {
    global: {
      stubs: {
        'router-link': { props: ['to'], template: '<a :href="to"><slot /></a>' },
        BbmKasbonPanel: { template: '<div data-testid="bbm-panel-stub" />' },
      },
    },
  })

  it('menampilkan klaim BBM + Data SPBU dalam panel yang sama dengan kasbon', async () => {
    const w = mountView()
    await flushPromises()
    expect(w.text()).toContain('BBM, Kasbon & Subsidi Tepat')
    expect(w.find('[data-testid="bbm-panel-stub"]').exists()).toBe(true)
  })

  it('kode unik pengajuan kasbon hari ini tetap tampil', async () => {
    const w = mountView()
    await flushPromises()
    expect(w.text()).toContain('Kode unik pengajuan kasbon hari ini')
    const codeInput = w.findAll('input').find((i) => i.element.value === '321')
    expect(codeInput).toBeTruthy()
    expect(apiMock).toHaveBeenCalledWith('/api/cash/daily-code')
  })
})
