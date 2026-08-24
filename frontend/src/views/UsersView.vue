<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { useAuthStore } from '../stores/auth'
import Modal from '../components/Modal.vue'
import StatCard from '../components/StatCard.vue'

const auth = useAuthStore()
const users = ref([])
const loading = ref(true)
const err = ref('')

// Search & Filter
const search = ref('')
const filterRole = ref('')
const filterStatus = ref('')
const filterBranch = ref('')

// Bulk Actions
const selected = ref([])
const selectAll = ref(false)
const bulkBusy = ref(false)

// Modals
const showForm = ref(false)
const showResetPin = ref(false)
const showAuditLog = ref(false)
const showDeleteConfirm = ref(false)
const showBulkConfirm = ref(false)
const showBulkResetPin = ref(false)

const form = ref({ username: '', full_name: '', role: 'ga', pin: '123456', team_name: '', branch_code: '', is_active: true })
const resetPinData = ref({ username: '', pin: '' })
const auditLogUser = ref(null)
const auditLogs = ref([])
const auditLoading = ref(false)
const deleteTarget = ref(null)
const bulkAction = ref('')
const bulkResetPinValue = ref('123456')

const busy = ref(false)
const msg = ref('')

const ROLES = [
  ['admin', '🛡️ Admin'], ['ga', '🧾 GA Officer'], ['finance', '💰 Finance'],
  ['marketing', '📣 Marketing'], ['chief_driver', '🚛 Chief Driver'], ['ob', '🚰 OB'],
  ['receptionist', '🪪 Receptionist'], ['traineer', '🎯 Traineer'], ['ga_hr', '⏰ GA HR'],
  ['driver', '🚗 Driver'],
  ['it_sby', '📰 IT Surabaya'],
  ['it_hu', '📰 IT Jakarta HO'],
  ['it_jkt2', '📰 IT Jakarta 2'],
  ['it_bdg', '📰 IT Bandung'],
  ['it_smg', '📰 IT Semarang'],
  ['it_mlg', '📰 IT Malang'],
  ['it_mdn', '📰 IT Medan'],
  ['it_bjm', '📰 IT Banjarmasin'],
  ['it_plm', '📰 IT Palembang'],
  ['it_lpg', '📰 IT Lampung'],
]
const roleLabel = (r) => (ROLES.find((x) => x[0] === r) || [r, r])[1]
const roleIcon = (r) => (ROLES.find((x) => x[0] === r) || ['', ''])[1].split(' ')[0]

const branches = ref([])

// Computed
const filteredUsers = computed(() => {
  return users.value.filter(u => {
    const matchSearch = !search.value || 
      u.username.toLowerCase().includes(search.value.toLowerCase()) ||
      u.full_name.toLowerCase().includes(search.value.toLowerCase())
    const matchRole = !filterRole.value || u.role === filterRole.value
    const matchStatus = filterStatus.value === '' || 
      (filterStatus.value === 'active' && u.is_active) ||
      (filterStatus.value === 'inactive' && !u.is_active)
    const matchBranch = !filterBranch.value || (u.branch_code || '') === filterBranch.value
    return matchSearch && matchRole && matchStatus && matchBranch
  })
})

const stats = computed(() => {
  const total = users.value.length
  const active = users.value.filter(u => u.is_active).length
  const inactive = total - active
  const byRole = {}
  ROLES.forEach(r => { byRole[r[0]] = users.value.filter(u => u.role === r[0]).length })
  return { total, active, inactive, byRole }
})

const selectedUsers = computed(() => users.value.filter(u => selected.value.includes(u.id)))
const selectedCount = computed(() => selected.value.length)

// Methods
async function load() {
  loading.value = true; err.value = ''
  try {
    const [u, b] = await Promise.all([
      api('/api/users'),
      api('/api/branches').catch(() => [])
    ])
    users.value = u || []
    branches.value = b || []
  } catch (e) { err.value = e.message }
  finally { loading.value = false }
}

function toggleSelectAll() {
  if (selectAll.value) {
    selected.value = filteredUsers.value.map(u => u.id)
  } else {
    selected.value = []
  }
}

function toggleSelect(id) {
  const idx = selected.value.indexOf(id)
  if (idx >= 0) selected.value.splice(idx, 1)
  else selected.value.push(id)
  selectAll.value = selected.value.length === filteredUsers.value.length
}

function openForm(u) {
  form.value = u ? { 
    username: u.username, full_name: u.full_name, role: u.role, 
    pin: '', team_name: u.team_name || '', branch_code: u.branch_code || '', 
    is_active: !!u.is_active 
  } : { username: '', full_name: '', role: 'ga', pin: '123456', team_name: '', branch_code: auth.user?.branch_code || '', is_active: true }
  showForm.value = true
}

async function save() {
  busy.value = true; msg.value = ''
  try {
    const body = { ...form.value }
    if (!body.pin) delete body.pin
    await api('/api/users/sync', { method: 'POST', body })
    msg.value = '✅ User berhasil disimpan'
    showForm.value = false; load()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { busy.value = false }
}

function openResetPin(u) {
  resetPinData.value = { username: u.username, pin: '' }
  showResetPin.value = true
}

async function doResetPin() {
  busy.value = true; msg.value = ''
  try {
    await api('/api/users/reset-pin', { method: 'POST', body: resetPinData.value })
    msg.value = '✅ PIN berhasil direset'
    showResetPin.value = false; load()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { busy.value = false }
}

function openDeleteConfirm(u) {
  deleteTarget.value = u
  showDeleteConfirm.value = true
}

async function doDelete() {
  if (!deleteTarget.value) return
  busy.value = true; msg.value = ''
  try {
    await api('/api/users/sync', { method: 'POST', body: { 
      username: deleteTarget.value.username, full_name: deleteTarget.value.full_name, 
      role: deleteTarget.value.role, is_active: false, team_name: deleteTarget.value.team_name || '' 
    }})
    msg.value = '✅ User dinonaktifkan'
    showDeleteConfirm.value = false; deleteTarget.value = null; load()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { busy.value = false }
}

async function toggleUser(u) {
  busy.value = true; msg.value = ''
  try {
    await api('/api/users/sync', { method: 'POST', body: { 
      username: u.username, full_name: u.full_name, role: u.role, 
      is_active: !u.is_active, team_name: u.team_name || '' 
    }})
    msg.value = `✅ User ${u.username} ${u.is_active ? 'dinonaktifkan' : 'diaktifkan'}`
    load()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { busy.value = false }
}

async function openAuditLog(u) {
  auditLogUser.value = u
  auditLoading.value = true
  showAuditLog.value = true
  try {
    const logs = await api('/api/audit-logs', { params: { user_name: u.username, limit: 50 } })
    auditLogs.value = logs || []
  } catch { auditLogs.value = [] }
  finally { auditLoading.value = false }
}

// Bulk Actions
function openBulkAction(action) {
  if (!selectedCount.value) { msg.value = '⚠️ Pilih user terlebih dahulu'; return }
  bulkAction.value = action
  showBulkConfirm.value = true
}

async function doBulkAction() {
  bulkBusy.value = true; msg.value = ''
  try {
    const promises = selectedUsers.value.map(u => {
      if (bulkAction.value === 'activate') {
        return api('/api/users/sync', { method: 'POST', body: { 
          username: u.username, full_name: u.full_name, role: u.role, is_active: true, team_name: u.team_name || '' 
        }})
      } else if (bulkAction.value === 'deactivate') {
        return api('/api/users/sync', { method: 'POST', body: { 
          username: u.username, full_name: u.full_name, role: u.role, is_active: false, team_name: u.team_name || '' 
        }})
      }
    })
    await Promise.all(promises)
    msg.value = `✅ ${selectedCount.value} user berhasil diproses`
    selected.value = []; selectAll.value = false
    showBulkConfirm.value = false; load()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { bulkBusy.value = false }
}

function openBulkResetPin() {
  if (!selectedCount.value) { msg.value = '⚠️ Pilih user terlebih dahulu'; return }
  bulkResetPinValue.value = '123456'
  showBulkResetPin.value = true
}

async function doBulkResetPin() {
  bulkBusy.value = true; msg.value = ''
  try {
    const promises = selectedUsers.value.map(u => 
      api('/api/users/reset-pin', { method: 'POST', body: { username: u.username, pin: bulkResetPinValue.value } })
    )
    await Promise.all(promises)
    msg.value = `✅ PIN ${selectedCount.value} user berhasil direset`
    selected.value = []; selectAll.value = false
    showBulkResetPin.value = false; load()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { bulkBusy.value = false }
}

// Export
function exportCsv() {
  const headers = ['Username', 'Nama Lengkap', 'Role', 'Tim', 'Branch', 'Status', 'Terakhir Login']
  const rows = filteredUsers.value.map(u => [
    u.username, u.full_name, roleLabel(u.role), u.team_name || '-', u.branch_code || '-', 
    u.is_active ? 'Aktif' : 'Nonaktif', u.last_login || '-'
  ])
  const csv = [headers, ...rows].map(r => r.map(c => `"${c}"`).join(',')).join('\n')
  const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = `users_${new Date().toISOString().slice(0, 10)}.csv`; a.click()
  URL.revokeObjectURL(url)
}

onMounted(load)
</script>

<template>
  <div>
    <!-- Header -->
    <div class="card card-pad" style="margin-bottom:16px;display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
      <div class="grow">
        <h3 style="margin:0;">👥 Manajemen User</h3>
        <p class="muted" style="font-size:11px;">Khusus Admin — pengelolaan akun &amp; hak akses per peran (ISO/IEC 27001 · A.8.2)</p>
      </div>
      <button class="btn btn-primary" @click="openForm(null)">➕ Tambah User</button>
      <button class="btn" @click="exportCsv" title="Export ke CSV">📥 Export</button>
    </div>

    <!-- Statistics -->
    <div class="stat-grid" style="margin-bottom:16px;">
      <StatCard icon="👥" label="Total User" :value="stats.total" color="#2563eb" />
      <StatCard icon="🟢" label="Aktif" :value="stats.active" color="#059669" />
      <StatCard icon="🔴" label="Nonaktif" :value="stats.inactive" color="#dc2626" />
      <StatCard icon="🛡️" label="Admin" :value="stats.byRole.admin || 0" color="#7c3aed" />
      <StatCard icon="🧾" label="GA" :value="stats.byRole.ga || 0" color="#0891b2" />
      <StatCard icon="💰" label="Finance" :value="stats.byRole.finance || 0" color="#d97706" />
    </div>

    <!-- Search & Filter -->
    <div class="card card-pad" style="margin-bottom:16px;">
      <div class="row" style="gap:8px;flex-wrap:wrap;align-items:center;">
        <input class="input" v-model="search" placeholder="🔍 Cari username atau nama..." style="min-width:200px;flex:1;" />
        <select class="select" v-model="filterRole" style="min-width:140px;">
          <option value="">Semua Role</option>
          <option v-for="r in ROLES" :key="r[0]" :value="r[0]">{{ r[1] }}</option>
        </select>
        <select class="select" v-model="filterStatus" style="min-width:120px;">
          <option value="">Semua Status</option>
          <option value="active">🟢 Aktif</option>
          <option value="inactive">🔴 Nonaktif</option>
        </select>
        <select class="select" v-model="filterBranch" style="min-width:140px;" v-if="branches.length">
          <option value="">Semua Cabang</option>
          <option v-for="b in branches" :key="b.code" :value="b.code">{{ b.name }}</option>
        </select>
        <span class="muted" style="font-size:12px;">{{ filteredUsers.length }} user</span>
      </div>
    </div>

    <!-- Bulk Actions -->
    <div v-if="selectedCount" class="card card-pad" style="margin-bottom:16px;background:var(--info-bg, #eff6ff);">
      <div class="row" style="gap:8px;align-items:center;flex-wrap:wrap;">
        <span class="badge badge-blue">{{ selectedCount }} dipilih</span>
        <button class="btn btn-sm" @click="openBulkAction('activate')">🟢 Aktifkan</button>
        <button class="btn btn-sm" @click="openBulkAction('deactivate')">🔴 Nonaktifkan</button>
        <button class="btn btn-sm" @click="openBulkResetPin">🔑 Reset PIN</button>
        <div class="spacer"></div>
        <button class="btn btn-sm" @click="selected = []; selectAll = false">✕ Batal Pilih</button>
      </div>
    </div>

    <!-- Message -->
    <div v-if="msg" class="alert" :class="msg.startsWith('✅') ? 'alert-success' : msg.startsWith('❌') ? 'alert-error' : 'alert-info'" style="margin-bottom:16px;">
      {{ msg }}
    </div>

    <!-- Loading / Error -->
    <div v-if="loading" class="empty skeleton">⏳ Memuat…</div>
    <div v-else-if="err" class="alert alert-error">{{ err }}</div>

    <!-- User Table -->
    <div v-else class="card">
      <div class="table-wrap">
        <table class="tbl">
          <thead>
            <tr>
              <th style="width:40px;"><input type="checkbox" v-model="selectAll" @change="toggleSelectAll" /></th>
              <th>Username</th>
              <th>Nama</th>
              <th>Role</th>
              <th>Tim</th>
              <th>Cabang</th>
              <th>Status</th>
              <th>Terakhir Login</th>
              <th style="min-width:140px;">Aksi</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="u in filteredUsers" :key="u.id" :class="{ 'row-inactive': !u.is_active }">
              <td><input type="checkbox" :checked="selected.includes(u.id)" @change="toggleSelect(u.id)" /></td>
              <td><b>{{ u.username }}</b></td>
              <td>{{ u.full_name }}</td>
              <td><span class="badge badge-purple">{{ roleLabel(u.role) }}</span></td>
              <td>{{ u.team_name || '—' }}</td>
              <td><span class="badge badge-blue" v-if="u.branch_code">{{ u.branch_code }}</span><span v-else class="muted">—</span></td>
              <td><span class="badge" :class="u.is_active ? 'badge-green' : 'badge-red'">{{ u.is_active ? '🟢 Aktif' : '🔴 Nonaktif' }}</span></td>
              <td class="muted" style="font-size:12px;">{{ u.last_login ? new Date(u.last_login).toLocaleString('id-ID') : '—' }}</td>
              <td style="white-space:nowrap;">
                <button class="btn btn-sm" :disabled="busy" @click="openForm(u)" title="✏️ Edit">✏️</button>
                <button class="btn btn-sm" :disabled="busy" @click="toggleUser(u)" :title="u.is_active ? '🚫 Nonaktifkan' : '🟢 Aktifkan'">{{ u.is_active ? '🚫' : '🟢' }}</button>
                <button class="btn btn-sm" :disabled="busy" @click="openResetPin(u)" title="🔑 Reset PIN">🔑</button>
                <button class="btn btn-sm" :disabled="busy" @click="openAuditLog(u)" title="📝 Audit Log">📝</button>
                <button class="btn btn-sm btn-danger" :disabled="busy" @click="openDeleteConfirm(u)" title="🗑 Nonaktifkan">🗑</button>
              </td>
            </tr>
            <tr v-if="!filteredUsers.length"><td colspan="9" class="empty">Tidak ada user ditemukan.</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Modal: Add/Edit User -->
    <Modal v-if="showForm" :title="form.username ? '✏️ Edit User' : '➕ Tambah User'" @close="showForm = false">
      <div class="form-grid">
        <div class="field"><label>Username *</label><input class="input" v-model="form.username" :disabled="!!form.username" required placeholder=" huruf kecil, tanpa spasi" /></div>
        <div class="field"><label>Nama Lengkap *</label><input class="input" v-model="form.full_name" required /></div>
        <div class="field"><label>Role *</label>
          <select class="select" v-model="form.role"><option v-for="r in ROLES" :key="r[0]" :value="r[0]">{{ r[1] }}</option></select>
        </div>
        <div class="field"><label>PIN {{ form.username && !form.pin ? '(kosong = tidak diubah)' : '' }}</label>
          <input class="input" v-model="form.pin" maxlength="6" inputmode="numeric" placeholder="6 digit angka" />
          <div v-if="form.pin && form.pin.length < 6" class="muted" style="font-size:11px;color:#dc2626;">PIN harus 6 digit</div>
        </div>
        <div class="field"><label>Tim Marketing</label><input class="input" v-model="form.team_name" placeholder="mis. Tim Yusie" /></div>
        <div class="field"><label>Cabang</label>
          <select class="select" v-model="form.branch_code">
            <option value="">Pusat</option>
            <option v-for="b in branches" :key="b.code" :value="b.code">{{ b.name }}</option>
          </select>
        </div>
        <div class="field"><label>Status</label>
          <select class="select" v-model="form.is_active"><option :value="true">🟢 Aktif</option><option :value="false">🔴 Nonaktif</option></select>
        </div>
      </div>
      <div class="row" style="justify-content:flex-end;margin-top:12px;gap:8px;">
        <button class="btn" @click="showForm = false">Batal</button>
        <button class="btn btn-primary" :disabled="busy || !form.username || !form.full_name || (form.pin && form.pin.length !== 6)" @click="save">💾 Simpan</button>
      </div>
    </Modal>

    <!-- Modal: Reset PIN -->
    <Modal v-if="showResetPin" title="🔑 Reset PIN" @close="showResetPin = false">
      <p class="muted" style="font-size:12px;margin-bottom:10px;">User: <b style="color:var(--text);">{{ resetPinData.username }}</b></p>
      <div class="field"><label>PIN baru (6 digit)</label>
        <input class="input" v-model="resetPinData.pin" maxlength="6" inputmode="numeric" placeholder="123456" />
      </div>
      <div class="row" style="justify-content:flex-end;margin-top:12px;gap:8px;">
        <button class="btn" @click="showResetPin = false">Batal</button>
        <button class="btn btn-primary" :disabled="busy || resetPinData.pin.length !== 6" @click="doResetPin">🔑 Reset</button>
      </div>
    </Modal>

    <!-- Modal: Delete Confirm -->
    <Modal v-if="showDeleteConfirm" title="🗑 Nonaktifkan User" @close="showDeleteConfirm = false; deleteTarget = null">
      <p style="margin:0 0 12px;">Yakin ingin menonaktifkan user <b>{{ deleteTarget?.username }}</b> ({{ deleteTarget?.full_name }})?</p>
      <p class="muted" style="font-size:12px;">User akan dinonaktifkan dan tidak bisa login.</p>
      <div class="row" style="justify-content:flex-end;margin-top:12px;gap:8px;">
        <button class="btn" @click="showDeleteConfirm = false; deleteTarget = null">Batal</button>
        <button class="btn btn-danger" :disabled="busy" @click="doDelete">🗑 Nonaktifkan</button>
      </div>
    </Modal>

    <!-- Modal: Bulk Action Confirm -->
    <Modal v-if="showBulkConfirm" :title="bulkAction === 'activate' ? '🟢 Aktifkan User' : '🔴 Nonaktifkan User'" @close="showBulkConfirm = false">
      <p style="margin:0 0 12px;">Yakin ingin {{ bulkAction === 'activate' ? 'mengaktifkan' : 'menonaktifkan' }} <b>{{ selectedCount }} user</b>?</p>
      <ul style="margin:0 0 12px;padding-left:18px;font-size:13px;">
        <li v-for="u in selectedUsers.slice(0, 10)" :key="u.id">{{ u.username }} — {{ u.full_name }}</li>
        <li v-if="selectedCount > 10" class="muted">...dan {{ selectedCount - 10 }} lainnya</li>
      </ul>
      <div class="row" style="justify-content:flex-end;margin-top:12px;gap:8px;">
        <button class="btn" @click="showBulkConfirm = false">Batal</button>
        <button class="btn" :class="bulkAction === 'activate' ? 'btn-primary' : 'btn-danger'" :disabled="bulkBusy" @click="doBulkAction">Konfirmasi</button>
      </div>
    </Modal>

    <!-- Modal: Bulk Reset PIN -->
    <Modal v-if="showBulkResetPin" title="🔑 Reset PIN Massal" @close="showBulkResetPin = false">
      <p style="margin:0 0 12px;">Reset PIN <b>{{ selectedCount }} user</b> ke PIN yang sama.</p>
      <div class="field"><label>PIN baru (6 digit)</label>
        <input class="input" v-model="bulkResetPinValue" maxlength="6" inputmode="numeric" />
      </div>
      <div class="row" style="justify-content:flex-end;margin-top:12px;gap:8px;">
        <button class="btn" @click="showBulkResetPin = false">Batal</button>
        <button class="btn btn-primary" :disabled="bulkBusy || bulkResetPinValue.length !== 6" @click="doBulkResetPin">🔑 Reset Semua</button>
      </div>
    </Modal>

    <!-- Modal: Audit Log -->
    <Modal v-if="showAuditLog" :title="'📝 Audit Log — ' + (auditLogUser?.username || '')" @close="showAuditLog = false" style="max-width:700px;">
      <div v-if="auditLoading" class="empty skeleton" style="padding:16px;">⏳ Memuat log…</div>
      <div v-else-if="!auditLogs.length" class="empty" style="padding:16px;">Tidak ada log aktivitas.</div>
      <div v-else class="table-wrap" style="max-height:400px;overflow-y:auto;">
        <table class="tbl" style="font-size:12px;">
          <thead><tr><th>Waktu</th><th>Aksi</th><th>Detail</th></tr></thead>
          <tbody>
            <tr v-for="log in auditLogs" :key="log.id">
              <td class="muted" style="white-space:nowrap;">{{ new Date(log.created_at).toLocaleString('id-ID') }}</td>
              <td><span class="badge badge-blue">{{ log.action }}</span></td>
              <td style="font-size:11px;max-width:300px;overflow:hidden;text-overflow:ellipsis;">{{ log.new_data ? JSON.stringify(log.new_data) : '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
.row-inactive { opacity: 0.6; }
.row { display: flex; flex-wrap: wrap; }
.grow { flex: 1; min-width: 200px; }
.spacer { flex: 1; }
.select { padding: 6px 10px; border: 1px solid var(--border, #e2e8f0); border-radius: 8px; background: var(--card, #fff); color: var(--text, #0f172a); font-size: 13px; }
.input { padding: 6px 10px; border: 1px solid var(--border, #e2e8f0); border-radius: 8px; background: var(--card, #fff); color: var(--text, #0f172a); font-size: 13px; }
</style>
