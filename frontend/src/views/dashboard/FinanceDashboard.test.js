import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises, config } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import FinanceDashboard from './FinanceDashboard.vue'

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }))
vi.mock('../../api', () => ({ api: apiMock }))

const RECAP = {
  summary: { total: 4, pending: 1, verified: 2, rejected: 1, qty: 53 },
  per_ob: [
    { ob_name: 'OB 1', total: 2, pending: 1, verified: 1, rejected: 0, qty: 5 },
    { ob_name: 'OB 2', total: 1, pending: 0, verified: 0, rejected: 1, qty: 48 },
  ],
  per_type: [
    { name: 'Gelas', qty: 48, purchases: 1 },
    { name: 'Galon', qty: 3, purchases: 1 },
  ],
  per_brand: [
    { name: 'AQUA', qty: 3, purchases: 1 },
    { name: 'Le Minerale', qty: 2, purchases: 1 },
  ],
  queue: [{ id: 1, display_id: 'WTR-20260812-0001', ob_name: 'OB 1', purchase_date: '2026-08-12', item_count: 1 }],
  kasbon: { waiting_approve: { count: 2, nominal: 250000 }, waiting_lpj: { count: 1 } },
}

// old inline helper replaced by pinia-aware mountView() di atas

describe('FinanceDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setActivePinia(createPinia())
    config.global.stubs = {
      'router-link': { props: ['to'], template: '<a :href="to"><slot /></a>' },
    }
  })
  afterEach(() => {
    config.global.stubs = {}
    vi.unstubAllGlobals()
  })

  async function mountView(mountOpts = {}) {
    const pinia = createPinia()
    setActivePinia(pinia)
    apiMock.mockResolvedValue(RECAP)
    const w = mount(FinanceDashboard, {
      global: {
        plugins: [pinia],
        stubs: { 'router-link': { template: '<a><slot /></a>' } },
      },
      ...mountOpts,
    })
    await flushPromises()
    return w
  }

  it('menampilkan kartu statistik rekap air minum', async () => {
    const w = await mountView()
    expect(w.text()).toContain('Total Pengajuan')
    expect(w.text()).toContain('Menunggu Verifikasi')
    expect(w.text()).toContain('Terverifikasi')
    expect(w.text()).toContain('4')
    expect(w.text()).toContain('53')
  })

  it('menampilkan antrean verifikasi & tabel per OB', async () => {
    const w = await mountView()
    expect(w.text()).toContain('WTR-20260812-0001')
    expect(w.text()).toContain('OB 1')
    expect(w.text()).toContain('OB 2')
    expect(w.text()).toContain('Verifikasi →')
  })

  it('menampilkan ringkasan kasbon menunggu Finance', async () => {
    const w = await mountView()
    expect(w.text()).toContain('Rp 250.000')
    expect(w.text()).toContain('2 pengajuan')
  })

  it('tombol Export CSV mengarah ke endpoint export', async () => {
    // jsdom tidak mendukung navigasi — stub location agar href bisa di-assign
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { href: 'http://localhost/' },
    })
    const w = await mountView()
    await w.findAll('button').find((b) => b.text().includes('Export CSV')).trigger('click')
    expect(window.location.href).toBe('/api/water/recap/export')
  })

  it('filter tanggal diteruskan ke /api/water/recap', async () => {
    const w = await mountView()
    const inputs = w.findAll('input[type="date"]')
    await inputs[0].setValue('2026-08-01')
    await inputs[1].setValue('2026-08-31')
    await w.findAll('button').find((b) => b.text().includes('Terapkan')).trigger('click')
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/water/recap?from=2026-08-01&to=2026-08-31')
  })

  // p2: instrumen verifikasi klaim BBM (👁 Detail + Subsidi Tepat) & Berita Acara
  const BBM_QUEUE = [{ id: 7, display_id: 'BBM-007', driver_name: 'BUDI', nopol: 'L 2', nominal: 200000, status: 'verified_ga', ml_anomaly_flag: 0 }]
  const TX_DETAIL = { id: 7, display_id: 'BBM-007', driver_name: 'BUDI', nopol: 'L 2', nominal: 200000, liter: 30, odo_km: 5000, km_per_liter: 10, status: 'verified_ga', photos: [], created_at: '2026-01-02 09:00' }
  // wave-18A: variant langkah 3 — dana sudah caim, menunggu arsip (LPJ)
  const TX_DETAIL_OS = { ...TX_DETAIL, status: 'os_finance' }
  const TX_CROSS = { health_score: 80, flags: [], proof_signals: [], budget_usage_percent: 40, odo_diff: 20, recommendation: 'AMAN' }
  const SUBSIDY_MATCH = {
    verdict: 'match', liter: 30, nominal: 200000, linked: null,
    candidates: [{ id: 9, transaction_id: 'SPBU-0001', transaction_date: '2026-01-02 07:30', volume: 30, amount: 199000, dvol: 0, dnom: 1000, spbu_id: '34.001.03', city: 'SIDOARJO', verification: 'ORISINIL', verdict: 'match' }],
  }
  const ATTESTS = [{ id: 3, period_start: '2026-01-01', period_end: '2026-01-31', record_count: 12, generated_by: 'Finance SBY', generated_at: '2026-02-01 10:00:00' }]

  const financeImpl = (path, opts = {}) => {
    if (path === '/api/water/recap') return Promise.resolve(RECAP)
    if (path === '/api/finance/bbm') {
      const tab = opts?.params?.tab
      const data = tab === 'ready' ? BBM_QUEUE
        : tab === 'history' ? [{ ...BBM_QUEUE[0], status: 'archived', foto_mypertamina_admin: 'myptm.png' }]
          : []
      return Promise.resolve({ data, total: data.length, total_pages: 1 })
    }
    if (path === '/api/queue/payout/7') return Promise.resolve({ status: 'success', msg: 'Dana #7 dicairkan!' })
    if (path.startsWith('/api/queue')) return Promise.resolve(opts?.params?.tab === 'driver_confirm' ? [] : BBM_QUEUE)
    if (path === '/api/subsidy/attest') return Promise.resolve({ attestations: ATTESTS })
    if (path === '/api/transactions/detail/7') return Promise.resolve(TX_DETAIL)
    if (path.startsWith('/api/cross-check')) return Promise.resolve(TX_CROSS)
    if (path.startsWith('/api/subsidy/match')) return Promise.resolve(SUBSIDY_MATCH)
    return Promise.resolve(RECAP)
  }

  async function openReadyClaim(w) {
    await w.findAll('button').find((b) => b.text().includes('Siap dicairkan')).trigger('click')
    await flushPromises()
    const row = w.findAll('tbody tr').find((r) => r.text().includes('BBM-007'))
    if (!row) throw new Error('ready BBM row BBM-007 was not rendered')
    await row.findAll('button').find((b) => b.text().includes('Detail')).trigger('click')
    await flushPromises()
    return row
  }

  it('menampilkan Berita Acara Subsidi Tepat (periode, dibuat oleh, unduh PDF)', async () => {
    Object.defineProperty(window, 'location', { writable: true, value: { href: 'http://localhost/' } })
    const openSpy = vi.spyOn(window, 'open').mockReturnValue(null)
    apiMock.mockImplementation(financeImpl)
    const w = mount(FinanceDashboard)
    await flushPromises()
    expect(w.text()).toContain('Berita Acara Rekonsiliasi — Subsidi Tepat')
    expect(w.text()).toContain('2026-01-01 s/d 2026-01-31')
    expect(w.text()).toContain('Finance SBY')
    await w.findAll('button').find((b) => b.text().includes('PDF')).trigger('click')
    expect(openSpy).toHaveBeenCalledWith('/api/subsidy/attest/3/pdf', '_blank')
  })

  it('👁 Detail klaim BBM: instrumen render + kandidat bisa dijodohkan', async () => {
    apiMock.mockImplementation(financeImpl)
    const w = mount(FinanceDashboard)
    await flushPromises()
    await openReadyClaim(w)

    expect(apiMock).toHaveBeenCalledWith('/api/transactions/detail/7')
    expect(apiMock).toHaveBeenCalledWith('/api/subsidy/match/7')
    expect(w.text()).toContain('📋 Data Klaim')
    expect(w.text()).toContain('🩺 Cross-Check Otomatis')
    expect(w.text()).toContain('⛽ Subsidi Tepat')
    expect(w.text()).toContain('SPBU-0001')

    // Penjodohan: klik 🔗 Jodohkan → konfirmasi → POST /api/subsidy/link/7
    await w.findAll('button').find((b) => b.text() === '🔗 Jodohkan').trigger('click')
    await flushPromises()
    const yes = w.findAll('button').find((b) => b.text() === 'Jodohkan' && !b.text().includes('🔗'))
    await yes.trigger('click')
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/subsidy/link/7', {
      method: 'POST',
      body: { subsidy_transaction_id: 9 },
    })
  })

  // ============================================================
  // wave-18A: kartu atas "Klaim BBM Menunggu Finance" + verifikasi BERTINGKAT
  // ============================================================
  const btnByText = (w, text) => w.findAll('button').find((b) => b.text() === text)
  // dialog konfirmasi (ConfirmDialog) dirender paling akhir → ambil .modal-box terakhir
  const lastDialog = (w) => {
    const boxes = w.findAll('.modal-box')
    return boxes[boxes.length - 1]
  }
  const modalBtn = (w, text) => lastDialog(w).findAll('button').find((b) => b.text() === text)

  // ============================================================
  // v2.68.0: widget Data SPBU — status agen + pencocokan advisory 1 klik
  // ============================================================
  const SUBSIDY_STATUS = {
    count: 138, last_pull: '2026-10-23 06:15:00',
    oldest: '2026-09-22 08:00:00', newest: '2026-10-22 13:00:00',
    coverage: { linked: 2, match: 3, no_record: 1, terbuka: 6 },
  }

  it('widget Data SPBU: jumlah data, rentang, tarik terakhir + chip coverage', async () => {
    apiMock.mockImplementation((path) => (path === '/api/subsidy/status' ? Promise.resolve(SUBSIDY_STATUS) : financeImpl(path)))
    const w = mount(FinanceDashboard)
    await flushPromises()
    const card = w.find('[data-testid="subsidy-data-card"]')
    expect(card.text()).toContain('Data SPBU — Subsidi Tepat')
    expect(card.find('[data-testid="subsidy-count"]').text()).toContain('138')
    expect(card.text()).toContain('2026-09-22 08:00:00')
    expect(card.text()).toContain('otomatis harian 06:15')
    const cov = card.find('[data-testid="subsidy-coverage"]')
    expect(cov.text()).toContain('Dijodohkan')
    expect(cov.text()).toContain('Match: 3')
    expect(cov.text()).toContain('Tanpa catatan: 1')
    // chip 'terbuka' (bukan chip couverture) tidak dirender
    expect(cov.text()).not.toContain('terbuka')
  })

  it('🤝 Cocokkan Klaim Otomatis → POST /api/subsidy/auto-match → muat ulang status & antrean', async () => {
    let statusCalls = 0
    apiMock.mockImplementation((path, opts = {}) => {
      if (path === '/api/subsidy/status') { statusCalls++; return Promise.resolve(SUBSIDY_STATUS) }
      if (path === '/api/subsidy/auto-match') {
        return Promise.resolve({ status: 'success', msg: 'Pencocokan otomatis: 3 match, 0 close, 1 tanpa catatan', match: 3 })
      }
      return financeImpl(path, opts)
    })
    const w = mount(FinanceDashboard)
    await flushPromises()
    const before = statusCalls
    await w.find('[data-testid="subsidy-data-card"]').find('button.btn-primary').trigger('click')
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/subsidy/auto-match', { method: 'POST' })
    expect(w.text()).toContain('✅ Pencocokan otomatis: 3 match')
    expect(statusCalls).toBeGreaterThan(before) // status + antrean direfresh
  })

  // v2.69.0: Login ulang agen (OTP) langsung dari dashboard
  it('🔑 OTP: Minta OTP → status waiting_otp (polling) → input kode → Kirim OTP', async () => {
    vi.useFakeTimers()
    let otpState = { state: 'idle' }
    apiMock.mockImplementation((path, opts = {}) => {
      if (path === '/api/subsidy/status') return Promise.resolve(SUBSIDY_STATUS)
      if (path === '/api/subsidy/otp/status') return Promise.resolve(otpState)
      if (path === '/api/subsidy/otp/request') return Promise.resolve({ status: 'success', state: 'starting', msg: 'Browser login dijalankan — OTP dikirim ke email akun' })
      if (path === '/api/subsidy/otp/submit') return Promise.resolve({ status: 'success', state: 'verifying', msg: 'OTP diteruskan ke agen' })
      return financeImpl(path, opts)
    })
    const w = mount(FinanceDashboard)
    await flushPromises()
    const card = w.find('[data-testid="subsidy-otp"]')
    expect(card.find('[data-testid="otp-state"]').text()).toContain('Idle')
    await card.find('[data-testid="otp-request"]').trigger('click')
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/subsidy/otp/request', { method: 'POST' })
    expect(card.find('[data-testid="otp-state"]').text()).toContain('Browser login')
    expect(card.find('[data-testid="otp-msg"]').text()).toContain('OTP dikirim ke email akun')
    // polling 4 detik → agen sampai halaman OTP (waiting_otp)
    otpState = { state: 'waiting_otp', msg: 'OTP dikirim ke email akun Subsidi Tepat' }
    await vi.advanceTimersByTimeAsync(4000)
    await flushPromises()
    expect(card.find('[data-testid="otp-state"]').text()).toContain('Menunggu OTP')
    const inp = card.find('[data-testid="otp-input"]')
    expect(inp.exists()).toBe(true)
    await inp.find('[data-testid="otp-code"]').setValue('123456')
    await inp.find('[data-testid="otp-submit"]').trigger('click')
    await flushPromises()
    expect(apiMock).toHaveBeenCalledWith('/api/subsidy/otp/submit', { method: 'POST', body: { code: '123456' } })
    expect(card.find('[data-testid="otp-state"]').text()).toContain('Memverifikasi OTP')
    w.unmount()
    vi.useRealTimers()
  })

  it('🔑 OTP: kode tak lengkap → tombol Kirim OTP nonaktif; status done tampil hijau', async () => {
    vi.useFakeTimers()
    let otpState = { state: 'waiting_otp', msg: 'Menunggu kode OTP' }
    let statusCalls = 0
    apiMock.mockImplementation((path) => {
      if (path === '/api/subsidy/status') { statusCalls++; return Promise.resolve(SUBSIDY_STATUS) }
      if (path === '/api/subsidy/otp/status') return Promise.resolve(otpState)
      return financeImpl(path)
    })
    const w = mount(FinanceDashboard)
    await flushPromises()
    const inp = w.find('[data-testid="subsidy-otp"]').find('[data-testid="otp-input"]')
    expect(inp.exists()).toBe(true)
    await inp.find('[data-testid="otp-code"]').setValue('12345')
    expect(inp.find('[data-testid="otp-submit"]').attributes('disabled')).toBeDefined()
    await inp.find('[data-testid="otp-code"]').setValue('123456')
    expect(inp.find('[data-testid="otp-submit"]').attributes('disabled')).toBeUndefined()
    // agen selesai → pesan done + status klaim/data direfresh
    otpState = { state: 'done', msg: '✅ Selesai: 138 transaksi ditarik & diimpor' }
    await vi.advanceTimersByTimeAsync(4000)
    await flushPromises()
    const card = w.find('[data-testid="subsidy-otp"]')
    expect(card.find('[data-testid="otp-msg"]').text()).toContain('Selesai: 138 transaksi')
    expect(statusCalls).toBeGreaterThan(1) // loadSubsidy() dipanggil ulang
    w.unmount()
    vi.useRealTimers()
  })

  it('riwayat pencairan: PDF transaksi, bukti MyPertamina, dan halaman riwayat dapat dibuka', async () => {
    const openSpy = vi.spyOn(window, 'open').mockReturnValue(null)
    apiMock.mockImplementation(financeImpl)
    const w = mount(FinanceDashboard)
    await flushPromises()
    const card = w.find('[data-testid="bbm-quick"]')
    await card.findAll('button').find((b) => b.text().includes('Sudah diproses')).trigger('click')
    await flushPromises()
    const row = card.findAll('tbody tr').find((tr) => tr.text().includes('BBM-007'))
    expect(row).toBeTruthy()
    expect(row.text()).toContain('Bukti MyPertamina tersimpan')
    await row.findAll('button').find((b) => b.text().includes('📄 PDF')).trigger('click')
    await row.findAll('button').find((b) => b.text().includes('Buka bukti')).trigger('click')
    expect(openSpy).toHaveBeenCalledWith('/admin/report/7', '_blank')
    expect(openSpy).toHaveBeenCalledWith('/uploads/myptm.png', '_blank', 'noopener')
  })

  it('BBM Finance menampilkan klaim masuk, siap dicairkan, serta riwayat selesai', async () => {
    apiMock.mockImplementation(financeImpl)
    const w = mount(FinanceDashboard)
    await flushPromises()
    const card = w.find('[data-testid="bbm-quick"]')
    expect(card.text()).toContain('BBM & Kasbon')
    expect(card.text()).toContain('Masuk')
    expect(card.text()).toContain('Siap dicairkan')
    expect(card.text()).toContain('Sudah diproses')
    expect(card.text()).toContain('Kelola kasbon')
    await card.findAll('button').find((b) => b.text().includes('Siap dicairkan')).trigger('click')
    await flushPromises()
    expect(card.text()).toContain('BBM-007')
  })

  it('lampiran Subsidi Tepat dapat diunggah dari Detail per transaksi', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'success', msg: 'Lampiran MyPertamina tersimpan pada transaksi.' }),
    })
    vi.stubGlobal('fetch', fetchMock)
    apiMock.mockImplementation(financeImpl)
    const w = mount(FinanceDashboard)
    await flushPromises()
    const card = w.find('[data-testid="bbm-quick"]')
    await card.findAll('button').find((b) => b.text().includes('Siap dicairkan')).trigger('click')
    await flushPromises()
    const row = card.findAll('tbody tr').find((r) => r.text().includes('BBM-007'))
    await row.findAll('button').find((b) => b.text().includes('Detail')).trigger('click')
    await flushPromises()
    await w.findAll('button').find((b) => b.text().includes('Lampirkan bukti MyPertamina')).trigger('click')
    await flushPromises()
    const uploadModal = w.findAll('.modal-box').find((m) => m.text().includes('Screenshot atau PDF MyPertamina'))
    const file = new File(['evidence'], 'mypertamina.png', { type: 'image/png' })
    Object.defineProperty(uploadModal.find('input[type="file"]').element, 'files', { value: [file] })
    await uploadModal.find('input[type="file"]').trigger('change')
    await uploadModal.findAll('button').find((b) => b.text().includes('Simpan lampiran')).trigger('click')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledOnce()
    const [url, options] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/finance/bbm/7/subsidy-evidence')
    expect(options.method).toBe('POST')
    const uploadedFile = options.body.get('file')
    expect(uploadedFile.name).toBe(file.name)
    expect(uploadedFile.type).toBe(file.type)
    expect(w.text()).toContain('✅ Lampiran MyPertamina tersimpan pada transaksi.')
  })

  it('kartu atas: angka os_finance mengikuti isi antrean driver_confirm', async () => {
    apiMock.mockImplementation((path, opts = {}) => {
      if (path === '/api/queue') return Promise.resolve(opts?.params?.tab === 'driver_confirm' ? BBM_QUEUE : [])
      if (path === '/api/water/recap') return Promise.resolve(RECAP)
      if (path === '/api/subsidy/attest') return Promise.resolve({ attestations: [] })
      return Promise.resolve(RECAP)
    })
    const w = mount(FinanceDashboard)
    await flushPromises()
    const figs = w.find('[data-testid="bbm-quick-figures"]').text()
    expect(figs).toContain('1') // 1 os_finance menunggu LPJ
  })

  it('modal detail (verified_ga): chip bertingkat menyala di langkah 2 + tombol Disbursement, PDF tampil', async () => {
    apiMock.mockImplementation(financeImpl)
    const w = mount(FinanceDashboard)
    await flushPromises()
    await openReadyClaim(w)

    const chips = w.find('[data-testid="bbm-stage-chips"]').findAll('.stage-chip')
    expect(chips.length).toBe(3)
    expect(chips[0].classes()).toContain('on') // 1 Verifikasi GA (selesai)
    expect(chips[1].classes()).toContain('on') // 2 Pencairan ← langkah aktif
    expect(chips[2].classes()).not.toContain('on')
    expect(w.text()).toContain('2️⃣ Pencairan (Finance)')

    // aksi kontekstual: Disbursement, bukan Arsipkan
    expect(btnByText(w, '💰 Disbursement — Cairkan')).toBeTruthy()
    expect(btnByText(w, '📦 Arsipkan')).toBeFalsy()

    // 📄 PDF per transaksi (status bukan pending) — modal render paling akhir, jadi ambil tombol PDF terakhir
    const openSpy = vi.spyOn(window, 'open').mockReturnValue(null)
    await w.findAll('button').filter((b) => b.text() === '📄 PDF').pop().trigger('click')
    await flushPromises()
    expect(openSpy).toHaveBeenCalledWith('/admin/report/7', '_blank')
  })

  it('💰 Disbursement — Cairkan: ask() + PIN/catatan opsional → POST /api/queue/payout + reload kartu', async () => {
    apiMock.mockImplementation(financeImpl)
    const w = mount(FinanceDashboard)
    await flushPromises()
    await openReadyClaim(w)

    const detailCallsBefore = apiMock.mock.calls.filter(([p]) => p === '/api/transactions/detail/7').length
    await modalBtn(w, '💰 Disbursement — Cairkan').trigger('click')
    await flushPromises()

    // dialog konfirmasi dengan input opsional (PIN/catatan)
    const dlg = lastDialog(w)
    expect(dlg.text()).toContain('Disbursement — Pencairan klaim')
    const note = dlg.find('textarea')
    expect(note.attributes('placeholder')).toContain('PIN')
    await note.setValue('siap cair')

    await modalBtn(w, '💰 Cairkan').trigger('click')
    await flushPromises()

    expect(apiMock).toHaveBeenCalledWith('/api/queue/payout/7', { method: 'POST' })
    // kartu detail direload setelah sukses
    const detailCallsAfter = apiMock.mock.calls.filter(([p]) => p === '/api/transactions/detail/7').length
    expect(detailCallsAfter).toBeGreaterThan(detailCallsBefore)
    // pesan hasil server di bawah modal
    expect(w.text()).toContain('✅ Dana #7 dicairkan!')
  })

  it('os_finance: LPJ diteruskan ke Kasbon tanpa aksi Arsipkan', async () => {
    apiMock.mockImplementation((path, opts = {}) => {
      if (path === '/api/transactions/detail/7') return Promise.resolve(TX_DETAIL_OS)
      return financeImpl(path, opts)
    })
    const w = mount(FinanceDashboard)
    await flushPromises()
    await openReadyClaim(w)

    expect(w.text()).toContain('Dana sudah cair · lanjutkan LPJ di Kasbon / BBM')
    expect(w.text()).not.toContain('Arsipkan')
    expect(w.findAll('a').some((a) => a.text().includes('Buka kasbon / LPJ'))).toBe(true)
  })

  it('LPJ kasbon verified_ga tampil selesai dan tidak menawarkan pencairan kedua', async () => {
    apiMock.mockImplementation((path, opts = {}) => {
      if (path === '/api/finance/bbm') {
        const data = opts?.params?.tab === 'history'
          ? [{ ...BBM_QUEUE[0], transaction_type: 'CASH_LPJ', status: 'verified_ga', cash_request_id: 13 }]
          : []
        return Promise.resolve({ data, total: data.length, total_pages: 1 })
      }
      if (path === '/api/transactions/detail/7') {
        return Promise.resolve({ ...TX_DETAIL, transaction_type: 'CASH_LPJ', status: 'verified_ga' })
      }
      return financeImpl(path, opts)
    })
    const w = mount(FinanceDashboard)
    await flushPromises()
    const card = w.find('[data-testid="bbm-quick"]')
    await card.findAll('button').find((b) => b.text().includes('Sudah diproses')).trigger('click')
    await flushPromises()
    const row = card.findAll('tbody tr').find((r) => r.text().includes('BBM-007'))
    expect(row.text()).toContain('Kasbon · LPJ')
    await row.findAll('button').find((b) => b.text().includes('Detail')).trigger('click')
    await flushPromises()
    expect(w.text()).toContain('LPJ kasbon disetujui')
    expect(w.text()).not.toContain('Disbursement — Cairkan')
    expect(btnByText(w, '📄 PDF')).toBeTruthy()
  })

  it('status archived → chip 4️⃣ "Selesai — dokumen tersimpan", tanpa aksi payout/arsip', async () => {
    apiMock.mockImplementation((path, opts = {}) => {
      if (path === '/api/transactions/detail/7') return Promise.resolve({ ...TX_DETAIL, status: 'archived' })
      return financeImpl(path, opts)
    })
    const w = mount(FinanceDashboard)
    await flushPromises()
    await openReadyClaim(w)

    expect(w.find('[data-testid="bbm-archived-chip"]').exists()).toBe(true)
    expect(w.text()).toContain('Selesai — dokumen tetap tersimpan')
    expect(btnByText(w, '💰 Disbursement — Cairkan')).toBeFalsy()
    expect(btnByText(w, '📦 Arsipkan')).toBeFalsy()
  })

  it('409 payout (klaim anomali belum clear GA) → pesan error tampil di bawah modal', async () => {
    apiMock.mockImplementation((path, opts = {}) => {
      if (path === '/api/queue/payout/7') {
        const err = new Error('Transaksi BBM-007 ber-flag anomali — wajib di-clear GA (verifikasi foto penuh) sebelum pencairan.')
        err.status = 409
        throw err
      }
      return financeImpl(path, opts)
    })
    const w = mount(FinanceDashboard)
    await flushPromises()
    await openReadyClaim(w)
    await btnByText(w, '💰 Disbursement — Cairkan').trigger('click')
    await flushPromises()
    await btnByText(w, '💰 Cairkan').trigger('click')
    await flushPromises()
    expect(w.text()).toContain('Pencairan ditahan — Transaksi BBM-007 ber-flag anomali')
  })
})
