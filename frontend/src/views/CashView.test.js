import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import CashView from './CashView.vue'
import { useAuthStore } from '../stores/auth'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api', () => ({ api: apiMock }))

describe('CashView — menu bar BBM / Kasbon & LPJ / SubsidiTepat', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMock.mockImplementation((path) => {
      if (path === '/api/cash/daily-code') return Promise.resolve({ code: '321', manual_mode: true })
      if (path === '/api/cash/history') return Promise.resolve([])
      if (path === '/api/nav/badges') return Promise.resolve({ badges: { bbm_verify_pending: 3, cash_pending: 2 } })
      return Promise.resolve([])
    })
  })

  const mountView = (role = 'finance') => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const auth = useAuthStore()
    auth.user = { role, user_name: `${role}_sby`, full_name: `${role.toUpperCase()} SBY` }
    return mount(CashView, {
      global: {
        plugins: [pinia],
        stubs: {
          'router-link': { props: ['to'], template: '<a :href="to"><slot /></a>' },
          BbmKasbonPanel: { props: ['activeSection'], template: '<div data-testid="bbm-panel-stub">{{ activeSection }}</div>' },
        },
      },
    })
  }

  it('menampilkan tiga tab utama dengan hitungan antrean', async () => {
    const w = mountView()
    await flushPromises()
    expect(w.text()).toContain('BBM, Kasbon & SPBU')
    expect(w.find('[data-testid="workspace-tab-bbm"]').text()).toContain('3 klaim')
    expect(w.find('[data-testid="workspace-tab-kasbon"]').text()).toContain('2 kasbon')
    expect(w.find('[data-testid="workspace-tab-subsidy"]').exists()).toBe(true)
    expect(w.find('[data-testid="bbm-panel-stub"]').text()).toBe('bbm')
    expect(w.find('[data-testid="workspace-tab-bbm"]').attributes('aria-selected')).toBe('true')
  })

  it('tab BBM hanya menampilkan workspace klaim BBM', async () => {
    const w = mountView()
    await flushPromises()
    expect(w.text()).not.toContain('Kode unik pengajuan kasbon hari ini')
    expect(w.find('[data-testid="bbm-panel-stub"]').text()).toBe('bbm')
  })

  it('tab Kasbon & LPJ menampilkan kode harian dan daftar pengajuan', async () => {
    const w = mountView()
    await flushPromises()
    await w.find('[data-testid="workspace-tab-kasbon"]').trigger('click')
    expect(w.find('[data-testid="workspace-tab-kasbon"]').attributes('aria-selected')).toBe('true')
    expect(w.text()).toContain('Kode unik pengajuan kasbon hari ini')
    expect(w.text()).toContain('Kasbon & LPJ')
    const codeInput = w.findAll('input').find((i) => i.element.value === '321')
    expect(codeInput).toBeTruthy()
    expect(apiMock).toHaveBeenCalledWith('/api/cash/daily-code')
    // Panel BBM tidak ikut dirender saat tab kasbon aktif.
    expect(w.find('[data-testid="bbm-panel-stub"]').exists()).toBe(false)
  })

  it('tab SubsidiTepat menampilkan panel SPBU/OTP dan menyembunyikan kasbon', async () => {
    const w = mountView()
    await flushPromises()
    await w.find('[data-testid="workspace-tab-subsidy"]').trigger('click')
    expect(w.find('[data-testid="workspace-tab-subsidy"]').attributes('aria-selected')).toBe('true')
    expect(w.find('[data-testid="bbm-panel-stub"]').text()).toBe('subsidy')
    expect(w.text()).not.toContain('Kode unik pengajuan kasbon hari ini')
  })

  it('tab SubsidiTepat tidak tersedia untuk role GA', async () => {
    const w = mountView('ga')
    await flushPromises()
    expect(w.find('[data-testid="workspace-tab-subsidy"]').exists()).toBe(false)
    expect(w.find('[data-testid="workspace-tab-kasbon"]').exists()).toBe(true)
  })
})
