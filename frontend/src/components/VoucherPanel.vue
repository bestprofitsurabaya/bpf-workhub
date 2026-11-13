<script setup>
/**
 * Voucher Rekanan (v2.107.0) — meja kerja finance untuk alur BBM ketiga.
 *
 * Voucher BUKAN klaim (driver tidak menalangi) dan BUKAN kasbon (kantor tidak
 * menyerahkan uang ke driver): SPBU mitra memberi voucher + blanko, driver
 * memakainya, lalu kantor membayar mitra per periode. Karena itu:
 *   - pemakaian diverifikasi GA (beban BBM dihitung sekali),
 *   - tagihan periode mengunci voucher (settlement_id) agar tidak ditagih dua kali,
 *   - pembayaran tagihan adalah kas keluar, bukan beban baru.
 */
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import Modal from './Modal.vue'
import { useStepupStore } from '../stores/stepup'
import { useAuthStore } from '../stores/auth'
import { formatDateTime } from '../utils/format.js'

const stepup = useStepupStore()
const auth = useAuthStore()

const fmtRp = (n) => 'Rp ' + (Number(n) || 0).toLocaleString('id-ID')
const fmtDate = (v) => (v ? String(v).slice(0, 10).split('-').reverse().join('-') : '-')
const localISO = (d) => {
  const p = (x) => String(x).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

const loading = ref(true)
const busy = ref(false)
const msg = ref('')
const err = ref('')

const summary = ref(null)
const pending = ref([])
const unsettled = ref([])
const settlements = ref([])
const selectedIds = ref([])
const detail = ref(null)
const detailLoading = ref(false)

const start = ref(localISO(new Date(Date.now() - 29 * 864e5)))
const end = ref(localISO(new Date()))
const form = ref({ invoice_no: '', notes: '', partner: '' })

const isFinance = computed(() => ['finance', 'admin'].includes(auth.role))
const isGa = computed(() => ['ga', 'admin'].includes(auth.role))
const selectedTotal = computed(() =>
  unsettled.value.filter((r) => selectedIds.value.includes(r.id))
    .reduce((s, r) => s + Number(r.nominal || 0), 0))
const allSelected = computed(() =>
  unsettled.value.length > 0 && selectedIds.value.length === unsettled.value.length)

function toggleAll(e) {
  selectedIds.value = e.target.checked ? unsettled.value.map((r) => r.id) : []
}
function toggle(id) {
  selectedIds.value = selectedIds.value.includes(id)
    ? selectedIds.value.filter((x) => x !== id)
    : [...selectedIds.value, id]
}

async function loadSummary() {
  summary.value = await api('/api/voucher/summary')
}
async function loadPending() {
  const r = await api('/api/voucher/pending')
  pending.value = r?.data || []
}
async function loadUnsettled() {
  const r = await api('/api/voucher/unsettled', { params: { start: start.value, end: end.value } })
  unsettled.value = r?.data || []
  selectedIds.value = selectedIds.value.filter((id) => unsettled.value.some((r) => r.id === id))
}
async function loadSettlements() {
  settlements.value = await api('/api/voucher/settlements')
}

async function reload() {
  loading.value = true
  err.value = ''
  try {
    await Promise.all([loadSummary(), loadPending(), loadUnsettled(), loadSettlements()])
  } catch (e) {
    err.value = e?.data?.error || e.message || 'Gagal memuat data voucher'
  } finally {
    loading.value = false
  }
}

async function verify(row) {
  if (row.ml_anomaly_flag) { await verifyFull(row); return }
  if (busy.value) return
  const ok = window.confirm(
    `Verifikasi voucher ${row.display_id}? Pastikan foto ODO, nota + ODO, dan struk sesuai.`)
  if (!ok) return
  busy.value = true
  msg.value = ''
  try {
    const r = await api(`/api/voucher/verify/${row.id}`, { method: 'POST' })
    msg.value = '✅ ' + (r?.msg || 'Voucher diverifikasi')
    await reload()
  } catch (e) {
    msg.value = ''
    err.value = e?.data?.msg || e.message
  } finally {
    busy.value = false
  }
}

/**
 * v2.108.0 (audit F1): voucher ber-flag anomali tidak boleh buntu.
 * GA memeriksa foto, lalu satu klik menjalankan dua langkah:
 *   1. POST /api/queue/anomaly-clear/<id> — wajib step-up PIN, mencatat
 *      siapa yang menyaksikan pemeriksaan (anomaly_cleared_by).
 *   2. POST /api/voucher/verify/<id> — baru boleh lanjut setelah bersih.
 * Bila user membatalkan PIN, tidak ada perubahan status.
 */
async function verifyFull(row) {
  if (busy.value) return
  const ok = window.confirm(
    `Verifikasi penuh voucher ${row.display_id}?\n\n` +
    'Voucher ini ditandai anomali. Periksa foto ODO, nota + ODO, dan struk. ' +
    'Setelah Anda konfirmasi dengan PIN, anomali dicatat sebagai diperiksa dan voucher diverifikasi.')
  if (!ok) return
  busy.value = true
  msg.value = ''
  err.value = ''
  try {
    const cleared = await stepup.require(
      () => api(`/api/queue/anomaly-clear/${row.id}`, { method: 'POST' }),
      'memeriksa anomali voucher')
    if (!cleared) return
    const r = await api(`/api/voucher/verify/${row.id}`, { method: 'POST' })
    msg.value = '✅ ' + (r?.msg || 'Voucher diverifikasi')
    await reload()
  } catch (e) {
    msg.value = ''
    err.value = e?.data?.msg || e.message
  } finally {
    busy.value = false
  }
}

async function createSettlement() {
  if (!selectedIds.value.length) {
    err.value = 'Pilih minimal satu voucher yang akan ditagihkan.'
    return
  }
  busy.value = true
  msg.value = ''
  err.value = ''
  try {
    const body = {
      period_start: start.value,
      period_end: end.value,
      invoice_no: form.value.invoice_no,
      notes: form.value.notes,
      partner: form.value.partner,
      tx_ids: selectedIds.value,
    }
    const r = await stepup.require(
      () => api('/api/voucher/settlements', { method: 'POST', body }),
      'membuat tagihan voucher')
    if (r) {
      msg.value = '✅ ' + (r.msg || 'Tagihan dibuat')
      form.value = { invoice_no: '', notes: '', partner: '' }
      await reload()
    }
  } catch (e) {
    err.value = e?.data?.msg || e.message
  } finally {
    busy.value = false
  }
}

async function pay(row) {
  if (!window.confirm(`Tandai tagihan ${row.display_id} sudah dibayar ke ${row.partner || 'SPBU mitra'}?`)) return
  busy.value = true
  msg.value = ''
  err.value = ''
  try {
    const r = await stepup.require(
      () => api(`/api/voucher/settlements/${row.id}/pay`, { method: 'POST' }),
      'menandai tagihan voucher dibayar')
    if (r) {
      msg.value = '✅ ' + (r.msg || 'Tagihan dibayar')
      await reload()
    }
  } catch (e) {
    err.value = e?.data?.msg || e.message
  } finally {
    busy.value = false
  }
}

async function cancelSettlement(row) {
  if (!window.confirm(`Batalkan tagihan ${row.display_id}? Voucher kembali ke daftar belum ditagih.`)) return
  busy.value = true
  msg.value = ''
  err.value = ''
  try {
    const r = await stepup.require(
      () => api(`/api/voucher/settlements/${row.id}/cancel`, { method: 'POST' }),
      'membatalkan tagihan voucher')
    if (r) {
      msg.value = '✅ ' + (r.msg || 'Tagihan dibatalkan')
      await reload()
    }
  } catch (e) {
    err.value = e?.data?.msg || e.message
  } finally {
    busy.value = false
  }
}

function openUsagePdf(row) {
  window.open(`/api/voucher/${row.id}/pdf`, '_blank', 'noopener')
}
function openSettlementPdf(row) {
  window.open(`/api/voucher/settlements/${row.id}/pdf`, '_blank', 'noopener')
}
function openPhoto(row, field) {
  if (row?.[field]) window.open('/uploads/' + encodeURIComponent(row[field]), '_blank', 'noopener')
}

async function openDetail(row) {
  detailLoading.value = true
  detail.value = { settlement: row, items: [] }
  try {
    detail.value = await api(`/api/voucher/settlements/${row.id}`)
  } catch (e) {
    err.value = e?.data?.error || e.message
    detail.value = null
  } finally {
    detailLoading.value = false
  }
}

onMounted(reload)
</script>

<template>
  <div class="voucher-panel" data-testid="voucher-panel">
    <div v-if="msg" class="alert alert-success" style="margin-bottom:10px;">{{ msg }}</div>
    <div v-if="err" class="alert alert-danger" style="margin-bottom:10px;">{{ err }}</div>

    <div class="card card-pad" style="margin-bottom:12px;">
      <div class="row" style="gap:10px;flex-wrap:wrap;align-items:center;">
        <b>🎟️ Voucher Rekanan</b>
        <span class="muted" style="font-size:12px;">
          SPBU mitra memberi voucher + blanko → driver memakai → finance menagih per periode.
        </span>
        <div class="spacer"></div>
        <span class="badge badge-gray">Nilai cabang: {{ fmtRp(summary?.config?.value) }}</span>
      </div>
      <div v-if="loading" class="muted" style="font-size:12px;margin-top:8px;">⏳ Memuat…</div>
      <div v-else class="row" style="gap:10px;flex-wrap:wrap;margin-top:10px;">
        <div class="card card-pad" style="flex:1 1 180px;">
          <div class="muted" style="font-size:12px;">⏳ Menunggu verifikasi GA</div>
          <b style="font-size:20px;">{{ summary?.pending?.count || 0 }}</b>
          <div class="muted" style="font-size:11px;">{{ fmtRp(summary?.pending?.amount) }}</div>
        </div>
        <div class="card card-pad" style="flex:1 1 180px;">
          <div class="muted" style="font-size:12px;">🧾 Belum ditagih</div>
          <b style="font-size:20px;">{{ summary?.open?.count || 0 }}</b>
          <div class="muted" style="font-size:11px;">{{ fmtRp(summary?.open?.amount) }}</div>
        </div>
        <div class="card card-pad" style="flex:1 1 180px;">
          <div class="muted" style="font-size:12px;">✅ Sudah masuk tagihan</div>
          <b style="font-size:20px;">{{ summary?.settled?.count || 0 }}</b>
          <div class="muted" style="font-size:11px;">{{ fmtRp(summary?.settled?.amount) }}</div>
        </div>
      </div>
    </div>

    <!-- 1. Verifikasi GA -->
    <div v-if="pending.length" class="card card-pad" style="margin-bottom:12px;">
      <b>⏳ Menunggu verifikasi GA ({{ pending.length }})</b>
      <p class="muted" style="font-size:11px;margin:4px 0;">
        Periksa foto ODO, nota + ODO, dan struk. Verifikasi membuat voucher masuk hitungan beban BBM.
        Voucher ber-flag <b>⚠ Anomali</b> wajib memakai <b>🛡 Verifikasi penuh</b> (PIN ulang).
      </p>
      <div class="table-wrap">
        <table class="tbl">
          <thead>
            <tr><th>No.</th><th>Tanggal</th><th>Driver</th><th>Nopol</th><th>SPBU / Nota</th>
              <th>Nilai</th><th>Liter</th><th>Foto</th><th></th></tr>
          </thead>
          <tbody>
            <tr v-for="row in pending" :key="row.id">
              <td>{{ row.display_id }}</td>
              <td>{{ formatDateTime(row.created_at) }}</td>
              <td>{{ row.driver_name }}
                <div v-if="row.ml_anomaly_flag" class="badge badge-amber" style="font-size:10px;"
                     title="Pola pemakaian tidak wajar — perlu pemeriksaan penuh">⚠ Anomali</div>
              </td>
              <td>{{ row.nopol }}</td>
              <td>{{ row.voucher_partner || '-' }}<div class="muted" style="font-size:11px;">{{ row.nota_no }}</div></td>
              <td>{{ fmtRp(row.nominal) }}<div class="muted" style="font-size:11px;">+ kode {{ row.daily_code }}</div></td>
              <td>{{ Number(row.liter || 0).toFixed(2) }} L</td>
              <td>
                <button v-if="row.foto_odo_sebelum" class="btn btn-sm" @click="openPhoto(row, 'foto_odo_sebelum')">📷 ODO</button>
                <button v-if="row.foto_nota_odo_sesudah" class="btn btn-sm" @click="openPhoto(row, 'foto_nota_odo_sesudah')">🧾 Nota</button>
                <button v-if="row.foto_struk" class="btn btn-sm" @click="openPhoto(row, 'foto_struk')">🎟️ Struk</button>
              </td>
              <td>
                <button v-if="isGa" class="btn btn-sm btn-success" :disabled="busy"
                        :data-testid="'voucher-verify-' + row.id" @click="verify(row)">
                  {{ row.ml_anomaly_flag ? '🛡 Verifikasi penuh' : '✅ Verifikasi' }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 2. Belum ditagih + buat tagihan -->
    <div class="card card-pad" style="margin-bottom:12px;">
      <b>🧾 Voucher terverifikasi belum ditagih ({{ unsettled.length }})</b>
      <div class="row" style="gap:8px;flex-wrap:wrap;margin:8px 0;">
        <label class="field" style="margin:0;">
          <span style="font-size:11px;">Dari</span>
          <input v-model="start" type="date" class="input" />
        </label>
        <label class="field" style="margin:0;">
          <span style="font-size:11px;">Sampai</span>
          <input v-model="end" type="date" class="input" />
        </label>
        <button class="btn btn-sm" :disabled="loading" @click="loadUnsettled">🔄 Muat ulang</button>
      </div>
      <div class="table-wrap">
        <table class="tbl">
          <thead>
            <tr>
              <th style="width:30px;">
                <input type="checkbox" :checked="allSelected" @change="toggleAll($event)" />
              </th>
              <th>Tanggal</th><th>Driver</th><th>Nopol</th><th>SPBU / Nota</th>
              <th>Nilai</th><th>Kode</th><th>Total</th><th>PDF</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in unsettled" :key="row.id">
              <td><input type="checkbox" :checked="selectedIds.includes(row.id)" @change="toggle(row.id)" /></td>
              <td>{{ fmtDate(row.created_at) }}</td>
              <td>{{ row.driver_name }}
                <div v-if="row.ml_anomaly_flag" class="badge badge-amber" style="font-size:10px;"
                     title="Pola pemakaian tidak wajar — perlu pemeriksaan penuh">⚠ Anomali</div>
              </td>
              <td>{{ row.nopol }}</td>
              <td>{{ row.voucher_partner || '-' }}<div class="muted" style="font-size:11px;">{{ row.nota_no }}</div></td>
              <td>{{ fmtRp(row.voucher_value) }}</td>
              <td>{{ row.daily_code }}</td>
              <td><b>{{ fmtRp(row.nominal) }}</b></td>
              <td><button class="btn btn-sm" @click="openUsagePdf(row)">📄</button></td>
            </tr>
            <tr v-if="!unsettled.length">
              <td colspan="9" class="muted">Tidak ada voucher terverifikasi pada periode ini.</td>
            </tr>
          </tbody>
          <tfoot v-if="unsettled.length">
            <tr>
              <th colspan="7" style="text-align:right;">Dipilih: {{ selectedIds.length }} voucher</th>
              <th colspan="2">{{ fmtRp(selectedTotal) }}</th>
            </tr>
          </tfoot>
        </table>
      </div>

      <div v-if="isFinance" class="form-grid" style="margin-top:10px;">
        <div class="field"><label>No. Invoice SPBU</label>
          <input class="input" v-model="form.invoice_no" placeholder="cth: INV/SPBU/XI/2026/001" />
        </div>
        <div class="field"><label>SPBU Mitra (opsional)</label>
          <input class="input" v-model="form.partner" placeholder="otomatis dari voucher bila kosong" />
        </div>
        <div class="field" style="grid-column:1/-1;"><label>Catatan</label>
          <input class="input" v-model="form.notes" placeholder="catatan rekonsiliasi (opsional)" />
        </div>
      </div>
      <div v-if="isFinance" style="margin-top:8px;">
        <button class="btn btn-primary" :disabled="busy || !selectedIds.length" @click="createSettlement">
          🧾 Buat tagihan {{ selectedIds.length ? '(' + selectedIds.length + ' voucher)' : '' }}
        </button>
        <span class="muted" style="font-size:11px;margin-left:8px;">
          Voucher yang masuk tagihan terkunci dan tidak muncul lagi di periode berikutnya.
        </span>
      </div>
    </div>

    <!-- 3. Riwayat tagihan -->
    <div class="card card-pad">
      <b>📚 Riwayat tagihan SPBU mitra ({{ settlements.length }})</b>
      <div class="table-wrap" style="margin-top:8px;">
        <table class="tbl">
          <thead>
            <tr><th>No.</th><th>Periode</th><th>SPBU Mitra</th><th>Invoice</th>
              <th>Voucher</th><th>Total</th><th>Status</th><th>Aksi</th></tr>
          </thead>
          <tbody>
            <tr v-for="row in settlements" :key="row.id">
              <td>{{ row.display_id }}</td>
              <td>{{ fmtDate(row.period_start) }} — {{ fmtDate(row.period_end) }}</td>
              <td>{{ row.partner || '-' }}</td>
              <td>{{ row.invoice_no || '-' }}</td>
              <td>{{ row.voucher_count }}</td>
              <td><b>{{ fmtRp(row.total_amount) }}</b></td>
              <td>
                <span class="badge" :class="row.status === 'paid' ? 'badge-green' : row.status === 'cancelled' ? 'badge-red' : 'badge-amber'">
                  {{ row.status === 'paid' ? 'Dibayar' : row.status === 'cancelled' ? 'Dibatalkan' : 'Menunggu bayar' }}
                </span>
                <div v-if="row.paid_at" class="muted" style="font-size:11px;">
                  {{ row.paid_by }} · {{ formatDateTime(row.paid_at) }}
                </div>
              </td>
              <td style="white-space:nowrap;">
                <button class="btn btn-sm" @click="openDetail(row)">👁</button>
                <button class="btn btn-sm" @click="openSettlementPdf(row)">📄 BA</button>
                <button v-if="isFinance && row.status === 'draft'" class="btn btn-sm btn-primary"
                        :disabled="busy" @click="pay(row)">💵 Bayar</button>
                <button v-if="isFinance && row.status === 'draft'" class="btn btn-sm btn-danger"
                        :disabled="busy" @click="cancelSettlement(row)">✕</button>
              </td>
            </tr>
            <tr v-if="!settlements.length">
              <td colspan="8" class="muted">Belum ada tagihan voucher.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <Modal v-if="detail" :title="'🧾 ' + (detail.settlement?.display_id || 'Tagihan')" @close="detail = null">
      <div v-if="detailLoading" class="muted">⏳ Memuat rincian…</div>
      <div v-else>
        <div class="form-grid">
          <div class="field"><label>SPBU Mitra</label><input class="input" :value="detail.settlement?.partner || '-'" disabled /></div>
          <div class="field"><label>Periode</label>
            <input class="input" :value="fmtDate(detail.settlement?.period_start) + ' — ' + fmtDate(detail.settlement?.period_end)" disabled />
          </div>
          <div class="field"><label>Invoice</label><input class="input" :value="detail.settlement?.invoice_no || '-'" disabled /></div>
          <div class="field"><label>Total</label><input class="input" :value="fmtRp(detail.settlement?.total_amount)" disabled /></div>
        </div>
        <div class="table-wrap" style="margin-top:10px;">
          <table class="tbl">
            <thead><tr><th>No.</th><th>Tanggal</th><th>Driver</th><th>Nopol</th><th>Nota</th><th>Total</th></tr></thead>
            <tbody>
              <tr v-for="it in detail.items" :key="it.id">
                <td>{{ it.display_id }}</td>
                <td>{{ fmtDate(it.created_at) }}</td>
                <td>{{ it.driver_name }}</td>
                <td>{{ it.nopol }}</td>
                <td>{{ it.nota_no }}</td>
                <td>{{ fmtRp(it.nominal) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div style="margin-top:12px;text-align:right;">
          <button class="btn" @click="openSettlementPdf(detail.settlement)">📄 Unduh Berita Acara</button>
        </div>
      </div>
    </Modal>
  </div>
</template>
