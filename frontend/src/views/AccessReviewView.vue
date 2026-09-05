<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import Modal from '../components/Modal.vue'
import StatCard from '../components/StatCard.vue'

const loading = ref(true)
const err = ref('')
const msg = ref('')
const busy = ref(false)

const data = ref(null)      // { users, summary, review, stale_days }
const search = ref('')
const filterStatus = ref('')
const filterRole = ref('')
const filterBranch = ref('')

const showDeactivate = ref(null)   // user yang akan dinonaktifkan
const branches = ref([])

const ACCOUNT_BADGE = {
  ok: 'badge-green', stale: 'badge-amber', never_login: 'badge-red', inactive: 'badge-gray',
}
const ACCOUNT_ICON = {
  ok: '🟢', stale: '🟡', never_login: '🔴', inactive: '⚪',
}
const ACCOUNT_LABEL = {
  ok: 'OK', stale: 'Basi', never_login: 'Belum Login', inactive: 'Nonaktif',
}

const ROLES = [
  ['admin', '🛡️ Admin'], ['ga', '🧾 GA'], ['finance', '💰 Finance'],
  ['marketing', '📣 Marketing'], ['chief_driver', '🚛 Chief Driver'], ['ob', '🚰 OB'],
  ['receptionist', '🪪 Receptionist'], ['traineer', '🎯 Traineer'], ['ga_hr', '⏰ GA HR'],
  ['driver', '🚗 Driver'],
]
const roleLabel = (r) => (ROLES.find((x) => x[0] === r) || [r, r])[1]

const branchName = (code) => {
  if (!code) return '—'
  const b = branches.value.find((x) => x.code === code)
  return b ? b.name : code
}

const summary = computed(() => data.value?.summary || { total: 0, active: 0, inactive: 0, ok: 0, stale: 0, never_login: 0 })
const review = computed(() => data.value?.review || { last_at: '', last_by: '' })
const staleDays = computed(() => data.value?.stale_days ?? 90)
const reviewDue = computed(() => {
  // Review triwulanan (90 hari) — belum pernah / lewat → due
  if (!review.value.last_at) return true
  const t = new Date(review.value.last_at.replace(' ', 'T'))
  return (Date.now() - t.getTime()) > 90 * 86400000
})

const filteredUsers = computed(() => {
  const q = search.value.toLowerCase()
  return (data.value?.users || []).filter((u) => {
    if (q && !u.username.toLowerCase().includes(q) && !(u.full_name || '').toLowerCase().includes(q)) return false
    if (filterStatus.value && u.account_status !== filterStatus.value) return false
    if (filterRole.value && u.role !== filterRole.value) return false
    if (filterBranch.value && (u.branch_code || '') !== filterBranch.value) return false
    return true
  })
})

async function load() {
  loading.value = true; err.value = ''
  try {
    const [d, b] = await Promise.all([
      api('/api/admin/access-review'),
      api('/api/branches').catch(() => ({ branches: [] })),
    ])
    data.value = d
    branches.value = (b && b.branches) ? b.branches : []
  } catch (e) { err.value = e.message }
  finally { loading.value = false }
}

async function completeReview() {
  busy.value = true; msg.value = ''
  try {
    const d = await api('/api/admin/access-review/complete', { method: 'POST' })
    msg.value = '✅ ' + (d.msg || 'Review ditandai selesai')
    await load()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { busy.value = false }
}

function exportCsv() {
  window.location.href = '/api/admin/access-review/export'
}

function fmtLast(u) {
  if (!u.last_login) return '—'
  return new Date(u.last_login).toLocaleString('id-ID')
}

function openDeactivate(u) { showDeactivate.value = u }

async function doDeactivate() {
  const u = showDeactivate.value
  if (!u) return
  busy.value = true; msg.value = ''
  try {
    await api('/api/users/sync', {
      method: 'POST',
      body: { username: u.username, full_name: u.full_name, role: u.role, is_active: false, team_name: u.team_name || '' },
    })
    msg.value = `✅ Akun ${u.username} dinonaktifkan (A.8.3)`
    showDeactivate.value = null
    await load()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { busy.value = false }
}

onMounted(load)
</script>

<template>
  <div>
    <div class="card card-pad" style="margin-bottom:16px;display:flex;align-items:center;flex-wrap:wrap;gap:8px;">
      <div class="grow">
        <h3 style="margin:0;">🛂 Access Review <span v-if="reviewDue" class="badge badge-red" style="margin-left:6px;">REVIEW TERLAMBAT</span></h3>
        <p class="muted" style="font-size:11px;margin-top:4px;">
          Review hak akses triwulanan (ISO/IEC 27001 A.5.15 · A.8.2 · A.8.3) — akun <b>Basi</b> =
          tidak login &gt; {{ staleDays }} hari · <b>Belum Login</b> = aktif tapi belum pernah masuk.
        </p>
        <p v-if="review.last_at" class="muted" style="font-size:11px;">
          📌 Review terakhir: <b>{{ review.last_by || '—' }}</b> · {{ review.last_at }}
        </p>
        <p v-else class="muted" style="font-size:11px;">📌 Belum pernah ada review tercatat.</p>
      </div>
      <button class="btn" :disabled="busy" @click="exportCsv" title="Unduh CSV untuk arsip triwulanan">📥 Export CSV</button>
      <button class="btn btn-primary" :disabled="busy" @click="completeReview">✔️ Tandai Review Selesai</button>
    </div>

    <div v-if="msg" class="alert" :class="msg.startsWith('✅') ? 'alert-success' : 'alert-error'" style="margin-bottom:16px;">{{ msg }}</div>

    <div class="stat-grid" style="margin-bottom:16px;">
      <StatCard icon="👥" label="Total User" :value="summary.total" color="#2563eb" />
      <StatCard icon="🟢" label="Aktif" :value="summary.active" color="#059669" />
      <StatCard icon="⚪" label="Nonaktif" :value="summary.inactive" color="#64748b" />
      <StatCard icon="🟢" label="OK" :value="summary.ok" color="#16a34a" />
      <StatCard icon="🟡" label="Basi (>{{ staleDays }} hr)" :value="summary.stale" color="#d97706" />
      <StatCard icon="🔴" label="Belum Login" :value="summary.never_login" color="#dc2626" />
    </div>

    <div class="card card-pad" style="margin-bottom:16px;">
      <div class="row" style="gap:8px;flex-wrap:wrap;align-items:center;">
        <input class="input" v-model="search" placeholder="🔍 Cari username / nama..." style="min-width:200px;flex:1;" />
        <select class="select" v-model="filterStatus" style="min-width:150px;">
          <option value="">Semua Status</option>
          <option value="ok">🟢 OK</option>
          <option value="stale">🟡 Basi</option>
          <option value="never_login">🔴 Belum Login</option>
          <option value="inactive">⚪ Nonaktif</option>
        </select>
        <select class="select" v-model="filterRole" style="min-width:140px;">
          <option value="">Semua Role</option>
          <option v-for="r in ROLES" :key="r[0]" :value="r[0]">{{ r[1] }}</option>
        </select>
        <select class="select" v-model="filterBranch" style="min-width:150px;" v-if="branches.length">
          <option value="">Semua Cabang</option>
          <option v-for="b in branches" :key="b.code" :value="b.code">{{ b.name }}</option>
        </select>
        <span class="muted" style="font-size:12px;">{{ filteredUsers.length }} akun</span>
      </div>
    </div>

    <div v-if="loading" class="empty skeleton">⏳ Memuat…</div>
    <div v-else-if="err" class="alert alert-error">{{ err }}</div>
    <div v-else class="card">
      <div class="table-wrap">
        <table class="tbl">
          <thead>
            <tr>
              <th>User</th><th>Role</th><th>Cabang</th>
              <th>Status Akun</th><th>Terakhir Login</th><th style="min-width:120px;">Aksi</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="u in filteredUsers" :key="u.id" :class="{ 'row-inactive': !u.is_active }">
              <td><b>{{ u.full_name }}</b><div class="muted" style="font-size:11px;">{{ u.username }}</div></td>
              <td>{{ u.role_label }}</td>
              <td><span class="badge badge-blue" v-if="u.branch_code">{{ branchName(u.branch_code) }}</span><span v-else class="muted">—</span></td>
              <td>
                <span class="badge" :class="ACCOUNT_BADGE[u.account_status]">
                  {{ ACCOUNT_ICON[u.account_status] }} {{ ACCOUNT_LABEL[u.account_status] }}
                </span>
              </td>
              <td class="muted" style="font-size:12px;">{{ fmtLast(u) }}</td>
              <td style="white-space:nowrap;">
                <button v-if="u.is_active && u.account_status !== 'ok'"
                        class="btn btn-sm btn-danger" :disabled="busy"
                        @click="openDeactivate(u)" title="Nonaktifkan akun (A.8.3)">🚫 Nonaktifkan</button>
                <span v-else class="muted" style="font-size:11px;">—</span>
              </td>
            </tr>
            <tr v-if="!filteredUsers.length"><td colspan="6" class="empty">Tidak ada akun ditemukan.</td></tr>
          </tbody>
        </table>
      </div>
      <div class="muted" style="font-size:11px;padding:10px 14px;">
        💡 Akun <b>Basi</b> &amp; <b>Belum Login</b> adalah kandidat pencabutan akses (A.8.3) —
        verifikasi ke pemilik divisi sebelum menonaktifkan.
      </div>
    </div>

    <Modal v-if="showDeactivate" :title="'🚫 Nonaktifkan ' + (showDeactivate?.username || '')" @close="showDeactivate = null">
      <p style="margin:0 0 12px;">
        Yakin menonaktifkan akun <b>{{ showDeactivate?.username }}</b> ({{ showDeactivate?.full_name }})?<br />
        <span class="muted" style="font-size:12px;">User tidak bisa login lagi sampai diaktifkan Admin.</span>
      </p>
      <div class="row" style="justify-content:flex-end;gap:8px;margin-top:12px;">
        <button class="btn" @click="showDeactivate = null">Batal</button>
        <button class="btn btn-danger" :disabled="busy" @click="doDeactivate">🚫 Nonaktifkan</button>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
.row-inactive { opacity: 0.55; }
.row { display: flex; flex-wrap: wrap; }
.grow { flex: 1; min-width: 200px; }
.select { padding: 6px 10px; border: 1px solid var(--border, #e2e8f0); border-radius: 8px; background: var(--card, #fff); color: var(--text, #0f172a); font-size: 13px; }
.input { padding: 6px 10px; border: 1px solid var(--border, #e2e8f0); border-radius: 8px; background: var(--card, #fff); color: var(--text, #0f172a); font-size: 13px; }
</style>
