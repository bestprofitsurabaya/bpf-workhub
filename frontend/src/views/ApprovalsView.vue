<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import Modal from '../components/Modal.vue'
import StatCard from '../components/StatCard.vue'

// v2.36.0 — Approval Berjenjang: antrean ACC atasan (Chief Driver → GA,
// GA HR → Admin). Daftar hanya pengajuan yang langkah aktifnya milik sesi
// (atau semua utk Admin) — sudah difilter backend.

const loading = ref(true)
const err = ref('')
const msg = ref('')
const busy = ref(false)

const items = ref([])          // baris approval_requests dari /api/approvals
const decideFor = ref(null)    // item yang sedang diputus
const note = ref('')

const DOC_LABEL = {
  cash: '💵 Kasbon', bbm: '⛽ Klaim BBM',
  overtime_driver: '⏰ Overtime Driver', overtime_ob: '⏰ Overtime OB/Security',
}
const DOC_ICON = { cash: '💵', bbm: '⛽', overtime_driver: '🚗', overtime_ob: '🧹' }

const summary = computed(() => ({
  menunggu: items.value.length,
  kasbonBbm: items.value.filter((r) => r.doc_type === 'cash' || r.doc_type === 'bbm').length,
  overtime: items.value.filter((r) => String(r.doc_type).startsWith('overtime')).length,
}))

async function load() {
  loading.value = true
  err.value = ''
  try {
    const d = await api('/api/approvals')
    items.value = (d && d.data) || []
  } catch (e) {
    err.value = e.message || 'Gagal memuat antrean ACC'
  } finally {
    loading.value = false
  }
}

function openDecide(r) {
  decideFor.value = r
  note.value = ''
}

function stepIndex(r) {
  return (r.step || 1)
}

function chainLabel(r) {
  const steps = Array.isArray(r.chain) ? r.chain : []
  return steps.map((s, i) => `${i + 1}. ${s.approver || s.role || '?'}`).join(' → ')
}

async function decide(decision) {
  const r = decideFor.value
  if (!r) return
  if (decision === 'rejected' && !note.value.trim()) {
    alert('Alasan penolakan wajib diisi')
    return
  }
  const label = decision === 'approved' ? 'menyetujui (ACC)' : 'menolak'
  if (!window.confirm(`${label.charAt(0).toUpperCase() + label.slice(1)} pengajuan ${r.display_id || r.doc_type + ' #' + r.doc_ref}?`)) return
  busy.value = true
  try {
    const d = await api(`/api/approvals/${r.doc_type}/${r.doc_ref}/decision`, {
      method: 'POST',
      body: { decision, note: note.value },
    })
    msg.value = d.msg || 'Keputusan tercatat'
    decideFor.value = null
    await load()
  } catch (e) {
    alert('❌ ' + (e.message || 'Gagal mencatat keputusan'))
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <div class="card card-pad" style="margin-bottom:16px;display:flex;align-items:center;flex-wrap:wrap;gap:8px;">
      <div style="flex:1;min-width:220px;">
        <h3 style="margin:0;">✅ Approval Berjenjang</h3>
        <p class="muted" style="margin:4px 0 0;font-size:13px;">
          Pengajuan menunggu ACC atasan sebelum diproses back-office.
          Kasbon &amp; Klaim BBM: Chief Driver → GA. Overtime: GA HR → Admin.
        </p>
      </div>
      <button class="btn" :disabled="loading" @click="load">⟳ Muat ulang</button>
    </div>

    <div v-if="err" class="card card-pad" style="margin-bottom:16px;border-left:4px solid #d33;">
      ⚠️ {{ err }}
    </div>
    <div v-if="msg" class="card card-pad" style="margin-bottom:16px;border-left:4px solid #3a3;">
      {{ msg }}
    </div>

    <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px;">
      <StatCard label="Menunggu Saya" :value="summary.menunggu" icon="⏳" />
      <StatCard label="Kasbon / BBM" :value="summary.kasbonBbm" icon="⛽" color="#d97706" />
      <StatCard label="Overtime" :value="summary.overtime" icon="⏰" color="#7c3aed" />
    </div>

    <div v-if="loading" class="card card-pad">Memuat…</div>

    <div v-else-if="!items.length" class="card card-pad" style="text-align:center;color:var(--muted,#777);">
      🎉 Tidak ada pengajuan yang menunggu ACC Anda.
    </div>

    <div v-else class="card">
      <div class="table-wrap">
        <table class="tbl">
          <thead>
            <tr>
              <th>Pengajuan</th>
              <th>Pengaju</th>
              <th>Cabang</th>
              <th>Rantai ACC</th>
              <th>Diajukan</th>
              <th style="width:170px;">Aksi</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in items" :key="r.doc_type + '-' + r.doc_ref">
              <td>
                <strong>{{ DOC_ICON[r.doc_type] || '📄' }} {{ r.display_id || (r.doc_type + ' #' + r.doc_ref) }}</strong>
                <div class="muted" style="font-size:12px;">{{ DOC_LABEL[r.doc_type] || r.doc_type }} · langkah {{ stepIndex(r) }}</div>
              </td>
              <td>
                {{ r.requested_by || '—' }}
                <div class="muted" style="font-size:12px;">{{ r.requester_role }}</div>
              </td>
              <td><span v-if="r.branch_code" class="badge badge-blue">{{ r.branch_code }}</span><span v-else class="muted">—</span></td>
              <td style="font-size:12px;">{{ chainLabel(r) }}</td>
              <td style="font-size:12px;">{{ (r.created_at || '').replace('T', ' ').slice(0, 16) }}</td>
              <td><button class="btn btn-primary" style="width:100%;" @click="openDecide(r)">Keputusan</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <Modal v-if="decideFor" :title="`Keputusan ACC — ${decideFor?.display_id || ''}`" @close="decideFor = null">
      <div v-if="decideFor">
        <p style="margin-top:0;">
          {{ DOC_ICON[decideFor.doc_type] || '📄' }}
          <strong>{{ DOC_LABEL[decideFor.doc_type] || decideFor.doc_type }}</strong>
          oleh <strong>{{ decideFor.requested_by }}</strong>
          <span v-if="decideFor.branch_code" class="badge badge-blue" style="margin-left:6px;">{{ decideFor.branch_code }}</span>
        </p>
        <p class="muted" style="font-size:13px;">Rantai ACC: {{ chainLabel(decideFor) }}</p>
        <div class="field">
          <label>Catatan <span class="muted">(wajib bila menolak)</span></label>
          <textarea v-model="note" class="input" rows="3" placeholder="mis. Nominal tidak sesuai kebutuhan perjalanan"></textarea>
        </div>
        <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:12px;">
          <button class="btn" :disabled="busy" @click="decideFor = null">Batal</button>
          <button class="btn btn-danger" :disabled="busy" @click="decide('rejected')">❌ Tolak</button>
          <button class="btn btn-primary" :disabled="busy" @click="decide('approved')">✅ ACC</button>
        </div>
      </div>
    </Modal>
  </div>
</template>
