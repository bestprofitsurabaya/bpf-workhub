<script setup>
import { computed, defineAsyncComponent, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import { useAuthStore } from '../stores/auth'
import { useStepupStore } from '../stores/stepup'
import Modal from '../components/Modal.vue'
import LoadingState from '../components/LoadingState.vue'
import ErrorState from '../components/ErrorState.vue'
import PageHeader from '../components/PageHeader.vue'
import BbmKasbonPanel from '../components/BbmKasbonPanel.vue'
import BbmActionQueue from '../components/BbmActionQueue.vue'
import BbmWorkspaceKpi from '../components/BbmWorkspaceKpi.vue'
import { formatDateTime } from '../utils/format.js'

// Fase 1 (v2.100.0): tiga laporan lama dirender di dalam meja kerja ini.
// Dimuat malas agar tab BBM tidak ikut menanggung chart.js.
const RekapReport = defineAsyncComponent(() => import('./RekapView.vue'))
const ExpensesReport = defineAsyncComponent(() => import('./ExpensesView.vue'))
const AnalyticsReport = defineAsyncComponent(() => import('./AnalyticsView.vue'))

const stepup = useStepupStore()

// Fase 3 (v2.103.0): antrean hanya menunjuk tab; aksi uang tetap di panel tab.
// v2.104.0: antrean boleh bringing baris yang perlu ditindak, dan tab tujuan
// bisa difilter — jadi "angka → baris → aksi" benar-benar jalan.
// Filter yang bisa dibawa:
//   { tab, filters: { kasbon?: 'cair'|'outstanding'|'all',
//                      bbmTab?: 'incoming'|'ready'|'confirm'|'history',
//                      bbmType?: 'CLAIM'|'CASH_LPJ' } }
const kasbonFilter = ref('all')
const bbmFocus = ref({ tab: '', type: '' })

const KASBON_FILTERS = {
  all: { label: 'Semua kasbon', test: () => true },
  cair: { label: 'Kasbon cair (dana diserahkan)', test: (c) => !!c.handover_at },
  outstanding: {
    label: 'Dana di driver (belum LPJ)',
    test: (c) => ['FUNDS_WITH_DRIVER', 'LPJ_SUBMITTED'].includes(c.status),
  },
}

const visibleCash = computed(() => {
  const f = KASBON_FILTERS[kasbonFilter.value] || KASBON_FILTERS.all
  return (cash.value || []).filter(f.test)
})

// Catatan filter per tab — supaya catatan dari tab lain tidak ikut terbawa.
const kasbonNote = computed(() =>
  kasbonFilter.value === 'all' ? '' : `Filter: ${KASBON_FILTERS[kasbonFilter.value].label}`)

const bbmNote = computed(() => {
  const parts = []
  if (bbmFocus.value.tab) parts.push(bbmFocus.value.tab)
  if (bbmFocus.value.type) parts.push(bbmFocus.value.type)
  return parts.length ? `Filter: ${parts.join(' · ')}` : ''
})

function applyFilters(filters) {
  if (!filters) return
  if (filters.kasbon && KASBON_FILTERS[filters.kasbon]) {
    kasbonFilter.value = filters.kasbon
  }
  if (filters.bbmTab || filters.bbmType) {
    bbmFocus.value = {
      tab: filters.bbmTab || bbmFocus.value.tab,
      type: filters.bbmType || bbmFocus.value.type,
    }
  }
}

function openQueue(payload) {
  // Backward-compatible: string (nama tab) atau objek { tab, filters }.
  const p = typeof payload === 'string' ? { tab: payload } : (payload || {})
  let tab = p.tab
  // Tab SubsidiTepat hanya untuk Finance/Admin — jangan buka tab yang tidak
  // ada (biarpun URL/parameter minta), cukup arahkan ke tab BBM.
  if (tab === 'subsidy' && !isFinance) tab = 'bbm'
  if (['bbm', 'kasbon', 'subsidy', 'laporan'].includes(tab)) activeSection.value = tab
  applyFilters(p.filters)
}

const auth = useAuthStore()

// Fase 3 (v2.102.0): satu periode untuk semua laporan di meja kerja ini.
// Sebelumnya Rekap & Analisis default 30 hari, Realisasi default YTD — angka
// tiga tab bisa berasal dari rentang berbeda tanpa disadari.
function localISO(d) {
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${mm}-${dd}`
}
const _scopeParams = new URLSearchParams(window.location.search)
const reportStart = ref(_scopeParams.get('start') || localISO(new Date(Date.now() - 29 * 864e5)))
const reportEnd = ref(_scopeParams.get('end') || localISO(new Date()))
const reportScope = computed(() => ({ start: reportStart.value, end: reportEnd.value }))

function scopePreset(key) {
  const now = new Date()
  if (key === '7') reportStart.value = localISO(new Date(Date.now() - 6 * 864e5))
  else if (key === '30') reportStart.value = localISO(new Date(Date.now() - 29 * 864e5))
  else if (key === 'month') reportStart.value = localISO(new Date(now.getFullYear(), now.getMonth(), 1))
  else if (key === 'year') reportStart.value = `${now.getFullYear()}-01-01`
  reportEnd.value = localISO(now)
}

// Periode ikut tersimpan di URL agar bookmark/refresh menampilkan angka yang sama.
watch([reportStart, reportEnd], ([s, e]) => {
  const p = new URLSearchParams(window.location.search)
  p.set('start', s); p.set('end', e); p.set('tab', 'laporan')
  window.history.replaceState(null, '', `${window.location.pathname}?${p.toString()}`)
})

const cash = ref([])
const loading = ref(true)
const err = ref('')
const daily = ref({ code: '', manual_mode: false })
const dailyMsg = ref('')
const busy = ref(false)
// v2.104.0: naikkan untuk memuat ulang antrean setelah aksi dari antrean.
const queueReloadKey = ref(0)

const action = ref(null) // { kind, id }
const form = ref({ amount: '', reason: '', notes: '' })
const detailItem = ref(null) // cash detail modal
const detailData = ref(null)
const detailLoading = ref(false)

const isGa = ['ga', 'admin'].includes(auth.role)
const isFinance = ['finance', 'admin'].includes(auth.role)
const canEditDaily = isFinance

// Menu bar modul: BBM | Kasbon & LPJ | SubsidiTepat (SPBU + OTP).
// Deep link ?tab=kasbon dipakai kartu prioritas Dashboard Finance.
const _params = new URLSearchParams(window.location.search)
const _requestedTab = _params.get('tab')
const _validTabs = ['bbm', 'kasbon', 'subsidy', 'laporan']
const activeSection = ref(
  _validTabs.includes(_requestedTab) && (_requestedTab !== 'subsidy' || isFinance) ? _requestedTab : 'bbm',
)

// Sub-tab laporan. Definisi & filter masih milik masing-masing halaman sampai
// Fase 2 menyatukan periode/cabang; sub-tab yang tidak boleh dilihat role
// tidak dirender sama sekali (mis. Realisasi untuk GA).
const REPORT_TABS = [
  { key: 'rekap', label: 'Rekap Klaim BBM', icon: '📋', roles: ['ga', 'finance', 'admin'], comp: RekapReport },
  { key: 'realisasi', label: 'Realisasi Pengeluaran', icon: '📊', roles: ['finance', 'admin'], comp: ExpensesReport },
  { key: 'analisis', label: 'Analisis BBM & Armada', icon: '📈', roles: ['ga', 'finance', 'admin'], comp: AnalyticsReport },
]
const reportViews = computed(() => REPORT_TABS.filter((t) => t.roles.includes(auth.role)))
const _requestedView = _params.get('view')
const reportView = ref(
  reportViews.value.some((t) => t.key === _requestedView) ? _requestedView : reportViews.value[0]?.key,
)
const activeReport = computed(
  () => reportViews.value.find((t) => t.key === reportView.value) || reportViews.value[0],
)

// v2.105.0: ?tab= & ?view= dibaca sekali saat mount. Tanpa watcher, klik menu
// atau redirect /rekap,/expenses,/analytics saat SUDAH di /cash tidak
// berpindah tab (komponen tidak mount ulang). Watcher ini membuat deep link
// tetap reaktif; guard `route` agar aman di unit test tanpa router.
const route = useRoute()
if (route) {
  watch(() => route.query, (q) => {
    const tab = String(q?.tab || '')
    if (_validTabs.includes(tab) && (tab !== 'subsidy' || isFinance)) {
      activeSection.value = tab
    }
    const view = String(q?.view || '')
    if (view && reportViews.value.some((t) => t.key === view)) {
      reportView.value = view
    }
  })
}

const STEPS = ['DRAFT', 'GA_APPROVED', 'FINANCE_APPROVED', 'FUNDS_WITH_DRIVER', 'LPJ_SUBMITTED', 'COMPLETED']
const STEP_ICONS = ['📝', '✅', '💰', '🤝', '📋', '🎉']
const STATUS_BADGE = {
  DRAFT: 'badge-gray', GA_APPROVED: 'badge-blue', FINANCE_APPROVED: 'badge-amber',
  FUNDS_WITH_DRIVER: 'badge-green', LPJ_SUBMITTED: 'badge-blue', COMPLETED: 'badge-green', REJECTED: 'badge-red',
}
const STATUS_LABEL = {
  DRAFT: 'Menunggu persetujuan GA',
  GA_APPROVED: 'Menunggu persetujuan Finance',
  FINANCE_APPROVED: 'Siap diserahkan ke driver',
  FUNDS_WITH_DRIVER: 'Dana di driver · menunggu LPJ',
  LPJ_SUBMITTED: 'LPJ menunggu verifikasi GA',
  COMPLETED: 'Selesai',
  REJECTED: 'Ditolak',
}
const queueBadges = ref({})
const kasbonSummary = computed(() => {
  const count = (statuses) => cash.value.filter((c) => statuses.includes(c.status)).length
  return [
    { label: 'Menunggu GA', n: count(['DRAFT']), tone: 'badge-gray' },
    { label: 'Menunggu Finance', n: count(['GA_APPROVED']), tone: 'badge-blue' },
    { label: 'Dana di driver', n: count(['FINANCE_APPROVED', 'FUNDS_WITH_DRIVER']), tone: 'badge-amber' },
    { label: 'LPJ menunggu', n: count(['LPJ_SUBMITTED']), tone: 'badge-purple' },
  ]
})
const stepOf = (s) => { const i = STEPS.indexOf(s); return i < 0 ? 0 : i }
const pctOf = (s) => (s === 'COMPLETED' ? 100 : Math.round((stepOf(s) / (STEPS.length - 1)) * 100))
const fmtRp = (n) => 'Rp ' + Number(n || 0).toLocaleString('id-ID')

const MODAL_TITLES = {
  approve_ga: '✅ Approve Kasbon',
  approve_finance: '💰 Approve Finance',
  handover: '🤝 Serah Terima ke Driver',
  reject: '⛔ Tolak Kasbon',
  delete: '🗑 Hapus Kasbon',
  edit: '✏️ Edit Kasbon',
  cancel: '↩️ Batal Kasbon',
  reset_lpj: '🔄 Reset LPJ',
  approve_lpj: '✅ Approve LPJ',
  reject_lpj: '❌ Tolak LPJ',
  verify_claim: '✅ Verifikasi Klaim',
}
const modalTitle = computed(() => {
  if (!action.value) return ''
  return `${MODAL_TITLES[action.value.kind] || 'Konfirmasi'} #${action.value.id}`
})

const canAct = computed(() => {
  const a = action.value
  if (!a) return false
  switch (a.kind) {
    case 'approve_ga': case 'handover': case 'approve_lpj': case 'reject_lpj': return isGa
    case 'verify_claim': return isGa
    case 'approve_finance': return isFinance
    case 'reset_lpj': return isFinance
    case 'reject': case 'delete': case 'edit': case 'cancel': return true
    default: return false
  }
})

async function load() {
  loading.value = true; err.value = ''
  try {
    const [history, dc, nav] = await Promise.all([
      api('/api/cash/history'),
      api('/api/cash/daily-code'),
      api('/api/nav/badges').catch(() => null),
    ])
    cash.value = Array.isArray(history) ? history : []
    daily.value = { code: dc.code, manual_mode: !!dc.manual_mode }
    queueBadges.value = nav?.badges || {}
    dailyMsg.value = ''
  } catch (e) { err.value = e.message }
  finally { loading.value = false }
}

async function setDailyCode() {
  if (!daily.value.manual_mode) { alert('⚠️ Mode manual belum diaktifkan. Buka Pengaturan untuk mengubah.'); return }
  const code = parseInt(daily.value.code, 10)
  if (!(code >= 100 && code <= 2000)) { alert('Kode harus 100-2000!'); return }
  busy.value = true
  try {
    const d = await api('/api/cash/daily-code', { method: 'POST', body: { code } })
    dailyMsg.value = '✅ ' + (d.msg || 'Tersimpan')
    load()
  } catch (e) { dailyMsg.value = '❌ ' + e.message }
  finally { busy.value = false }
}

function openAction(kind, item) {
  form.value = { amount: item?.base_amount ?? '', reason: '', notes: '' }
  action.value = { kind, id: item?.id }
}

// v2.104.0: aksi dari baris antrean "Perlu Tindakan" memakai modal & step-up
// yang sama dengan aksi di panel tab — tidak ada jalur aksi kedua.
function onQueueAction(payload) {
  if (!payload?.kind || !payload?.item) return
  openAction(payload.kind, payload.item)
}

async function openDetail(item) {
  detailItem.value = item
  detailLoading.value = true
  detailData.value = null
  try {
    detailData.value = await api(`/api/cash/detail/${item.id}`)
  } catch (e) { alert('❌ Gagal memuat detail: ' + e.message) }
  finally { detailLoading.value = false }
}

// v2.106.0: dokumen resmi per kasbon (bukti pengajuan & pencairan).
// Sebelumnya kasbon satu-satunya modul finance tanpa PDF per transaksi.
function openKasbonPdf(item) {
  if (item?.id) window.open(`/api/cash/${item.id}/pdf`, '_blank', 'noopener')
}

async function submitAction() {
  const a = action.value
  if (!a) return
  if (a.kind === 'reject' && !form.value.reason.trim()) { alert('Alasan penolakan wajib diisi'); return }
  if (a.kind === 'reject_lpj' && !form.value.reason.trim()) { alert('Alasan penolakan LPJ wajib diisi'); return }
  if (a.kind === 'cancel' && !form.value.reason.trim()) { alert('Alasan pembatalan wajib diisi'); return }
  if (a.kind === 'edit' && !(parseInt(form.value.amount, 10) > 0)) { alert('Nominal wajib diisi'); return }
  busy.value = true
  const who = auth.user?.full_name || auth.user?.user_name || ''
  const EP = {
    approve_ga: `/api/cash/approve-ga/${a.id}`,
    approve_finance: `/api/cash/approve-finance/${a.id}`,
    handover: `/api/cash/handover/${a.id}`,
    reject: `/api/cash/reject/${a.id}`,
    delete: `/api/cash/delete/${a.id}`,
    edit: `/api/cash/edit/${a.id}`,
    cancel: `/api/cash/cancel/${a.id}`,
    reset_lpj: `/api/cash/reset-lpj/${a.id}`,
    approve_lpj: `/api/cash/approve-lpj/${a.id}`,
    reject_lpj: `/api/cash/reject-lpj/${a.id}`,
    // v2.104.0: verifikasi klaim langsung dari antrean "Perlu Tindakan".
    // Endpoint + step-up yang sama seperti antrean GA di dashboard.
    verify_claim: `/api/queue/approve-ga/${a.id}`,
  }[a.kind]
  const body = {
    approve_ga: { ga_name: who },
    approve_finance: { finance_name: who },
    handover: { ga_name: who },
    reject: { reason: form.value.reason },
    edit: { base_amount: parseInt(form.value.amount, 10), reason: form.value.reason || 'Revisi dari SPA' },
    cancel: { reason: form.value.reason },
    reset_lpj: { reason: form.value.reason || 'Reset LPJ dari SPA' },
    approve_lpj: { ga_name: who, notes: form.value.notes },
    reject_lpj: { ga_name: who, reason: form.value.reason },
    verify_claim: { ga_name: who },
  }[a.kind]
  // Step-up (ISO/IEC 27001 A.8.5): aksi yang menggerakkan uang kasbon
  // (approve GA, pencairan Finance, serah terima dana ke driver, approve LPJ)
  // wajib konfirmasi PIN ulang bila grant belum ada. Verifikasi klaim (GA)
  // juga wajib step-up — endpointnya memakai `@stepup_required`.
  const STEPUP_KINDS = ['approve_ga', 'approve_finance', 'handover', 'approve_lpj', 'verify_claim']
  try {
    const run = () => api(EP, { method: 'POST', body })
    const d = STEPUP_KINDS.includes(a.kind)
      ? await stepup.require(run, `konfirmasi ${a.kind.replace(/_/g, ' ')} kasbon`)
      : await run()
    alert(d.msg || 'Berhasil')
    action.value = null
    load()
    // Antrean "Perlu Tindakan" ikut berubah setelah aksi — minta muat ulang.
    queueReloadKey.value += 1
  } catch (e) {
    // v2.36.0: ACC berjenjang — jelaskan ke mana pengajuan harus diproses.
    if (e.status === 409 && e.data && e.data.code === 'SUPERVISOR_APPROVAL_REQUIRED') {
      alert('⏳ Menunggu ACC atasan (' + (e.data.pending_at || 'langkah berikutnya') + '). Proses dulu lewat menu ACC Atasan.')
    } else { alert('❌ ' + e.message) }
  }
  finally { busy.value = false }
}

const ACTIONS = {
  DRAFT: [
    { kind: 'approve_ga', label: '✅ GA Approve', cls: 'btn-info', show: () => isGa },
    { kind: 'reject', label: '❌ Tolak', cls: 'btn-danger', show: () => isGa },
    { kind: 'edit', label: '✏️ Edit', cls: 'btn-warning', show: () => true },
    { kind: 'delete', label: '🗑 Hapus', cls: 'btn-secondary', show: () => true },
  ],
  GA_APPROVED: [
    { kind: 'approve_finance', label: '💰 Finance Approve', cls: 'btn-success', show: () => isFinance },
    { kind: 'cancel', label: '↩ Batal', cls: 'btn-warning', show: () => true },
  ],
  FINANCE_APPROVED: [
    { kind: 'handover', label: '🤝 Serahkan ke Driver', cls: 'btn-warning', show: () => isGa },
    { kind: 'cancel', label: '↩ Batal', cls: 'btn-secondary', show: () => true },
  ],
  FUNDS_WITH_DRIVER: [],
  LPJ_SUBMITTED: [
    { kind: 'approve_lpj', label: '✅ Approve LPJ', cls: 'btn-success', show: () => isGa },
    { kind: 'reject_lpj', label: '❌ Tolak LPJ', cls: 'btn-danger', show: () => isGa },
  ],
  COMPLETED: [
    { kind: 'reset_lpj', label: '🔄 Reset LPJ', cls: 'btn-secondary', show: () => isFinance },
  ],
}

onMounted(load)
</script>

<template>
  <div>
    <PageHeader icon="⛽" title="BBM, Kasbon &amp; SPBU"
                subtitle="Satu pusat kerja klaim BBM, kasbon/LPJ, dan data SPBU SubsidiTepat" />

    <BbmActionQueue :reload-key="queueReloadKey" @open="openQueue" @act="onQueueAction" />

    <!-- KPI periode ini — setiap angka bisa diklik ke daftar baris sumber. -->
    <BbmWorkspaceKpi :scope="reportScope" @open="openQueue" />

    <nav class="workspace-tabs" role="tablist" aria-label="Menu BBM, Kasbon, dan SPBU">
      <button type="button" role="tab" :aria-selected="activeSection === 'bbm'" :class="{ active: activeSection === 'bbm' }"
              data-testid="workspace-tab-bbm" @click="activeSection = 'bbm'">
        <span class="workspace-tab-icon" aria-hidden="true">⛽</span>
        <span class="workspace-tab-text">BBM<small>Klaim &amp; pencairan</small></span>
        <span class="workspace-tab-count" aria-label="klaim menunggu">{{ queueBadges.bbm_verify_pending || 0 }} klaim</span>
      </button>
      <button type="button" role="tab" :aria-selected="activeSection === 'kasbon'" :class="{ active: activeSection === 'kasbon' }"
              data-testid="workspace-tab-kasbon" @click="activeSection = 'kasbon'">
        <span class="workspace-tab-icon" aria-hidden="true">🧾</span>
        <span class="workspace-tab-text">Kasbon &amp; LPJ<small>Kode harian &amp; LPJ driver</small></span>
        <span class="workspace-tab-count" aria-label="kasbon menunggu">{{ queueBadges.cash_pending || 0 }} kasbon</span>
      </button>
      <button v-if="isFinance" type="button" role="tab" :aria-selected="activeSection === 'subsidy'" :class="{ active: activeSection === 'subsidy' }"
              data-testid="workspace-tab-subsidy" @click="activeSection = 'subsidy'">
        <span class="workspace-tab-icon" aria-hidden="true">🛡️</span>
        <span class="workspace-tab-text">SubsidiTepat<small>Data SPBU &amp; akses OTP</small></span>
      </button>
      <button type="button" role="tab" :aria-selected="activeSection === 'laporan'" :class="{ active: activeSection === 'laporan' }"
              data-testid="workspace-tab-laporan" @click="activeSection = 'laporan'">
        <span class="workspace-tab-icon" aria-hidden="true">📈</span>
        <span class="workspace-tab-text">Laporan<small>Rekap, realisasi, analisis</small></span>
      </button>
    </nav>

    <!-- Tab 1 — klaim BBM: masuk → siap dicairkan → konfirmasi LPJ → riwayat. -->
    <section v-if="activeSection === 'bbm'" class="workspace-section" aria-label="Transaksi BBM">
      <BbmKasbonPanel active-section="bbm" :focus="bbmFocus" />
      <p v-if="bbmNote" class="muted" style="font-size:11px;" data-testid="filter-note">{{ bbmNote }}</p>
    </section>

    <!-- Tab 2 — kasbon & LPJ: kode harian + seluruh pengajuan kasbon. -->
    <section v-else-if="activeSection === 'kasbon'" class="workspace-section" aria-label="Kasbon dan LPJ">
      <div class="card card-pad kasbon-code">
        <div class="row">
          <div class="workspace-tab-icon" aria-hidden="true">🔢</div>
          <div class="grow">
            <b>Kode Harian</b>
            <div class="muted" style="font-size:12px;">Kode unik pengajuan kasbon hari ini</div>
          </div>
          <input class="input" style="width:130px;text-align:center;font-weight:700;" v-model="daily.code"
                 :readonly="!canEditDaily || !daily.manual_mode" :maxlength="4" />
          <button class="btn btn-primary" v-if="canEditDaily && daily.manual_mode" :disabled="busy" @click="setDailyCode">Simpan</button>
          <span class="muted" style="font-size:12px;">{{ dailyMsg }}</span>
        </div>
      </div>

      <div v-if="loading"><LoadingState :rows="4" label="Memuat data kasbon…" /></div>
      <div v-else-if="err"><ErrorState :message="err" @retry="load" /></div>
      <template v-else>
        <div class="card">
          <div class="card-pad row kasbon-head">
            <b>🧾 Kasbon &amp; LPJ</b>
            <span class="badge badge-blue">{{ visibleCash.length }} pengajuan</span>
            <div class="grow"></div>
            <span v-for="s in kasbonSummary" :key="s.label" class="badge" :class="s.tone">
              {{ s.label }} <b>{{ s.n }}</b>
            </span>
          </div>
          <!-- v2.104.0: filter dari KPI / antrean — daftar bisa disaring. -->
          <div class="card-pad row" style="gap:6px;flex-wrap:wrap;border-bottom:1px solid var(--border);">
            <button v-for="(f, key) in KASBON_FILTERS" :key="key" class="btn btn-sm"
                    :class="kasbonFilter === key ? 'btn-primary' : ''"
                    :data-testid="'kasbon-filter-' + key"
                    @click="kasbonFilter = key">
              {{ f.label }}
            </button>
            <span v-if="kasbonNote" class="muted" style="font-size:11px;" data-testid="kasbon-note">{{ kasbonNote }}</span>
          </div>
          <div v-if="!visibleCash.length" class="empty">Tidak ada pengajuan kasbon pada filter ini.</div>
          <div v-for="c in visibleCash" :key="c.id" class="cash-item">
            <div class="row" style="align-items:center;">
              <div class="grow">
                <div class="row" style="gap:8px;align-items:center;">
                  <b>{{ c.display_id }}</b>
                  <span class="badge" :class="STATUS_BADGE[c.status] || 'badge-gray'">{{ STATUS_LABEL[c.status] || c.status }}</span>
                </div>
                <div class="muted" style="font-size:12px;margin-top:4px;">
                  👤 {{ c.driver_name }} · 🚗 {{ c.nopol || '—' }} · ⛽ {{ c.bbm_type }}
                </div>
                <div style="margin-top:6px;font-weight:700;color:var(--accent);">
                  {{ fmtRp(c.total_amount) }} <small class="muted">(kode: {{ c.daily_code }})</small>
                </div>
              </div>
              <div style="text-align:right;">
                <div class="step-track">
                  <span v-for="(ic, i) in STEP_ICONS" :key="i" class="step-ic"
                        :style="{ color: i <= stepOf(c.status) ? (c.status === 'COMPLETED' ? '#059669' : '#2563eb') : '#cbd5e1' }">{{ ic }}</span>
                </div>
                <div class="progress"><div class="progress-bar" :style="{ width: pctOf(c.status) + '%', background: c.status === 'COMPLETED' ? '#059669' : '#2563eb' }"></div></div>
              </div>
            </div>
            <div class="row" style="margin-top:10px;flex-wrap:wrap;gap:6px;">
              <button class="btn btn-sm" @click="openDetail(c)">👁 Detail</button>
              <button class="btn btn-sm" @click="openKasbonPdf(c)">📄 PDF</button>
              <template v-if="ACTIONS[c.status]">
                <button v-for="a in ACTIONS[c.status].filter(x => x.show())" :key="a.kind"
                        class="btn btn-sm" :class="a.cls" @click="openAction(a.kind, c)">{{ a.label }}</button>
              </template>

              <span v-if="c.status === 'COMPLETED' && !isFinance" class="muted" style="font-size:12px;">🎉 Selesai</span>
            </div>
          </div>
        </div>
      </template>
    </section>

    <!-- Tab 3 — SubsidiTepat: Data SPBU, Berita Acara, dan login ulang agen (OTP). -->
    <section v-else-if="activeSection === 'subsidy'" class="workspace-section" aria-label="Data SPBU SubsidiTepat">
      <BbmKasbonPanel active-section="subsidy" />
    </section>

    <!-- Tab 4 — Laporan: tiga laporan lama dalam satu tempat (Fase 1 v2.100.0). -->
    <section v-else class="workspace-section" aria-label="Laporan dan analisis">
      <div class="card card-pad report-scope" data-testid="report-scope">
        <div class="row" style="flex-wrap:wrap;gap:10px;align-items:flex-end;">
          <div class="field" style="margin:0;width:150px;"><label>Dari</label>
            <input class="input" type="date" v-model="reportStart" data-testid="scope-start" />
          </div>
          <div class="field" style="margin:0;width:150px;"><label>Sampai</label>
            <input class="input" type="date" v-model="reportEnd" data-testid="scope-end" />
          </div>
          <div class="row" style="gap:6px;flex-wrap:wrap;">
            <button class="btn btn-sm" data-testid="scope-preset-7" @click="scopePreset('7')">7 hari</button>
            <button class="btn btn-sm" data-testid="scope-preset-30" @click="scopePreset('30')">30 hari</button>
            <button class="btn btn-sm" data-testid="scope-preset-month" @click="scopePreset('month')">Bulan ini</button>
            <button class="btn btn-sm" data-testid="scope-preset-year" @click="scopePreset('year')">Tahun ini</button>
          </div>
          <div class="spacer"></div>
          <span class="muted" style="font-size:11px;">
            Periode dipakai bersama Rekap, Realisasi, dan Analisis. Cabang mengikuti sesi;
            Finance HO memilih cabang di tab Realisasi.
          </span>
        </div>
      </div>
      <nav class="workspace-tabs report-subtabs" role="tablist" aria-label="Jenis laporan">
        <button v-for="r in reportViews" :key="r.key" type="button" role="tab"
                :aria-selected="reportView === r.key" :class="{ active: reportView === r.key }"
                :data-testid="'report-tab-' + r.key" @click="reportView = r.key">
          <span class="workspace-tab-icon" aria-hidden="true">{{ r.icon }}</span>
          <span class="workspace-tab-text">{{ r.label }}</span>
        </button>
      </nav>
      <component v-if="activeReport" :is="activeReport.comp" :scope="reportScope" @open-tab="openQueue" />
    </section>

    <!-- Cash Detail Modal -->
    <Modal v-if="detailItem" :title="'📋 Detail ' + detailItem.display_id" @close="detailItem = null; detailData = null">
      <div v-if="detailLoading" class="empty" style="padding:16px;">⏳ Memuat detail…</div>
      <div v-else-if="detailData">
        <div class="form-grid">
          <div class="field"><label>Driver</label><input class="input" :value="detailData.driver_name" disabled /></div>
          <div class="field"><label>Nopol</label><input class="input" :value="detailData.nopol" disabled /></div>
          <div class="field"><label>Kendaraan / BBM</label><input class="input" :value="detailData.vehicle_type + ' · ' + detailData.bbm_type" disabled /></div>
          <div class="field"><label>Total</label><input class="input" :value="fmtRp(detailData.total_amount) + ' (kode: ' + detailData.daily_code + ')'" disabled /></div>
          <div class="field"><label>Status</label><input class="input" :value="(detailData.status || '').replace(/_/g, ' ')" disabled /></div>
          <div class="field"><label>Dibuat</label><input class="input" :value="formatDateTime(detailData.created_at)" disabled /></div>
        </div>
        <p v-if="detailData.notes" class="muted" style="font-size:12px;margin:8px 0;">📝 {{ detailData.notes }}</p>
        <div v-if="detailData.lpj" style="margin-top:12px;">
          <h4 style="margin:0 0 8px;">📋 LPJ Terkait</h4>
          <div class="form-grid">
            <div class="field"><label>Transaksi LPJ</label><input class="input" :value="detailData.lpj.display_id || detailData.lpj.id" disabled /></div>
            <div class="field"><label>Nominal</label><input class="input" :value="fmtRp(detailData.lpj.nominal)" disabled /></div>
            <div class="field"><label>ODO</label><input class="input" :value="detailData.lpj.odo_km + ' km'" disabled /></div>
            <div class="field"><label>Status</label><input class="input" :value="detailData.lpj.status" disabled /></div>
          </div>
        </div>
        <div style="margin-top:12px;text-align:right;">
          <button class="btn" @click="openKasbonPdf(detailData || detailItem)">📄 PDF Kasbon</button>
          <button class="btn btn-secondary" @click="detailItem = null; detailData = null">Tutup</button>
        </div>
      </div>
    </Modal>

    <Modal v-if="action" :title="modalTitle" @close="action = null">
      <template v-if="action.kind === 'reject'">
        <div class="field"><label>Alasan penolakan</label><textarea class="input" v-model="form.reason" rows="3" placeholder="Alasan penolakan..."></textarea></div>
      </template>
      <template v-else-if="action.kind === 'cancel'">
        <div class="field"><label>Alasan pembatalan</label><textarea class="input" v-model="form.reason" rows="3" placeholder="Alasan pembatalan..."></textarea></div>
      </template>
      <template v-else-if="action.kind === 'edit'">
        <div class="field"><label>Nominal dasar (tanpa kode unik)</label><input class="input" type="number" v-model="form.amount" placeholder="Contoh: 500000" /></div>
        <div class="field"><label>Alasan revisi</label><textarea class="input" v-model="form.reason" rows="3" placeholder="Alasan revisi..."></textarea></div>
      </template>
      <template v-else-if="action.kind === 'reject_lpj'">
        <div class="field"><label>Alasan penolakan LPJ</label><textarea class="input" v-model="form.reason" rows="3" placeholder="Alasan penolakan..."></textarea></div>
      </template>
      <template v-else-if="action.kind === 'approve_lpj'">
        <div class="field"><label>Catatan verifikasi (opsional)</label><textarea class="input" v-model="form.notes" rows="2" placeholder="Catatan..."></textarea></div>
      </template>
      <div class="row" style="justify-content:flex-end;gap:8px;">
        <button class="btn btn-secondary" @click="action = null">Batal</button>
        <button class="btn btn-primary" :disabled="busy || !canAct" @click="submitAction">Konfirmasi</button>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
.kasbon-code { margin-bottom: 16px; }
.report-subtabs { margin-bottom: 14px; }
.report-scope { margin-bottom: 14px; }
.kasbon-code .workspace-tab-icon { background: var(--primary-soft); }
.kasbon-head { border-bottom: 1px solid var(--border); gap: 8px; }
.cash-item { padding: 14px; border-bottom: 1px solid var(--border); }
.cash-item:last-child { border-bottom: none; }
.step-track { display: flex; gap: 6px; font-size: 11px; justify-content: flex-end; }
.step-ic { filter: grayscale(0); }
.progress { background: var(--border); border-radius: 4px; height: 5px; width: 160px; margin-top: 5px; }
.progress-bar { height: 100%; border-radius: 4px; transition: width .4s ease; }
@media (max-width: 640px) {
  .progress { width: 110px; }
  .kasbon-head { align-items: flex-start; }
}
</style>
