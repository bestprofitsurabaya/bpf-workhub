import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import CashView from './CashView.vue'
import { useAuthStore } from '../stores/auth'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../api', () => ({ api: apiMock }))

// v2.104.0 — fixture kasbon dengan tiga kondisi supaya filter bisa diuji:
// satu sudah cair & selesai, satu dana masih di driver, satu belum cair.
const CASH_ROWS = [
  { id: 1, display_id: 'KSB-1', status: 'COMPLETED', total_amount: 100000, handover_at: '2026-11-01 10:00:00' },
  { id: 2, display_id: 'KSB-2', status: 'FUNDS_WITH_DRIVER', total_amount: 200000, handover_at: '2026-11-02 10:00:00' },
  { id: 3, display_id: 'KSB-3', status: 'DRAFT', total_amount: 300000, handover_at: null },
]

// Fase 1 (v2.100.0): laporan dirender malas. Di tes menu, ganti dengan stub
// supaya chart.js & request laporan tidak ikut berjalan.
// `__esModule` wajib: defineAsyncComponent membaca modul hasil import dan akan
// memperlakukan namespace proxy Vitest sebagai komponen bila flag ini hilang.
vi.mock('./RekapView.vue', () => ({
  __esModule: true,
  default: { name: 'RekapStub', props: ['scope'], template: '<div data-testid="report-stub-rekap">rekap-stub</div>' },
}))
vi.mock('./ExpensesView.vue', () => ({
  __esModule: true,
  default: { name: 'ExpensesStub', props: ['scope'], template: '<div data-testid="report-stub-realisasi">realisasi-stub</div>' },
}))
vi.mock('./AnalyticsView.vue', () => ({
  __esModule: true,
  default: { name: 'AnalyticsStub', props: ['scope'], template: '<div data-testid="report-stub-analisis">analisis-stub</div>' },
}))

describe('CashView — meja kerja BBM / Kasbon & LPJ / SPBU / Laporan', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // jsdom tidak mengimplementasikan alert — aksi di panel memakai alert.
    global.alert = vi.fn()
    apiMock.mockImplementation((path) => {
      if (path === '/api/cash/daily-code') return Promise.resolve({ code: '321', manual_mode: true })
      if (path === '/api/cash/history') return Promise.resolve(CASH_ROWS)
      if (path === '/api/nav/badges') return Promise.resolve({ badges: { bbm_verify_pending: 3, cash_pending: 2 } })
      if (path === '/api/bbm/workspace/summary') return Promise.resolve({
        period: { start: '2026-10-14', end: '2026-11-12' },
        claims: {
          dibayar: { count: 4, amount: 1200000 },
          lpj_sah: { count: 2, amount: 500000 },
        },
        kasbon: {
          cair: { count: 3, amount: 900000 },
          outstanding: { count: 1, amount: 300000 },
        },
      })
      if (path === '/api/bbm/workspace/actions') return Promise.resolve({
        items: [{
          key: 'claim_pending', label: 'Klaim menunggu verifikasi GA', kind: 'claim',
          count: 2, amount: 500000, oldest_days: 5, threshold_days: 2, target: 'bbm',
          rows: [
            { id: 71, ref: 'TX-71', driver_name: 'Budi', nopol: 'N 1', amount: 250000, age_days: 5 },
            { id: 72, ref: 'TX-72', driver_name: 'Sari', nopol: '', amount: 250000, age_days: 3 },
          ],
        }, {
          key: 'driver_due_lpj', label: 'Dana di driver, LPJ belum masuk', kind: 'cash',
          count: 2, amount: 500000, oldest_days: 21, threshold_days: 14, target: 'kasbon',
          rows: [
            { id: 81, ref: 'KSB-81', driver_name: 'Andi', nopol: 'N 8', amount: 250000, age_days: 21 },
          ],
        }],
        thresholds: { claim_days: 2, driver_days: 14, lpj_days: 7 },
      })
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
          BbmKasbonPanel: { props: ['activeSection', 'focus'], template: '<div data-testid="bbm-panel-stub">{{ activeSection }}</div>' },
          VoucherPanel: { template: '<div data-testid="voucher-panel-stub">voucher</div>' },
          // KPI disorotkan agar uji fokus pada CashView: stub memancarkan
          // event `open` persis seperti komponen aslinya.
          BbmWorkspaceKpi: {
            props: ['scope'],
            template: '<button data-testid="kpi-trigger" @click="$emit(\'open\', { tab: \'kasbon\', filters: { kasbon: \'outstanding\' }, label: \'Dana di Driver\' })">kpi</button>',
          },
        },
      },
    })
  }

  const openReports = async (w) => {
    await w.find('[data-testid="workspace-tab-laporan"]').trigger('click')
    await flushPromises()
    // Beri satu putaran microtask untuk loader defineAsyncComponent.
    await new Promise((r) => setTimeout(r, 0))
    await flushPromises()
  }

  it('menampilkan lima tab utama dengan hitungan antrean', async () => {
    const w = mountView()
    await flushPromises()
    expect(w.text()).toContain('BBM, Kasbon & SPBU')
    expect(w.find('[data-testid="workspace-tab-bbm"]').text()).toContain('3 klaim')
    expect(w.find('[data-testid="workspace-tab-kasbon"]').text()).toContain('2 kasbon')
    expect(w.find('[data-testid="workspace-tab-voucher"]').exists()).toBe(true)
    expect(w.find('[data-testid="workspace-tab-subsidy"]').exists()).toBe(true)
    expect(w.find('[data-testid="workspace-tab-laporan"]').exists()).toBe(true)
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

  it('setiap kasbon punya dokumen PDF per transaksi', async () => {
    const openSpy = vi.spyOn(window, 'open').mockReturnValue(null)
    const w = mountView()
    await flushPromises()
    await w.find('[data-testid="workspace-tab-kasbon"]').trigger('click')

    const row = w.findAll('.cash-item').find((r) => r.text().includes('KSB-1'))
    expect(row).toBeTruthy()
    await row.findAll('button').find((b) => b.text().includes('📄 PDF')).trigger('click')
    expect(openSpy).toHaveBeenCalledWith('/api/cash/1/pdf', '_blank', 'noopener')
    openSpy.mockRestore()
  })

  it('tab Voucher Rekanan menampilkan panel voucher', async () => {
    const w = mountView()
    await flushPromises()
    await w.find('[data-testid="workspace-tab-voucher"]').trigger('click')
    expect(w.find('[data-testid="workspace-tab-voucher"]').attributes('aria-selected')).toBe('true')
    expect(w.find('[data-testid="voucher-panel-stub"]').exists()).toBe(true)
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

  // Fase 1: tiga laporan lama menjadi sub-tab di meja kerja yang sama.
  it('tab Laporan memuat Rekap, Realisasi, dan Analisis', async () => {
    const w = mountView('finance')
    await flushPromises()
    expect(w.find('[data-testid="workspace-tab-laporan"]').exists()).toBe(true)
    await openReports(w)
    expect(w.find('[data-testid="report-tab-rekap"]').exists()).toBe(true)
    expect(w.find('[data-testid="report-tab-realisasi"]').exists()).toBe(true)
    expect(w.find('[data-testid="report-tab-analisis"]').exists()).toBe(true)
    // Default sub-tab = Rekap, dan isinya benar-benar dirender.
    expect(w.find('[data-testid="report-tab-rekap"]').attributes('aria-selected')).toBe('true')
    expect(w.find('[data-testid="report-stub-rekap"]').exists()).toBe(true)
  })

  it('sub-tab laporan bisa berpindah tanpa meninggalkan meja kerja', async () => {
    const w = mountView('finance')
    await flushPromises()
    await openReports(w)
    await w.find('[data-testid="report-tab-realisasi"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="report-stub-realisasi"]').exists()).toBe(true)
    expect(w.find('[data-testid="report-stub-rekap"]').exists()).toBe(false)
    expect(w.find('[data-testid="workspace-tab-laporan"]').attributes('aria-selected')).toBe('true')
  })

  // Fase 3 (v2.103.0): antrean tindakan tampil dan menunjuk tab yang tepat.
  it('panel Perlu Tindakan menampilkan antrean dan membuka tab terkait', async () => {
    const w = mountView('finance')
    await flushPromises()

    const queue = w.find('[data-testid="action-queue"]')
    expect(queue.exists()).toBe(true)
    expect(w.find('[data-testid="action-driver_due_lpj"]').text()).toContain('Dana di driver')
    expect(w.find('[data-testid="action-driver_due_lpj"]').text()).toContain('21 hari')

    await w.find('[data-testid="action-open-driver_due_lpj"]').trigger('click')
    expect(w.find('[data-testid="workspace-tab-kasbon"]').attributes('aria-selected')).toBe('true')
    expect(w.text()).toContain('Kode unik pengajuan kasbon hari ini')
  })

  // Fase 3 (v2.102.0): satu periode untuk semua sub-laporan.
  it('tab Laporan memakai satu context bar periode untuk semua sub-tab', async () => {
    const w = mountView('finance')
    await flushPromises()
    await openReports(w)

    expect(w.find('[data-testid="report-scope"]').exists()).toBe(true)
    await w.find('[data-testid="scope-preset-year"]').trigger('click')
    await flushPromises()

    const startVal = w.find('[data-testid="scope-start"]').element.value
    const endVal = w.find('[data-testid="scope-end"]').element.value
    expect(startVal).toMatch(/-01-01$/)

    // Sub-tab aktif menerima periode dari bar…
    expect(w.findComponent({ name: 'RekapStub' }).props('scope')).toEqual({ start: startVal, end: endVal })
    // …dan sub-tab lain memakai periode yang sama saat berpindah.
    await w.find('[data-testid="report-tab-analisis"]').trigger('click')
    await flushPromises()
    expect(w.findComponent({ name: 'AnalyticsStub' }).props('scope').start).toBe(startVal)
  })

  it('GA hanya melihat Rekap & Analisis — Realisasi tidak dirender', async () => {
    const w = mountView('ga')
    await flushPromises()
    await openReports(w)
    expect(w.find('[data-testid="report-tab-rekap"]').exists()).toBe(true)
    expect(w.find('[data-testid="report-tab-analisis"]').exists()).toBe(true)
    expect(w.find('[data-testid="report-tab-realisasi"]').exists()).toBe(false)
  })

  // --- v2.104.0: "angka → baris → aksi" --------------------------------

  it('KPI meneruskan filter ke tab tujuan dan menyaring daftar', async () => {
    const w = mountView('finance')
    await flushPromises()

    // KPI "Dana di Driver" → tab Kasbon + filter dana di driver.
    await w.find('[data-testid="kpi-trigger"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="workspace-tab-kasbon"]').attributes('aria-selected')).toBe('true')
    // Hanya kasbon berstatus FUNDS_WITH_DRIVER / LPJ_SUBMITTED yang tampil.
    expect(w.text()).toContain('KSB-2')
    expect(w.text()).not.toContain('KSB-1')
    expect(w.text()).not.toContain('KSB-3')
  })

  it('filter kasbon bisa diubah dan mengembalikan seluruh daftar', async () => {
    const w = mountView('finance')
    await flushPromises()
    await w.find('[data-testid="workspace-tab-kasbon"]').trigger('click')

    expect(w.text()).toContain('3 pengajuan')
    await w.find('[data-testid="kasbon-filter-cair"]').trigger('click')
    expect(w.text()).toContain('2 pengajuan')
    expect(w.text()).toContain('KSB-1')
    expect(w.text()).not.toContain('KSB-3')

    await w.find('[data-testid="kasbon-filter-all"]').trigger('click')
    expect(w.text()).toContain('3 pengajuan')
  })

  it('antrean menampilkan baris nyata dan aksi sesuai peran', async () => {
    const w = mountView('ga')
    await flushPromises()

    await w.find('[data-testid="action-rows-claim_pending"]').trigger('click')
    expect(w.find('[data-testid="action-row-claim_pending-71"]').text()).toContain('TX-71')
    expect(w.find('[data-testid="action-row-claim_pending-71"]').text()).toContain('5 hari')
    // GA boleh memverifikasi klaim langsung dari antrean.
    expect(w.find('[data-testid="action-do-claim_pending-verify_claim-71"]').exists()).toBe(true)
  })

  it('Finance tidak melihat tombol verifikasi GA di antrean', async () => {
    const w = mountView('finance')
    await flushPromises()
    await w.find('[data-testid="action-rows-claim_pending"]').trigger('click')
    expect(w.find('[data-testid="action-do-claim_pending-verify_claim-71"]').exists()).toBe(false)
  })

  it('aksi dari antrean memakai modal & endpoint yang sama dengan panel tab', async () => {
    const w = mountView('ga')
    await flushPromises()
    await w.find('[data-testid="action-rows-claim_pending"]').trigger('click')
    await w.find('[data-testid="action-do-claim_pending-verify_claim-71"]').trigger('click')
    await flushPromises()

    // Modal konfirmasi terbuka — bukan aksi langsung tanpa konfirmasi.
    expect(w.text()).toContain('Verifikasi Klaim #71')
    await w.findAll('button').find((b) => b.text() === 'Konfirmasi').trigger('click')
    await flushPromises()

    expect(apiMock).toHaveBeenCalledWith('/api/queue/approve-ga/71', {
      method: 'POST',
      body: { ga_name: 'GA SBY' },
    })
  })
})
