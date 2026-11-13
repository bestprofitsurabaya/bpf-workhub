import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import AppLayout from './AppLayout.vue'
import { useAuthStore } from '../stores/auth'

const { apiMock, rtMock } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  rtMock: {
    connected: false, items: [], toasts: [], unread: 0, receptionistSeq: 0,
    connect: vi.fn(), disconnect: vi.fn(), markAllRead: vi.fn(), dismissToast: vi.fn(),
  },
}))
vi.mock('../api', () => ({ api: apiMock }))
vi.mock('../stores/realtime', () => ({ useRealtimeStore: () => rtMock }))

function makeRouter() {
  const Blank = { template: '<div />' }
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/dashboard', component: Blank },
      { path: '/ga', component: Blank },
      { path: '/settings', component: Blank },
      { path: '/cash', component: Blank },
      { path: '/receptionist', component: Blank },
      { path: '/first-work', component: Blank },
    ],
  })
}

async function mountLayout({ role = 'admin', userName = 'admin', isHo = true, path = '/settings' } = {}) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore()
  auth.user = { role, user_name: userName, full_name: 'Uji', is_ho_admin: isHo }
  apiMock.mockImplementation((p) => {
    if (p === '/api/nav/badges') return Promise.resolve({ badges: { ga_pending: 3, first_work_pending: 4 } })
    return Promise.resolve({})
  })
  const router = makeRouter()
  await router.push(path)
  await router.isReady()
  const w = mount(AppLayout, { global: { plugins: [pinia, router] } })
  await flushPromises()
  return { w, router }
}

describe('AppLayout — P1 navigasi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.setItem('bpf_onboarded:admin', '1')
    localStorage.setItem('bpf_onboarded:admin_sby', '1')
  })

  it('menu admin cabang dikelompokkan & aksi lintas cabang tetap tersembunyi', async () => {
    const { w } = await mountLayout({ userName: 'admin_sby', isHo: false })
    const nav = w.find('.side-nav').text()
    expect(nav).toContain('Ringkasan')
    expect(nav).toContain('Operasional')
    // admin tidak terlibat ACC apa pun → grup Persetujuan kosong & tidak tampil
    expect(nav).not.toContain('ACC Atasan')
    expect(nav).toContain('Rekrutmen')
    expect(nav).toContain('Absensi FirstWork')
    expect(nav).toContain('Perkakas IT')
    expect(nav).not.toContain('Rekrutan Saya')
    expect(nav).not.toContain('Access Review')
    expect(nav).not.toContain('Audit Log')
    w.unmount()
  })

  it('menu traineer hanya berisi Rekrutmen (lihat saja) & Absensi FirstWork', async () => {
    const { w } = await mountLayout({ role: 'traineer', userName: 'traineer_mlg', isHo: false, path: '/first-work' })
    const nav = w.find('.side-nav').text()
    expect(nav).toContain('Rekrutmen')
    expect(nav).toContain('Absensi FirstWork')
    for (const hidden of ['Rekrutan Saya', 'Pelamar Kerja', 'User & Driver', 'Sync Sheet', 'In-Out Karyawan']) {
      expect(nav).not.toContain(hidden)
    }
    w.unmount()
  })

  it('menu finance menampilkan workspace BBM dan modul kerja finance yang relevan', async () => {
    const { w } = await mountLayout({ role: 'finance', userName: 'finance_sby', isHo: false, path: '/cash' })
    const nav = w.find('.side-nav').text()
    expect(nav).toContain('Dashboard Finance')
    expect(nav).toContain('BBM, Kasbon & SPBU')
    expect(nav).toContain('Air Minum')
    // v2.105.0: laporan dipangkas dari sidebar finance — semuanya sudah ada di
    // dalam /cash tab Laporan (tanpa duplikasi menu).
    for (const hidden of ['Dashboard GA', 'Log Perjalanan', 'Pengadaan (PO)', 'ACC Atasan',
                          'Rekap Klaim BBM', 'Realisasi Pengeluaran', 'Analisis BBM & Armada']) {
      expect(nav).not.toContain(hidden)
    }
    w.unmount()
  })

  it('badge antrean tampil di menu yang relevan', async () => {
    const { w } = await mountLayout({ role: 'admin', userName: 'admin', isHo: true })
    const ga = w.findAll('.side-nav a').find((a) => a.text().includes('Dashboard GA'))
    expect(ga.text()).toContain('3')
    const fw = w.findAll('.side-nav a').find((a) => a.text().includes('Absensi FirstWork'))
    expect(fw.text()).toContain('4')
    w.unmount()
  })

  it('breadcrumb mengikuti grup & halaman aktif', async () => {
    const { w } = await mountLayout({ path: '/settings' })
    expect(w.find('.crumb').text()).toContain('Beranda')
    expect(w.find('.crumb').text()).toContain('SDM & Armada')
    expect(w.find('.crumb').text()).toContain('Pengaturan')
    w.unmount()
  })

  it('tombol ? membuka bantuan halaman & glosarium', async () => {
    const { w } = await mountLayout({ path: '/settings' })
    await w.find('button[title="Bantuan & glosarium (?)"]').trigger('click')
    await flushPromises()
    expect(w.text()).toContain('Bantuan & Glosarium')
    expect(w.text()).toContain('Pengaturan')
    await w.findAll('button').find((b) => b.text().includes('Glosarium')).trigger('click')
    expect(w.text()).toContain('Step-up PIN')
    w.unmount()
  })

  it('Ctrl+K membuka pencarian, Enter membuka menu terpilih', async () => {
    const { w, router } = await mountLayout({ path: '/settings' })
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true }))
    await flushPromises()
    const input = w.find('.search-input')
    expect(input.exists()).toBe(true)
    await input.setValue('kasbon')
    expect(w.findAll('.search-item').length).toBe(1)
    expect(w.find('.search-item').text()).toContain('BBM, Kasbon & SPBU')
    await input.trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/cash')
    expect(w.find('.search-overlay').exists()).toBe(false)
    w.unmount()
  })
})
