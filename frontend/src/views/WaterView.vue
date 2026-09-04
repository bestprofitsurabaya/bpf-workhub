<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { useAuthStore } from '../stores/auth'
import Modal from '../components/Modal.vue'

const auth = useAuthStore()
const isOB = auth.role === 'ob'
const isFinance = ['finance', 'admin'].includes(auth.role)

const loading = ref(true)
const err = ref('')
const msg = ref('')
const busy = ref(false)

// ---- Master merk (dropdown) ----
const types = ref([])          // [{id, name, brands: [...]}]
const typeOptions = computed(() => types.value.map((t) => t.name))

// ---- Form pengajuan OB ----
const showForm = ref(false)
const form = ref({ purchase_date: new Date().toISOString().slice(0, 10), items: [] })
const fotoBefore = ref(null)
const fotoAfter = ref(null)
const fotoBeforeUrl = ref('')
const fotoAfterUrl = ref('')

// ---- Daftar pengajuan ----
const purchases = ref([])
const selected = ref(null)     // detail
const verifyModal = ref(null)  // { kind: 'verify'|'reject', id }
const verifyForm = ref({ remark: '', note: '', reason: '' })

// ---- Kelola merk (finance) ----
const brandModal = ref(false)
const brandForm = ref({ type_id: null, brand: '' })

const STATUS_BADGE = { pending: 'badge-amber', verified: 'badge-green', rejected: 'badge-red' }
const STATUS_LABEL = { pending: 'Menunggu Verifikasi', verified: 'Terverifikasi', rejected: 'Ditolak' }
const fmtDate = (d) => (d ? String(d).slice(0, 10) : '-')
const fmtDateTime = (d) => (d ? String(d).replace('T', ' ').slice(0, 16) : '-')
const brandsOf = (typeName) => {
  const t = types.value.find((x) => x.name === typeName)
  return t ? t.brands : []
}
const itemTotal = (p) => (p.items || []).reduce((s, i) => s + Number(i.quantity || 0), 0)

function newItem() {
  return { drink_type: 'Galon', brand: '', satuan: 'pcs', quantity: 1 }
}
function addItem() { form.value.items.push(newItem()) }
function removeItem(i) { form.value.items.splice(i, 1) }

function onPickFoto(e, which) {
  const f = e.target.files?.[0]
  if (!f) return
  if (which === 'before') { fotoBefore.value = f; fotoBeforeUrl.value = URL.createObjectURL(f) }
  else { fotoAfter.value = f; fotoAfterUrl.value = URL.createObjectURL(f) }
}

async function loadMaster() {
  try {
    const d = await api('/api/water/brands')
    types.value = Array.isArray(d?.types) ? d.types : []
  } catch { /* noop */ }
}

async function load() {
  loading.value = true; err.value = ''
  try {
    await loadMaster()
    const list = await api('/api/water/purchases')
    purchases.value = Array.isArray(list) ? list : []
  } catch (e) { err.value = e.message }
  finally { loading.value = false }
}

async function submitForm() {
  if (!form.value.purchase_date) { msg.value = '❌ Tanggal pengiriman wajib diisi'; return }
  if (!form.value.items.length) { msg.value = '❌ Minimal satu item'; return }
  for (const it of form.value.items) {
    if (!it.brand || !(Number(it.quantity) > 0)) { msg.value = '❌ Setiap item wajib: merk & kuantitas > 0'; return }
  }
  if (!fotoBefore.value || !fotoAfter.value) { msg.value = '❌ Foto sebelum & sesudah diisi wajib diunggah'; return }
  busy.value = true; msg.value = ''
  try {
    const fd = new FormData()
    fd.append('purchase_date', form.value.purchase_date)
    fd.append('items', JSON.stringify(form.value.items.map((i) => ({
      drink_type: i.drink_type, brand: i.brand, satuan: i.satuan, quantity: Number(i.quantity),
    }))))
    fd.append('foto_before', fotoBefore.value)
    fd.append('foto_after', fotoAfter.value)
    const csrf = localStorage.getItem('bpf_csrf') || sessionStorage.getItem('bpf_csrf') || ''
    const r = await fetch('/api/water/purchases', {
      method: 'POST',
      headers: { Accept: 'application/json', 'X-CSRF-Token': csrf },
      body: fd,
    })
    const data = await r.json().catch(() => ({}))
    if (!r.ok) throw new Error(data.msg || data.error || `HTTP ${r.status}`)
    msg.value = '✅ ' + (data.msg || 'Pengajuan terkirim')
    showForm.value = false
    form.value = { purchase_date: new Date().toISOString().slice(0, 10), items: [] }
    form.value.items.push(newItem())
    fotoBefore.value = fotoAfter.value = null
    fotoBeforeUrl.value = fotoAfterUrl.value = ''
    load()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { busy.value = false }
}

async function openDetail(p) {
  selected.value = null
  try {
    selected.value = await api(`/api/water/purchases/${p.id}`)
  } catch (e) { alert('❌ ' + e.message) }
}

function openVerify(kind, p) {
  verifyForm.value = { remark: '', note: '', reason: '' }
  verifyModal.value = { kind, id: p.id, display_id: p.display_id }
}

async function submitVerify() {
  const v = verifyModal.value
  if (!v) return
  if (v.kind === 'verify' && !verifyForm.value.remark.trim()) { alert('Remark verifikasi wajib diisi'); return }
  if (v.kind === 'reject' && !verifyForm.value.reason.trim()) { alert('Alasan penolakan wajib diisi'); return }
  busy.value = true
  try {
    const ep = v.kind === 'verify' ? `/api/water/purchases/${v.id}/verify` : `/api/water/purchases/${v.id}/reject`
    const body = v.kind === 'verify' ? { remark: verifyForm.value.remark, note: verifyForm.value.note } : { reason: verifyForm.value.reason }
    const d = await api(ep, { method: 'POST', body })
    alert(d.msg || 'Berhasil')
    verifyModal.value = null
    load()
  } catch (e) { alert('❌ ' + e.message) }
  finally { busy.value = false }
}

function openBrandModal() {
  brandForm.value = { type_id: types.value[0]?.id ?? null, brand: '' }
  brandModal.value = true
}

async function addBrand() {
  if (!brandForm.value.type_id || !brandForm.value.brand.trim()) { alert('Pilih tipe dan isi merk'); return }
  busy.value = true
  try {
    const d = await api('/api/water/brands', { method: 'POST', body: { type_id: brandForm.value.type_id, brand: brandForm.value.brand.trim() } })
    alert(d.msg || 'Merk disimpan')
    brandModal.value = false
    loadMaster(); load()
  } catch (e) { alert('❌ ' + e.message) }
  finally { busy.value = false }
}

async function deleteBrand(b) {
  if (!confirm(`Nonaktifkan merk "${b.brand}"?`)) return
  busy.value = true
  try {
    const d = await api(`/api/water/brands/${b.id}`, { method: 'DELETE' })
    alert(d.msg || 'Merk dinonaktifkan')
    loadMaster(); load()
  } catch (e) { alert('❌ ' + e.message) }
  finally { busy.value = false }
}

function downloadPdf(p) {
  window.open(`/api/water/purchases/${p.id}/pdf`, '_blank')
}

onMounted(() => { form.value.items.push(newItem()); load() })
</script>

<template>
  <div>
    <div v-if="msg" class="alert" :class="msg.startsWith('✅') ? 'alert-success' : 'alert-error'">{{ msg }}</div>

    <!-- Header + aksi -->
    <div class="card card-pad" style="margin-bottom:16px;display:flex;align-items:center;flex-wrap:wrap;gap:8px;">
      <div class="grow">
        <h3 style="margin:0;">🚰 Tanda Terima Air Minum</h3>
        <p class="muted" style="font-size:11px;">
          {{ isOB ? 'Ajukan pembelian air minum — Finance akan memverifikasi' : 'Verifikasi pengajuan & kelola merk air minum' }}
        </p>
      </div>
      <button v-if="isOB" class="btn btn-primary" @click="showForm = true">➕ Ajukan Pembelian</button>
      <button v-if="isFinance" class="btn" @click="openBrandModal">🏷️ Kelola Merk</button>
    </div>

    <div v-if="loading" class="empty skeleton">⏳ Memuat…</div>
    <div v-else-if="err" class="alert alert-error">{{ err }}</div>
    <template v-else>
      <!-- Daftar pengajuan -->
      <div class="card">
        <div class="card-pad row" style="border-bottom:1px solid var(--border);">
          <b>📋 Pengajuan {{ isOB ? 'Saya' : 'Semua' }}</b>
          <span class="badge badge-blue">{{ purchases.length }}</span>
        </div>
        <div v-if="!purchases.length" class="empty">Belum ada pengajuan.</div>
        <div v-for="p in purchases" :key="p.id" class="cash-item">
          <div class="row" style="align-items:center;flex-wrap:wrap;gap:8px;">
            <div class="grow">
              <div class="row" style="gap:8px;align-items:center;">
                <b>{{ p.display_id }}</b>
                <span class="badge" :class="STATUS_BADGE[p.status] || 'badge-gray'">{{ STATUS_LABEL[p.status] || p.status }}</span>
              </div>
              <div class="muted" style="font-size:12px;margin-top:4px;">
                🗓️ {{ fmtDate(p.purchase_date) }} · 👤 {{ p.ob_name }} · 📦 {{ itemTotal(p) }} item
              </div>
            </div>
            <div class="row" style="gap:6px;">
              <button class="btn btn-sm" @click="openDetail(p)">👁️ Detail</button>
              <button v-if="isFinance && p.status === 'pending'" class="btn btn-sm btn-success" @click="openVerify('verify', p)">✅ Verifikasi</button>
              <button v-if="isFinance && p.status === 'pending'" class="btn btn-sm btn-danger" @click="openVerify('reject', p)">✖ Tolak</button>
              <button v-if="p.status === 'verified'" class="btn btn-sm" @click="downloadPdf(p)">📄 PDF</button>
            </div>
          </div>
        </div>
      </div>

      <!-- Master merk (finance) -->
      <div v-if="isFinance" class="card" style="margin-top:16px;">
        <div class="card-pad row" style="border-bottom:1px solid var(--border);">
          <b>🏷️ Master Merk Air Minum</b>
          <span class="badge badge-purple">{{ types.length }} tipe</span>
        </div>
        <div class="card-pad" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;">
          <div v-for="t in types" :key="t.id">
            <b style="color:var(--accent);">{{ t.name }}</b>
            <div v-if="!t.brands.length" class="muted" style="font-size:12px;margin-top:4px;">Belum ada merk.</div>
            <div v-for="b in t.brands" :key="b.id" class="row" style="justify-content:space-between;align-items:center;gap:6px;margin-top:4px;">
              <span style="font-size:13px;">• {{ b.brand }}</span>
              <button class="btn btn-sm btn-danger" :disabled="busy" style="padding:1px 6px;font-size:11px;" @click="deleteBrand(b)" title="Nonaktifkan">✖</button>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- Modal detail -->
    <Modal v-if="selected" :title="'👁️ ' + (selected.display_id || 'Detail')" @close="selected = null" wide>
      <template v-if="selected">
        <div class="row" style="gap:8px;align-items:center;">
          <b>{{ selected.display_id }}</b>
          <span class="badge" :class="STATUS_BADGE[selected.status] || 'badge-gray'">{{ STATUS_LABEL[selected.status] || selected.status }}</span>
          <span class="badge" v-if="selected.status === 'verified'">✔ {{ selected.verified_by || '' }}</span>
        </div>
        <p class="muted" style="font-size:12px;">
          🗓️ {{ fmtDate(selected.purchase_date) }} · 👤 {{ selected.ob_name }} · 🕐 {{ fmtDateTime(selected.created_at) }}
        </p>
        <table class="tbl" style="margin-top:8px;">
          <thead><tr><th>Jenis</th><th>Merk</th><th>Satuan</th><th>Qty</th></tr></thead>
          <tbody>
            <tr v-for="(it, i) in selected.items" :key="i">
              <td>{{ it.drink_type }}</td><td><b>{{ it.brand }}</b></td><td>{{ it.satuan }}</td><td>{{ it.quantity }}</td>
            </tr>
          </tbody>
        </table>
        <div v-if="selected.status === 'verified'" style="margin-top:10px;padding:10px;background:var(--bg-alt,#f0fdf4);border:1px solid #86efac;border-radius:8px;">
          <b style="color:#059669;">✔ Terverifikasi</b>
          <div style="font-size:13px;margin-top:4px;"><b>Remark:</b> {{ selected.remark || '-' }}</div>
          <div v-if="selected.note" style="font-size:13px;margin-top:2px;"><b>Catatan:</b> {{ selected.note }}</div>
          <div class="muted" style="font-size:11px;margin-top:4px;">Oleh {{ selected.verified_by }} · {{ fmtDateTime(selected.verified_at) }}</div>
        </div>
        <div v-if="selected.status === 'rejected'" style="margin-top:10px;padding:10px;background:#fef2f2;border:1px solid #fca5a5;border-radius:8px;">
          <b style="color:#dc2626;">✖ Ditolak</b>
          <div style="font-size:13px;margin-top:4px;">{{ selected.rejection_reason || '-' }}</div>
        </div>
        <div class="row" style="gap:12px;margin-top:12px;">
          <div v-if="selected.foto_before" style="flex:1;">
            <img :src="'/uploads/' + selected.foto_before" style="width:100%;border-radius:8px;border:1px solid var(--border);" alt="Sebelum" />
            <div class="muted" style="font-size:11px;text-align:center;">📷 Sebelum diisi</div>
          </div>
          <div v-if="selected.foto_after" style="flex:1;">
            <img :src="'/uploads/' + selected.foto_after" style="width:100%;border-radius:8px;border:1px solid var(--border);" alt="Sesudah" />
            <div class="muted" style="font-size:11px;text-align:center;">📷 Sesudah diisi</div>
          </div>
        </div>
        <div class="row" style="justify-content:flex-end;gap:8px;margin-top:12px;">
          <button v-if="selected.status === 'verified'" class="btn btn-primary" @click="downloadPdf(selected)">📄 Unduh PDF Tanda Terima</button>
          <button class="btn" @click="selected = null">Tutup</button>
        </div>
      </template>
    </Modal>

    <!-- Modal form pengajuan (OB) -->
    <Modal v-if="showForm" title="➕ Ajukan Pembelian Air Minum" @close="showForm = false" wide>
      <div class="field"><label>Tanggal Pengiriman *</label><input class="input" type="date" v-model="form.purchase_date" /></div>
      <div class="row" style="justify-content:space-between;align-items:center;margin-top:10px;">
        <b style="font-size:13px;">📦 Item Pembelian</b>
        <button class="btn btn-sm" @click="addItem">➕ Tambah Item</button>
      </div>
      <div v-for="(it, i) in form.items" :key="i" class="row" style="gap:6px;margin-top:6px;align-items:flex-end;flex-wrap:wrap;">
        <div class="field" style="min-width:110px;">
          <label>Jenis</label>
          <select class="select" v-model="it.drink_type">
            <option v-for="t in typeOptions" :key="t" :value="t">{{ t }}</option>
          </select>
        </div>
        <div class="field grow">
          <label>Merk *</label>
          <select class="select" v-model="it.brand">
            <option value="" disabled>— pilih merk —</option>
            <option v-for="b in brandsOf(it.drink_type)" :key="b.id" :value="b.brand">{{ b.brand }}</option>
          </select>
        </div>
        <div class="field" style="width:100px;">
          <label>Satuan</label>
          <select class="select" v-model="it.satuan">
            <option value="pcs">pcs</option><option value="dus">dus</option><option value="karton">karton</option>
            <option value="botol">botol</option><option value="gelas">gelas</option><option value="galon">galon</option>
          </select>
        </div>
        <div class="field" style="width:90px;">
          <label>Qty *</label>
          <input class="input" type="number" min="1" v-model="it.quantity" />
        </div>
        <button class="btn btn-sm btn-danger" style="margin-bottom:6px;" @click="removeItem(i)" :disabled="form.items.length === 1">✖</button>
      </div>
      <div class="muted" style="font-size:11px;margin-top:6px;">💡 Merk berasal dari master Finance — jika belum ada, hubungi Finance.</div>

      <div class="row" style="gap:12px;margin-top:14px;">
        <div class="field grow">
          <label>📷 Foto SEBELUM diisi (wajib) *</label>
          <input class="input" type="file" accept="image/*" @change="onPickFoto($event, 'before')" />
          <img v-if="fotoBeforeUrl" :src="fotoBeforeUrl" style="width:100%;max-height:160px;object-fit:cover;border-radius:8px;margin-top:6px;border:1px solid var(--border);" />
        </div>
        <div class="field grow">
          <label>📷 Foto SESUDAH diisi (wajib) *</label>
          <input class="input" type="file" accept="image/*" @change="onPickFoto($event, 'after')" />
          <img v-if="fotoAfterUrl" :src="fotoAfterUrl" style="width:100%;max-height:160px;object-fit:cover;border-radius:8px;margin-top:6px;border:1px solid var(--border);" />
        </div>
      </div>
      <div class="row" style="justify-content:flex-end;gap:8px;margin-top:12px;">
        <button class="btn" @click="showForm = false">Batal</button>
        <button class="btn btn-primary" :disabled="busy" @click="submitForm">🚀 Kirim ke Finance</button>
      </div>
    </Modal>

    <!-- Modal verifikasi (finance) -->
    <Modal v-if="verifyModal" :title="verifyModal.kind === 'verify' ? '✅ Verifikasi ' + verifyModal.display_id : '✖ Tolak ' + verifyModal.display_id" @close="verifyModal = null">
      <template v-if="verifyModal.kind === 'verify'">
        <div class="field"><label>Remark *</label><textarea class="input" v-model="verifyForm.remark" rows="3" placeholder="Ringkasan hasil verifikasi..."></textarea></div>
        <div class="field"><label>Note tambahan (opsional)</label><textarea class="input" v-model="verifyForm.note" rows="2" placeholder="Catatan tambahan bila diperlukan..."></textarea></div>
      </template>
      <template v-else>
        <div class="field"><label>Alasan penolakan *</label><textarea class="input" v-model="verifyForm.reason" rows="3" placeholder="Alasan penolakan..."></textarea></div>
      </template>
      <div class="row" style="justify-content:flex-end;gap:8px;">
        <button class="btn" @click="verifyModal = null">Batal</button>
        <button class="btn btn-primary" :disabled="busy" @click="submitVerify">
          {{ verifyModal.kind === 'verify' ? '✅ Verifikasi' : '✖ Tolak' }}
        </button>
      </div>
    </Modal>

    <!-- Modal kelola merk (finance) -->
    <Modal v-if="brandModal" title="🏷️ Tambah Merk Air Minum" @close="brandModal = false">
      <div class="field"><label>Jenis</label>
        <select class="select" v-model="brandForm.type_id">
          <option v-for="t in types" :key="t.id" :value="t.id">{{ t.name }}</option>
        </select>
      </div>
      <div class="field"><label>Nama Merk *</label><input class="input" v-model="brandForm.brand" placeholder="mis. AQUA / Le Minerale / VIT" /></div>
      <div class="row" style="justify-content:flex-end;gap:8px;margin-top:12px;">
        <button class="btn" @click="brandModal = false">Batal</button>
        <button class="btn btn-primary" :disabled="busy || !brandForm.brand.trim()" @click="addBrand">💾 Simpan</button>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
.cash-item { padding: 14px; border-bottom: 1px solid var(--border); }
.cash-item:last-child { border-bottom: none; }
</style>
