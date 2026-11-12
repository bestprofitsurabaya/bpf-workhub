<script setup>
/**
 * Realisasi Pengeluaran (v2.99.0).
 *
 * Menjawab: berapa uang yang benar-benar terpakai tahun ini, terdiri dari apa,
 * dan berapa sisa kasbon yang belum dipertanggungjawabkan?
 *
 * Jembatan: Kasbon cair − Realisasi LPJ = Sisa dana di driver.
 * Total realisasi = Pembelian barang diterima + Realisasi LPJ.
 * Kasbon BUKAN pengeluaran final (hanya dana muka) — lihat routes_expense.py.
 */
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { useAuthStore } from '../stores/auth'
import PageHeader from '../components/PageHeader.vue'
import ReportMeta from '../components/ReportMeta.vue'
import LoadingState from '../components/LoadingState.vue'
import ErrorState from '../components/ErrorState.vue'

const auth = useAuthStore()
const loading = ref(true)
const err = ref('')
const notice = ref('')
const generatedAt = ref('')

// Fase 3 (v2.102.0): periode datang dari context bar /cash (rentang tanggal),
// dipetakan ke tahun + bulan karena rekap pengeluaran dihitung per tahun.
const props = defineProps({ scope: { type: Object, default: null } })
const emit = defineEmits(['open-tab'])

function monthsFromScope(scope) {
  if (!scope?.start || !scope?.end) return null
  const y = Number(scope.end.slice(0, 4))
  const sy = Number(scope.start.slice(0, 4))
  const mf = sy === y ? Number(scope.start.slice(5, 7)) : 1
  const mt = Math.min(12, Math.max(mf, Number(scope.end.slice(5, 7))))
  return { year: y, monthFrom: mf, monthTo: mt, clipped: sy !== y }
}

const NAMA_BULAN = ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des']
const now = new Date()
const _initial = monthsFromScope(props.scope)
const year = ref(_initial?.year ?? now.getFullYear())
const branch = ref(auth.role === 'admin' ? 'ALL' : (auth.user?.branch_code || ''))
// Server menentukan cakupan (v2.99.1): hanya Admin Pusat / Finance HO yang
// boleh memilih "Semua Cabang". Finance cabang terkunci ke cabangnya.
const allBranches = ref(auth.role === 'admin')
const monthFrom = ref(_initial?.monthFrom ?? 1)
const monthTo = ref(_initial?.monthTo ?? (now.getFullYear() === year.value ? now.getMonth() + 1 : 12))
const clipped = ref(!!_initial?.clipped)
const branches = ref([])

const recap = ref(null)
const display = ref(null)
const outstanding = ref({ total: 0, count: 0 })
const perBranchRaw = ref({})
const errors = ref({})

const zeros = () => Array(12).fill(0)
const vec = (obj, key) => (Array.isArray(obj?.[key]) ? obj[key] : zeros())
const sumSlice = (arr, from = monthFrom.value, to = monthTo.value) =>
  arr.slice(from - 1, to).reduce((a, b) => a + (Number(b) || 0), 0)

const fmtRupiah = (n) => 'Rp ' + new Intl.NumberFormat('id-ID').format(Math.round(Number(n) || 0))
const pct = (part, whole) => (whole > 0 ? ((part / whole) * 100).toFixed(1) + '%' : '—')

const rowsBulan = computed(() => {
  const po = vec(display.value, 'po')
  const kasbon = vec(display.value, 'kasbon')
  const lpj = vec(display.value, 'lpj')
  return Array.from({ length: monthTo.value - monthFrom.value + 1 }, (_, k) => {
    const i = monthFrom.value - 1 + k
    return {
      month: i + 1,
      label: NAMA_BULAN[i],
      po: po[i] || 0,
      kasbon: kasbon[i] || 0,
      lpj: lpj[i] || 0,
      sisa: (kasbon[i] || 0) - (lpj[i] || 0),
      total: (po[i] || 0) + (lpj[i] || 0),
    }
  })
})

const totals = computed(() => {
  const po = sumSlice(vec(display.value, 'po'))
  const kasbon = sumSlice(vec(display.value, 'kasbon'))
  const lpj = sumSlice(vec(display.value, 'lpj'))
  return { po, kasbon, lpj, sisa: kasbon - lpj, total: po + lpj }
})

const perBranch = computed(() => {
  const whole = totals.value.total
  return Object.entries(perBranchRaw.value).map(([code, v]) => {
    const po = sumSlice(vec(v, 'po'))
    const kasbon = sumSlice(vec(v, 'kasbon'))
    const lpj = sumSlice(vec(v, 'lpj'))
    const total = po + lpj
    return { code, name: v.name, po, kasbon, lpj, total, share: pct(total, whole) }
  }).sort((a, b) => b.total - a.total)
})

const periodLabel = computed(() =>
  `${NAMA_BULAN[monthFrom.value - 1]}–${NAMA_BULAN[monthTo.value - 1]} ${year.value}`)

const isYtd = computed(() =>
  year.value === now.getFullYear() && monthTo.value === now.getMonth() + 1 && monthFrom.value === 1)

const scopeLabel = computed(() => {
  if (branch.value === 'ALL') return 'Semua cabang aktif'
  const b = branches.value.find((x) => x.code === branch.value)
  return b ? `${b.code} — ${b.name}` : branch.value
})

const pesanErrCabang = computed(() =>
  Object.entries(errors.value).map(([c, e]) => `${c}: ${e}`).join(' · '))

async function load() {
  loading.value = true
  err.value = ''
  try {
    const d = await api(`/api/expenses/recap?year=${year.value}&branch=${branch.value}`)
    recap.value = d
    display.value = d.display || { name: '—', po: [], kasbon: [], lpj: [], total: [] }
    branches.value = d.branches || []
    perBranchRaw.value = branch.value === 'ALL' ? (d.per_branch || {}) : {}
    errors.value = d.errors || {}
    allBranches.value = d.scope?.all_branches ?? (auth.role === 'admin')
    if (!allBranches.value && d.selected && d.selected !== 'ALL') branch.value = d.selected
    outstanding.value = d.outstanding || { total: 0, count: 0 }
    generatedAt.value = new Date().toLocaleString('id-ID')
  } catch (e) {
    err.value = e?.data?.error || e?.message || 'Gagal memuat rekap pengeluaran'
  } finally {
    loading.value = false
  }
}

watch(() => props.scope, (s) => {
  const m = monthsFromScope(s)
  if (!m) return
  if (m.year === year.value && m.monthFrom === monthFrom.value && m.monthTo === monthTo.value) return
  year.value = m.year
  monthFrom.value = m.monthFrom
  monthTo.value = m.monthTo
  clipped.value = m.clipped
  load()
})

// === Drill-down ===
const detail = ref({ open: false, month: null, loading: false, error: '', sections: [] })
const DETAIL_CATS = [['po', '🛒 Pembelian Barang'], ['kasbon', '💵 Kasbon Cair'], ['lpj', '📋 Realisasi LPJ']]

async function openDetail(month) {
  detail.value = { open: true, month, loading: true, error: '', sections: [] }
  try {
    const results = await Promise.all(DETAIL_CATS.map(([category]) =>
      api('/api/expenses/detail', { params: { year: year.value, month, branch: branch.value, category } })
    ))
    detail.value.sections = results.map((r, i) => ({
      key: DETAIL_CATS[i][0],
      label: DETAIL_CATS[i][1],
      rows: r.rows || [],
      total: r.total || 0,
      errors: r.errors || {},
    }))
  } catch (e) {
    detail.value.error = e?.data?.error || e?.message || 'Gagal memuat rincian'
  } finally {
    detail.value.loading = false
  }
}

function closeDetail() { detail.value.open = false }

// === CSV ===
function csvCell(v) {
  const s = String(v ?? '')
  return /[",\n;]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s
}

function exportCsv() {
  notice.value = ''
  if (!rowsBulan.value.length) { notice.value = 'Tidak ada data untuk diekspor.'; return }
  const header = ['Bulan', 'Pembelian Barang', 'Kasbon Cair', 'Realisasi LPJ', 'Sisa Kasbon', 'Total Realisasi']
  const lines = [
    [`Realisasi Pengeluaran ${scopeLabel.value}`, '', '', '', '', ''].map(csvCell).join(','),
    [`Periode ${periodLabel.value}`, '', '', '', '', ''].map(csvCell).join(','),
    header.join(','),
    ...rowsBulan.value.map((r) => [r.label, r.po, r.kasbon, r.lpj, r.sisa, r.total].map(csvCell).join(',')),
    ['TOTAL', totals.value.po, totals.value.kasbon, totals.value.lpj, totals.value.sisa, totals.value.total].map(csvCell).join(','),
  ]
  const blob = new Blob(['\ufeff' + lines.join('\n')], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `realisasi_pengeluaran_${branch.value}_${year.value}_${monthFrom.value}-${monthTo.value}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(load)
</script>

<template>
  <div>
    <PageHeader icon="📊" title="Realisasi Pengeluaran"
                subtitle="Uang yang benar-benar terpakai: pembelian diterima + LPJ BBM, dengan jembatan kasbon">
      <div v-if="allBranches" class="field" style="width:190px;">
        <select class="select" v-model="branch" @change="load">
          <option value="ALL">🏭 Semua Cabang</option>
          <option v-for="b in branches" :key="b.code" :value="b.code">{{ b.name }}</option>
        </select>
      </div>
      <div v-else class="field" style="width:190px;">
        <label>Cabang</label>
        <input class="input" :value="scopeLabel" disabled />
      </div>
    </PageHeader>

    <div v-if="notice" class="alert" style="margin-bottom:12px;">ℹ️ {{ notice }}</div>

    <div v-if="loading"><LoadingState :rows="5" label="Memuat rekap pengeluaran…" /></div>
    <div v-else-if="err"><ErrorState :message="err" @retry="load" /></div>
    <template v-else>
      <ReportMeta
        title="Realisasi Pengeluaran"
        question="Berapa uang yang benar-benar terpakai pada periode ini, terdiri dari apa, dan berapa kasbon yang belum dipertanggungjawabkan?"
        :period="periodLabel + (isYtd ? ' (YTD)' : '')"
        :scope="scopeLabel"
        source="purchase_orders + po_receipts, fuel_cash_requests, transactions (CASH_LPJ)"
        basis="PO: qty diterima × harga (tanggal order) · Kasbon cair: handover_at terisi · LPJ sah: CASH_LPJ verified_ga/archived"
        exclusions="Air minum & overtime belum menyimpan nominal; kasbon bukan pengeluaran final"
        :generated-at="generatedAt"
        :rows="rowsBulan.length + ' bulan'"
      />

      <div class="card card-pad" style="margin-bottom:14px;">
        <div class="row" style="flex-wrap:wrap;gap:10px;align-items:center;">
          <b>📅 {{ periodLabel }}</b>
          <span v-if="clipped" class="muted" style="font-size:11px;color:var(--danger);">
            Rekap pengeluaran dihitung per tahun; rentang lintas tahun dipotong ke {{ year }}.
          </span>
          <div class="spacer"></div>
          <button class="btn" @click="exportCsv">⬇️ CSV</button>
          <button class="btn btn-primary" @click="load">🔄 Muat ulang</button>
        </div>
      </div>

      <div v-if="pesanErrCabang" class="alert alert-error" style="margin-bottom:12px;">
        ⚠️ Sebagian cabang gagal dihitung: {{ pesanErrCabang }}
      </div>

      <!-- Jembatan kas + kartu realisasi. v2.104.0: tiap angka bisa diklik ke
           daftar baris sumber di tab operasional (bukan sekadar angka). -->
      <div class="row" style="gap:12px;flex-wrap:wrap;margin-bottom:12px;">
        <button type="button" class="card card-pad grow aq-link" style="min-width:190px;text-align:left;"
             data-testid="open-kasbon-cair"
             @click="emit('open-tab', { tab: 'kasbon', filters: { kasbon: 'cair' }, label: 'Kasbon cair' })">
          <div class="muted" style="font-size:12px;">💵 Kasbon BBM Cair</div>
          <b style="font-size:21px;">{{ fmtRupiah(totals.kasbon) }}</b>
          <div class="muted" style="font-size:10px;">Dana muka — belum tentu terpakai · klik untuk lihat baris</div>
        </button>
        <button type="button" class="card card-pad grow aq-link" style="min-width:190px;text-align:left;"
             data-testid="open-lpj-sah"
             @click="emit('open-tab', { tab: 'bbm', filters: { bbmTab: 'history', bbmType: 'CASH_LPJ' }, label: 'LPJ sah' })">
          <div class="muted" style="font-size:12px;">📋 Realisasi LPJ</div>
          <b style="font-size:21px;">{{ fmtRupiah(totals.lpj) }}</b>
          <div class="muted" style="font-size:10px;">Dipertanggungjawabkan driver · klik untuk lihat baris</div>
        </button>
        <button type="button" class="card card-pad grow aq-link" style="min-width:190px;text-align:left;"
             :style="totals.sisa < 0 ? 'border-color:var(--danger)' : ''"
             data-testid="open-sisa-kasbon"
             @click="emit('open-tab', { tab: 'kasbon', filters: { kasbon: 'cair' }, label: 'Sisa Kasbon' })">
          <div class="muted" style="font-size:12px;">↔️ Sisa Kasbon</div>
          <b style="font-size:21px;" :style="totals.sisa < 0 ? 'color:var(--danger)' : ''">{{ fmtRupiah(totals.sisa) }}</b>
          <div class="muted" style="font-size:10px;">Kasbon cair − LPJ · klik untuk lihat baris</div>
        </button>
        <button type="button" class="card card-pad grow aq-link" style="min-width:190px;text-align:left;"
             :style="outstanding.total > 0 ? 'border-color:#d97706' : ''"
             data-testid="open-kasbon-queue"
             @click="emit('open-tab', { tab: 'kasbon', filters: { kasbon: 'outstanding' }, label: 'Dana di Driver' })">
          <div class="muted" style="font-size:12px;">🚗 Dana di Driver</div>
          <b style="font-size:21px;color:#d97706;">{{ fmtRupiah(outstanding.total) }}</b>
          <div class="muted" style="font-size:10px;">{{ outstanding.count }} kasbon belum LPJ · klik untuk buka antrean</div>
        </button>
      </div>

      <div class="row" style="gap:12px;flex-wrap:wrap;margin-bottom:16px;">
        <div class="card card-pad grow" style="min-width:200px;">
          <div class="muted" style="font-size:12px;">🛒 Pembelian Barang (PO diterima)</div>
          <b style="font-size:22px;">{{ fmtRupiah(totals.po) }}</b>
        </div>
        <div class="card card-pad grow" style="min-width:200px;background:var(--primary-soft, rgba(25,103,210,.08));">
          <div class="muted" style="font-size:12px;">Σ Total Realisasi {{ year }}</div>
          <b style="font-size:24px;">{{ fmtRupiah(totals.total) }}</b>
          <div class="muted" style="font-size:10px;">Pembelian diterima + LPJ (bukan kasbon)</div>
        </div>
      </div>

      <!-- Tabel bulanan -->
      <div class="card" style="margin-bottom:16px;">
        <div class="card-pad row" style="border-bottom:1px solid var(--border);gap:8px;">
          <b>📅 Per Bulan — {{ display?.name || '—' }} · {{ periodLabel }}</b>
          <div class="spacer"></div>
          <span class="muted" style="font-size:11px;">Klik “Rincian” untuk melihat transaksi sumber</span>
        </div>
        <div class="table-wrap">
          <table class="table">
            <thead>
              <tr>
                <th>Bulan</th>
                <th style="text-align:right;">Pembelian</th>
                <th style="text-align:right;">Kasbon Cair</th>
                <th style="text-align:right;">Realisasi LPJ</th>
                <th style="text-align:right;">Sisa</th>
                <th style="text-align:right;">Total Realisasi</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in rowsBulan" :key="r.label" :class="{ 'bulan-aktif': r.total > 0 || r.kasbon > 0 }">
                <td>{{ r.label }}</td>
                <td style="text-align:right;">{{ r.po ? fmtRupiah(r.po) : '—' }}</td>
                <td style="text-align:right;">{{ r.kasbon ? fmtRupiah(r.kasbon) : '—' }}</td>
                <td style="text-align:right;">{{ r.lpj ? fmtRupiah(r.lpj) : '—' }}</td>
                <td style="text-align:right;" :style="r.sisa < 0 ? 'color:var(--danger)' : ''">{{ r.sisa ? fmtRupiah(r.sisa) : '—' }}</td>
                <td style="text-align:right;"><b>{{ r.total ? fmtRupiah(r.total) : '—' }}</b></td>
                <td style="text-align:right;"><button class="btn btn-sm" @click="openDetail(r.month)">Rincian</button></td>
              </tr>
              <tr style="font-weight:700;">
                <td>Total {{ periodLabel }}</td>
                <td style="text-align:right;">{{ fmtRupiah(totals.po) }}</td>
                <td style="text-align:right;">{{ fmtRupiah(totals.kasbon) }}</td>
                <td style="text-align:right;">{{ fmtRupiah(totals.lpj) }}</td>
                <td style="text-align:right;">{{ fmtRupiah(totals.sisa) }}</td>
                <td style="text-align:right;">{{ fmtRupiah(totals.total) }}</td>
                <td></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Per cabang -->
      <div v-if="perBranch.length" class="card" style="margin-bottom:16px;">
        <div class="card-pad row" style="border-bottom:1px solid var(--border);">
          <b>🏭 Per Cabang — {{ periodLabel }}</b>
        </div>
        <div class="table-wrap">
          <table class="table">
            <thead>
              <tr>
                <th>Cabang</th>
                <th style="text-align:right;">Pembelian</th>
                <th style="text-align:right;">Kasbon Cair</th>
                <th style="text-align:right;">Realisasi LPJ</th>
                <th style="text-align:right;">Total Realisasi</th>
                <th style="text-align:right;">Porsi</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="b in perBranch" :key="b.code">
                <td><b>{{ b.code }}</b> — {{ b.name }}</td>
                <td style="text-align:right;">{{ fmtRupiah(b.po) }}</td>
                <td style="text-align:right;">{{ fmtRupiah(b.kasbon) }}</td>
                <td style="text-align:right;">{{ fmtRupiah(b.lpj) }}</td>
                <td style="text-align:right;"><b>{{ fmtRupiah(b.total) }}</b></td>
                <td style="text-align:right;">{{ b.share }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Definisi & pengecualian -->
      <div class="card card-pad" style="margin-bottom:16px;">
        <b style="font-size:13px;">ℹ️ Cara membaca laporan ini</b>
        <ul class="muted" style="font-size:12px;margin:8px 0 0;padding-left:18px;line-height:1.7;">
          <li><b>Kasbon cair</b> = uang muka yang sudah diserahkan ke driver (handover_at terisi). Bukan pengeluaran final.</li>
          <li><b>Realisasi LPJ</b> = LPJ kasbon yang sah (verified_ga/archived). Total realisasi = pembelian diterima + LPJ sah.</li>
          <li><b>Sisa kasbon</b> = kasbon cair − LPJ. Nilai negatif berarti LPJ melebihi dana muka dan perlu ditelusuri.</li>
          <li><b>Pembelian barang</b> = qty yang benar-benar diterima × harga item, dikelompokkan menurut tanggal order.</li>
          <li>Air minum dan overtime belum masuk karena sistem belum menyimpan nominalnya — bukan dianggap nol.</li>
        </ul>
      </div>
    </template>

    <!-- Modal drill-down -->
    <div v-if="detail.open" class="rd-overlay" role="dialog" aria-modal="true"
         :aria-label="`Rincian ${NAMA_BULAN[detail.month - 1]} ${year}`"
         @click.self="closeDetail">
      <div class="rd-modal">
        <div class="row" style="justify-content:space-between;margin-bottom:10px;">
          <h3 style="margin:0;">🔎 Rincian {{ NAMA_BULAN[detail.month - 1] }} {{ year }} — {{ scopeLabel }}</h3>
          <button class="btn-icon" aria-label="Tutup" @click="closeDetail">✕</button>
        </div>
        <div v-if="detail.loading" class="muted" style="font-size:12px;">⏳ Memuat rincian…</div>
        <div v-else-if="detail.error" class="alert alert-error">{{ detail.error }}</div>
        <template v-else>
          <div v-for="s in detail.sections" :key="s.key" style="margin-bottom:14px;">
            <div class="row" style="gap:8px;margin-bottom:4px;">
              <b style="font-size:13px;">{{ s.label }}</b>
              <div class="spacer"></div>
              <b style="font-size:13px;">{{ fmtRupiah(s.total) }}</b>
            </div>
            <div v-if="Object.keys(s.errors).length" class="muted" style="font-size:11px;color:var(--danger);">
              Gagal: {{ Object.entries(s.errors).map(([c, e]) => `${c}: ${e}`).join(' · ') }}
            </div>
            <div v-if="!s.rows.length" class="muted" style="font-size:11px;">Tidak ada baris.</div>
            <div v-else class="table-wrap">
              <table class="table">
                <thead><tr><th>Cabang</th><th>Tanggal</th><th>Referensi</th><th>Keterangan</th><th style="text-align:right;">Nilai</th></tr></thead>
                <tbody>
                  <tr v-for="(r, i) in s.rows" :key="s.key + i">
                    <td>{{ r.branch_code }}</td>
                    <td class="muted" style="font-size:11px;">{{ r.date }}</td>
                    <td><b>{{ r.ref }}</b></td>
                    <td>{{ r.description }}<span v-if="r.party"> · {{ r.party }}</span></td>
                    <td style="text-align:right;">{{ fmtRupiah(r.amount) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.table { width: 100%; border-collapse: collapse; font-size: 13px; }
/* Kartu KPI yang bisa diklik → daftar baris sumber (v2.104.0). */
.aq-link {
  cursor: pointer; text-align: left; font-size: inherit; color: inherit;
  transition: border-color .15s ease, transform .15s ease;
}
.aq-link:hover { transform: translateY(-1px); border-color: var(--primary, #2563eb); }
.aq-link:focus-visible { outline: 2px solid var(--primary, #2563eb); outline-offset: 2px; }
.table th, .table td { padding: 7px 10px; border-bottom: 1px solid var(--border, #e5e7eb); }
.table th { text-align: left; font-weight: 600; }
.bulan-aktif td { background: var(--primary-soft, rgba(25,103,210,.05)); }
.rd-overlay {
  position: fixed; inset: 0; background: rgba(15, 23, 42, .55); z-index: 120;
  display: flex; align-items: flex-start; justify-content: center; padding: 24px 12px; overflow: auto;
}
.rd-modal {
  background: var(--surface, #fff); border-radius: 14px; padding: 16px;
  width: min(960px, 100%); box-shadow: 0 20px 50px rgba(15, 23, 42, .3);
}
</style>
