<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import PageHeader from '../components/PageHeader.vue'
import Modal from '../components/Modal.vue'
import LoadingState from '../components/LoadingState.vue'
import ErrorState from '../components/ErrorState.vue'
import { formatDate, formatDateTime, formatRupiah } from '../utils/format'
import {
  STATUS_LABEL, STATUS_BADGE, COND_META, EVENT_LABEL, assetTitle, categoryLabel, downloadBlob,
} from '../utils/itAssets'

const route = useRoute()
const router = useRouter()

const tag = computed(() => String(route.params.tag || '').toUpperCase())
const asset = ref(null)
const meta = ref({ categories: [], statuses: [], conditions: [] })
const loading = ref(true)
const err = ref('')
const msg = ref('')
const msgType = ref('success')
const busy = ref(false)

function flash(text, type = 'success') {
  msg.value = text
  msgType.value = type
  window.clearTimeout(flash._t)
  flash._t = window.setTimeout(() => { msg.value = '' }, 6000)
}

async function load() {
  loading.value = true; err.value = ''
  try {
    const [detail, m] = await Promise.all([
      api(`/api/it/assets/${encodeURIComponent(tag.value)}`),
      api('/api/it/meta'),
    ])
    asset.value = detail.data
    meta.value = m
  } catch (e) {
    err.value = e.message
  } finally {
    loading.value = false
  }
}

// ------------------------------------------------------------- ubah kondisi
const condNote = ref('')
const condPhoto = ref(null)
const condPhotoUrl = ref('')
function onPhoto(e) {
  const file = e.target.files?.[0] || null
  condPhoto.value = file
  if (condPhotoUrl.value) URL.revokeObjectURL(condPhotoUrl.value)
  condPhotoUrl.value = file ? URL.createObjectURL(file) : ''
}
async function setCondition(cond) {
  if (!asset.value) return
  busy.value = true
  try {
    const fd = new FormData()
    fd.append('cond', cond)
    fd.append('note', condNote.value)
    if (cond === 'rusak_berat' && asset.value.status === 'aktif') fd.append('status', 'service')
    if (condPhoto.value) fd.append('photo', condPhoto.value)
    const csrf = localStorage.getItem('bpf_csrf') || sessionStorage.getItem('bpf_csrf') || ''
    const r = await fetch(`/api/it/assets/${encodeURIComponent(tag.value)}/condition`, {
      method: 'POST',
      headers: { Accept: 'application/json', 'X-CSRF-Token': csrf },
      body: fd,
    })
    const data = await r.json().catch(() => ({}))
    if (!r.ok) throw new Error(data.msg || data.error || `HTTP ${r.status}`)
    flash(`✅ ${data.msg}`)
    condNote.value = ''
    condPhoto.value = null
    condPhotoUrl.value = ''
    await load()
  } catch (e) {
    flash('❌ ' + e.message, 'error')
  } finally {
    busy.value = false
  }
}

// ---------------------------------------------------------------- edit aset
const editModal = ref(false)
const editForm = ref({})
const saving = ref(false)
function openEdit() {
  const a = asset.value || {}
  editForm.value = {
    category: a.category, brand: a.brand || '', model: a.model || '',
    serial_number: a.serial_number || '', status: a.status, cond: a.cond,
    location_room: a.location_room || '', location_detail: a.location_detail || '',
    assigned_to: a.assigned_to || '', vendor: a.vendor || '',
    purchase_date: (a.purchase_date || '').slice(0, 10),
    purchase_price: a.purchase_price ?? '', warranty_until: (a.warranty_until || '').slice(0, 10),
    hostname: a.hostname || '', ip_address: a.ip_address || '', mac_address: a.mac_address || '',
    os_name: a.os_name || '', notes: a.notes || '',
  }
  editModal.value = true
}
async function saveEdit() {
  saving.value = true
  try {
    const res = await api(`/api/it/assets/${encodeURIComponent(tag.value)}`, {
      method: 'PATCH', body: editForm.value,
    })
    flash(`✅ ${res.msg}`)
    editModal.value = false
    await load()
  } catch (e) {
    flash('❌ ' + e.message, 'error')
  } finally {
    saving.value = false
  }
}

// ------------------------------------------------------------------ catatan
const noteModal = ref(false)
const noteForm = ref({ kind: 'note', note: '' })
async function saveNote() {
  if (!noteForm.value.note.trim()) { flash('Catatan wajib diisi', 'error'); return }
  saving.value = true
  try {
    const res = await api(`/api/it/assets/${encodeURIComponent(tag.value)}/events`, {
      method: 'POST', body: noteForm.value,
    })
    flash(`✅ ${res.msg}`)
    noteModal.value = false
    noteForm.value = { kind: 'note', note: '' }
    await load()
  } catch (e) {
    flash('❌ ' + e.message, 'error')
  } finally {
    saving.value = false
  }
}

// -------------------------------------------------------------------- label
async function printLabel() {
  try {
    const blob = await api(`/api/it/assets/${encodeURIComponent(tag.value)}/label.pdf`, { raw: true })
    downloadBlob(blob, `label_${tag.value}.pdf`)
    flash('✅ Label diunduh')
    await load()
  } catch (e) {
    flash('❌ ' + e.message, 'error')
  }
}

function eventSummary(ev) {
  if (ev.before_json || ev.after_json) {
    const before = ev.before_json || {}
    const after = ev.after_json || {}
    const parts = []
    for (const key of Object.keys(after)) {
      if (before[key] !== after[key]) parts.push(`${key}: ${before[key] ?? '—'} → ${after[key] ?? '—'}`)
    }
    return parts.join(' · ')
  }
  return ''
}

onMounted(load)
</script>

<template>
  <div class="it-detail">
    <PageHeader :icon="asset ? (COND_META[asset.cond]?.icon || '📦') : '📦'"
                :title="asset ? asset.asset_tag : 'Detail Aset'"
                :subtitle="asset ? assetTitle(asset) : 'Memuat…'">
      <button class="btn" @click="router.push('/it/inventory?tab=assets')">← Daftar Aset</button>
      <button v-if="asset" class="btn" @click="printLabel">🏷️ Cetak Label</button>
      <button v-if="asset" class="btn btn-primary" @click="openEdit">✏️ Edit Data</button>
    </PageHeader>

    <div v-if="msg" class="alert" :class="msgType === 'error' ? 'alert-error' : 'alert-success'" style="margin-bottom:14px;">{{ msg }}</div>

    <LoadingState v-if="loading" />
    <ErrorState v-else-if="err" :message="err" @retry="load" />

    <template v-else-if="asset">
      <div class="detail-grid">
        <!-- identitas -->
        <div class="card card-pad">
          <h3>Identitas</h3>
          <dl class="kv">
            <dt>Tag</dt><dd class="mono strong">{{ asset.asset_tag }}</dd>
            <dt>Kategori</dt><dd>{{ categoryLabel(asset.category) }}</dd>
            <dt>Merek / Model</dt><dd>{{ assetTitle(asset) }}</dd>
            <dt>Nomor Seri</dt><dd>{{ asset.serial_number || '—' }}</dd>
            <dt>Status</dt>
            <dd><span class="badge" :class="STATUS_BADGE[asset.status] || 'badge-gray'">{{ STATUS_LABEL[asset.status] || asset.status }}</span></dd>
            <dt>Kondisi</dt>
            <dd><span class="badge" :class="COND_META[asset.cond]?.badge || 'badge-gray'">{{ COND_META[asset.cond]?.icon }} {{ COND_META[asset.cond]?.label || asset.cond }}</span></dd>
            <dt>Sumber</dt><dd>{{ asset.source }}</dd>
          </dl>
        </div>

        <!-- penempatan -->
        <div class="card card-pad">
          <h3>Penempatan &amp; Garansi</h3>
          <dl class="kv">
            <dt>Ruangan</dt><dd>{{ asset.location_room || '—' }}</dd>
            <dt>Detail Lokasi</dt><dd>{{ asset.location_detail || '—' }}</dd>
            <dt>PIC / Pemakai</dt><dd>{{ asset.assigned_to || '—' }}</dd>
            <dt>Tanggal Beli</dt><dd>{{ formatDate(asset.purchase_date) }}</dd>
            <dt>Harga Beli</dt><dd>{{ asset.purchase_price != null ? formatRupiah(asset.purchase_price) : '—' }}</dd>
            <dt>Garansi</dt><dd>{{ formatDate(asset.warranty_until) }}</dd>
            <dt>Vendor</dt><dd>{{ asset.vendor || '—' }}</dd>
          </dl>
        </div>

        <!-- jaringan -->
        <div class="card card-pad">
          <h3>Jaringan &amp; Sistem</h3>
          <dl class="kv">
            <dt>Hostname</dt><dd class="mono">{{ asset.hostname || '—' }}</dd>
            <dt>IP</dt><dd class="mono">{{ asset.ip_address || '—' }}</dd>
            <dt>MAC</dt><dd class="mono">{{ asset.mac_address || '—' }}</dd>
            <dt>OS</dt><dd>{{ asset.os_name || '—' }}</dd>
            <dt>Terakhir dilihat</dt><dd>{{ asset.last_seen_at ? formatDateTime(asset.last_seen_at) : '—' }}</dd>
            <dt>Label dicetak</dt><dd>{{ asset.label_printed_at ? formatDateTime(asset.label_printed_at) : 'belum' }}</dd>
          </dl>
        </div>

        <!-- kondisi cepat -->
        <div class="card card-pad">
          <h3>Ubah Kondisi Cepat</h3>
          <div class="cond-buttons">
            <button v-for="(c, key) in COND_META" :key="key" class="cond-btn" :class="{ on: asset.cond === key }"
                    :style="{ '--c': c.color }" :disabled="busy" @click="setCondition(key)">
              <span class="cond-icon">{{ c.icon }}</span>
              <span>{{ c.label }}</span>
            </button>
          </div>
          <div class="field" style="margin-top:10px;">
            <label>Catatan (opsional)</label>
            <input class="input" v-model="condNote" placeholder="cth: layar berkedip setelah listrik padam" />
          </div>
          <div class="field">
            <label>Foto (opsional)</label>
            <input class="input" type="file" accept="image/*" capture="environment" @change="onPhoto" />
            <img v-if="condPhotoUrl" :src="condPhotoUrl" alt="Pratinjau foto kondisi" class="photo-preview" />
          </div>
          <p class="muted tiny">Kondisi berat otomatis mengusulkan status <em>service</em>. Semua perubahan masuk riwayat.</p>
          <button class="btn" style="margin-top:6px;" @click="noteModal = true">📝 Tambah Catatan / Servis</button>
        </div>
      </div>

      <div class="card card-pad" style="margin-top:16px;">
        <h3>Riwayat</h3>
        <div v-if="!asset.events?.length" class="muted">Belum ada riwayat.</div>
        <ul v-else class="timeline">
          <li v-for="ev in asset.events" :key="ev.id">
            <span class="badge badge-gray">{{ EVENT_LABEL[ev.kind] || ev.kind }}</span>
            <span class="strong">{{ ev.note || eventSummary(ev) || '—' }}</span>
            <span v-if="ev.note && eventSummary(ev)" class="muted tiny">{{ eventSummary(ev) }}</span>
            <a v-if="ev.photo_path" :href="`/uploads/${ev.photo_path}`" target="_blank" rel="noopener" class="tiny">📷 foto</a>
            <span class="when">{{ formatDateTime(ev.created_at) }} · {{ ev.actor || '—' }}</span>
          </li>
        </ul>
      </div>

      <p class="muted tiny" style="margin-top:12px;">
        Perubahan tercatat append-only di tabel riwayat. Hapus permanen tidak disediakan —
        gunakan status <code>disposed</code> agar tag tidak dipakai ulang.
      </p>
    </template>

    <!-- modal edit -->
    <Modal v-if="editModal" :title="'✏️ Edit — ' + tag" wide @close="editModal = false">
      <div class="form-grid">
        <div class="field">
          <label>Kategori</label>
          <select class="select" v-model="editForm.category">
            <option v-for="c in meta.categories" :key="c.code" :value="c.code">{{ c.icon }} {{ c.label }}</option>
          </select>
        </div>
        <div class="field"><label>Merek</label><input class="input" v-model="editForm.brand" /></div>
        <div class="field"><label>Model</label><input class="input" v-model="editForm.model" /></div>
        <div class="field"><label>Nomor Seri</label><input class="input" v-model="editForm.serial_number" /></div>
        <div class="field">
          <label>Status</label>
          <select class="select" v-model="editForm.status">
            <option v-for="s in meta.statuses" :key="s" :value="s">{{ STATUS_LABEL[s] || s }}</option>
          </select>
        </div>
        <div class="field">
          <label>Kondisi</label>
          <select class="select" v-model="editForm.cond">
            <option v-for="c in meta.conditions" :key="c" :value="c">{{ COND_META[c]?.label || c }}</option>
          </select>
        </div>
        <div class="field"><label>Ruangan</label><input class="input" v-model="editForm.location_room" /></div>
        <div class="field"><label>Detail Lokasi</label><input class="input" v-model="editForm.location_detail" /></div>
        <div class="field"><label>PIC</label><input class="input" v-model="editForm.assigned_to" /></div>
        <div class="field"><label>Vendor</label><input class="input" v-model="editForm.vendor" /></div>
        <div class="field"><label>Tanggal Beli</label><input class="input" type="date" v-model="editForm.purchase_date" /></div>
        <div class="field"><label>Harga Beli</label><input class="input" type="number" min="0" v-model="editForm.purchase_price" /></div>
        <div class="field"><label>Garansi Sampai</label><input class="input" type="date" v-model="editForm.warranty_until" /></div>
        <div class="field"><label>Hostname</label><input class="input" v-model="editForm.hostname" /></div>
        <div class="field"><label>IP</label><input class="input" v-model="editForm.ip_address" /></div>
        <div class="field"><label>MAC</label><input class="input" v-model="editForm.mac_address" /></div>
        <div class="field"><label>OS</label><input class="input" v-model="editForm.os_name" /></div>
      </div>
      <div class="field"><label>Catatan</label><textarea class="textarea" rows="2" v-model="editForm.notes"></textarea></div>
      <div class="row" style="justify-content:flex-end;margin-top:10px;">
        <button class="btn" @click="editModal = false">Batal</button>
        <button class="btn btn-primary" :disabled="saving" @click="saveEdit">{{ saving ? 'Menyimpan…' : 'Simpan' }}</button>
      </div>
    </Modal>

    <!-- modal catatan -->
    <Modal v-if="noteModal" title="📝 Catatan Baru" @close="noteModal = false">
      <div class="field">
        <label>Jenis</label>
        <select class="select" v-model="noteForm.kind">
          <option value="note">Catatan umum</option>
          <option value="repair">Perbaikan</option>
          <option value="service">Servis vendor</option>
          <option value="assign">Penugasan</option>
          <option value="transfer">Mutasi lokasi</option>
        </select>
      </div>
      <div class="field">
        <label>Catatan <span class="req">*</span></label>
        <textarea class="textarea" rows="3" v-model="noteForm.note" placeholder="cth: Ganti SSD 512 GB, vendor XYZ, biaya Rp 850.000"></textarea>
      </div>
      <div class="row" style="justify-content:flex-end;">
        <button class="btn" @click="noteModal = false">Batal</button>
        <button class="btn btn-primary" :disabled="saving" @click="saveNote">Simpan</button>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
.detail-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 14px; }
.kv { display: grid; grid-template-columns: 120px 1fr; gap: 6px 10px; margin: 0; font-size: 13px; }
.kv dt { color: var(--text-3); font-size: 11.5px; font-weight: 600; }
.kv dd { margin: 0; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.strong { font-weight: 700; }
.tiny { font-size: 11px; }
.cond-buttons { display: grid; grid-template-columns: 1fr; gap: 8px; }
.cond-btn {
  display: flex; align-items: center; gap: 10px; padding: 12px 14px;
  border: 2px solid var(--border); border-radius: 12px; background: var(--surface);
  font: inherit; font-weight: 700; font-size: 14px; cursor: pointer; text-align: left;
  transition: border-color .15s, background .15s;
}
.cond-btn:hover { border-color: var(--c); background: color-mix(in srgb, var(--c) 7%, var(--surface)); }
.cond-btn.on { border-color: var(--c); background: color-mix(in srgb, var(--c) 12%, var(--surface)); color: var(--c); }
.cond-icon { font-size: 20px; }
.photo-preview { max-width: 100%; max-height: 180px; margin-top: 6px; border-radius: 8px; border: 1px solid var(--border); }
.timeline { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.timeline li { display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; font-size: 12.5px; padding-bottom: 8px; border-bottom: 1px dashed var(--border); }
.timeline li:last-child { border-bottom: none; }
.timeline .when { margin-left: auto; color: var(--text-3); font-size: 11px; }
</style>
