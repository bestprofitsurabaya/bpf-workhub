<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { useAuthStore } from '../stores/auth'
import { useStepupStore } from '../stores/stepup'
import Modal from '../components/Modal.vue'

const stepup = useStepupStore()

const auth = useAuthStore()
const cash = ref([])
const loading = ref(true)
const err = ref('')
const daily = ref({ code: '', manual_mode: false })
const dailyMsg = ref('')
const pendingLpj = ref([])
const busy = ref(false)

const action = ref(null) // { kind, id }
const form = ref({ amount: '', reason: '', notes: '' })
const detailItem = ref(null) // cash detail modal
const detailData = ref(null)
const detailLoading = ref(false)

const isGa = ['ga', 'admin'].includes(auth.role)
const isFinance = ['finance', 'admin'].includes(auth.role)
const canEditDaily = isFinance

const STEPS = ['DRAFT', 'GA_APPROVED', 'FINANCE_APPROVED', 'FUNDS_WITH_DRIVER', 'LPJ_SUBMITTED', 'COMPLETED']
const STEP_ICONS = ['📝', '✅', '💰', '🤝', '📋', '🎉']
const STATUS_COLOR = {
  DRAFT: '#94a3b8', GA_APPROVED: '#0891b2', FINANCE_APPROVED: '#d97706',
  FUNDS_WITH_DRIVER: '#059669', LPJ_SUBMITTED: '#2563eb', COMPLETED: '#059669', REJECTED: '#dc2626',
}
const STATUS_BADGE = {
  DRAFT: 'badge-gray', GA_APPROVED: 'badge-blue', FINANCE_APPROVED: 'badge-amber',
  FUNDS_WITH_DRIVER: 'badge-green', LPJ_SUBMITTED: 'badge-blue', COMPLETED: 'badge-green', REJECTED: 'badge-red',
}
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
    case 'approve_finance': return isFinance
    case 'reset_lpj': return isFinance
    case 'reject': case 'delete': case 'edit': case 'cancel': return true
    default: return false
  }
})

async function load() {
  loading.value = true; err.value = ''
  try {
    const d = await api('/api/cash/history')
    cash.value = Array.isArray(d) ? d : []
    const dc = await api('/api/cash/daily-code')
    daily.value = { code: dc.code, manual_mode: !!dc.manual_mode }
    dailyMsg.value = ''
    try {
      const pl = await api('/api/cash/pending-lpj')
      pendingLpj.value = Array.isArray(pl) ? pl : []
    } catch { pendingLpj.value = [] }
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

async function openDetail(item) {
  detailItem.value = item
  detailLoading.value = true
  detailData.value = null
  try {
    detailData.value = await api(`/api/cash/detail/${item.id}`)
  } catch (e) { alert('❌ Gagal memuat detail: ' + e.message) }
  finally { detailLoading.value = false }
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
  }[a.kind]
  // Step-up (ISO/IEC 27001 A.8.5): aksi yang menggerakkan uang kasbon
  // (approve GA, pencairan Finance, serah terima dana ke driver, approve LPJ)
  // wajib konfirmasi PIN ulang bila grant belum ada.
  const STEPUP_KINDS = ['approve_ga', 'approve_finance', 'handover', 'approve_lpj']
  try {
    const run = () => api(EP, { method: 'POST', body })
    const d = STEPUP_KINDS.includes(a.kind)
      ? await stepup.require(run, `konfirmasi ${a.kind.replace(/_/g, ' ')} kasbon`)
      : await run()
    alert(d.msg || 'Berhasil')
    action.value = null
    load()
  } catch (e) { alert('❌ ' + e.message) }
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
    <div class="card card-pad" style="margin-bottom:16px;">
      <div class="row">
        <div class="grow">
          <b>🔢 Kode Harian</b>
          <div class="muted" style="font-size:12px;">Kode unik pengajuan kasbon hari ini</div>
        </div>
        <input class="input" style="width:130px;text-align:center;font-weight:700;" v-model="daily.code"
               :readonly="!canEditDaily || !daily.manual_mode" :maxlength="4" />
        <button class="btn btn-primary" v-if="canEditDaily && daily.manual_mode" :disabled="busy" @click="setDailyCode">Simpan</button>
        <span class="muted" style="font-size:12px;">{{ dailyMsg }}</span>
      </div>
    </div>

    <div v-if="loading" class="empty skeleton">⏳ Memuat…</div>
    <div v-else-if="err" class="alert alert-error">{{ err }}</div>
    <template v-else>
      <div class="card" style="margin-bottom:16px;">
        <div class="card-pad row" style="border-bottom:1px solid var(--border);">
          <b>💰 Pengajuan Kasbon</b>
          <span class="badge badge-blue">{{ cash.length }} pengajuan</span>
        </div>
        <div v-if="!cash.length" class="empty">Tidak ada pengajuan kasbon.</div>
        <div v-for="c in cash" :key="c.id" class="cash-item">
          <div class="row" style="align-items:center;">
            <div class="grow">
              <div class="row" style="gap:8px;align-items:center;">
                <b>{{ c.display_id }}</b>
                <span class="badge" :class="STATUS_BADGE[c.status] || 'badge-gray'">{{ (c.status || '').replace(/_/g, ' ') }}</span>
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
            <template v-if="ACTIONS[c.status]">
              <button v-for="a in ACTIONS[c.status].filter(x => x.show())" :key="a.kind"
                      class="btn btn-sm" :class="a.cls" @click="openAction(a.kind, c)">{{ a.label }}</button>
            </template>
            <span v-if="c.status === 'FUNDS_WITH_DRIVER'" class="muted" style="font-size:12px;">✅ Dana di Driver — menunggu LPJ</span>
            <span v-if="c.status === 'COMPLETED' && !isFinance" class="muted" style="font-size:12px;">🎉 Selesai</span>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-pad row" style="border-bottom:1px solid var(--border);">
          <b>📋 Menunggu LPJ</b>
          <span class="badge badge-amber">{{ pendingLpj.length }}</span>
        </div>
        <div v-if="!pendingLpj.length" class="empty">Tidak ada kasbon menunggu LPJ.</div>
        <div v-for="c in pendingLpj" :key="c.id" class="cash-item">
          <div class="row">
            <div class="grow">
              <b>{{ c.display_id }}</b> <span class="badge badge-amber">FUNDS WITH DRIVER</span>
              <div class="muted" style="font-size:12px;">👤 {{ c.driver_name }} · 🚗 {{ c.nopol || '—' }} · {{ fmtRp(c.total_amount) }}</div>
            </div>
            <span class="muted" style="font-size:11px;">{{ c.created_at }}</span>
          </div>
        </div>
      </div>
    </template>

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
          <div class="field"><label>Dibuat</label><input class="input" :value="detailData.created_at" disabled /></div>
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
.cash-item { padding: 14px; border-bottom: 1px solid var(--border); }
.cash-item:last-child { border-bottom: none; }
.step-track { display: flex; gap: 6px; font-size: 11px; justify-content: flex-end; }
.step-ic { filter: grayscale(0); }
.progress { background: var(--border); border-radius: 4px; height: 5px; width: 160px; margin-top: 5px; }
.progress-bar { height: 100%; border-radius: 4px; transition: width .4s ease; }
</style>
