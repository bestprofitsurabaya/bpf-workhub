<script setup>
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useDriverStore } from '../../stores/driverStore'
import { api } from '../../api'
import { saveTripDraft, loadTripDraft, deleteTripDraft } from '../../utils/idb'

const store = useDriverStore()
const emit = defineEmits(['toast'])

const tripDate = ref(new Date().toISOString().slice(0, 10))
const nopol = ref('')
const kmAwal = ref(0)
const kmAkhir = ref(0)
const jamBerangkat = ref('')
const jamTiba = ref('')

const rows = ref([])
const appointments = ref([])
const apptLoading = ref(false)
const saving = ref(false)

// Modal hasil kunjungan (🏁 Selesai Dikunjungi)
const visitAppt = ref(null)
const visitForm = ref({ result: '', note: '' })
const savingVisit = ref(false)

const VISIT_LABELS = { ditemui: '😊 Ditemui', prospek: '🤝 Prospek', gagal: '❌ Gagal' }

watch(() => store.profile, (p) => { if (p) nopol.value = p.nopol || '' }, { immediate: true })

function addRow(data = {}) {
  rows.value.push({
    berangkat: data.berangkat || '', pukulB: data.pukulB || '', kmB: data.kmB || 0,
    tujuan: data.tujuan || '', pukulT: data.pukulT || '', kmT: data.kmT || 0,
    apptId: data.apptId || null,
  })
}

// === Auto-save ke IndexedDB ===
let saveTimer = null
function scheduleAutoSave() {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => doAutoSave(), 1000)
}

async function doAutoSave() {
  if (!store.driverName || !tripDate.value) return
  const draft = {
    nopol: nopol.value,
    kmAwal: kmAwal.value,
    kmAkhir: kmAkhir.value,
    jamBerangkat: jamBerangkat.value,
    jamTiba: jamTiba.value,
    rows: JSON.parse(JSON.stringify(rows.value)),
  }
  await saveTripDraft(store.driverName, tripDate.value, draft)
}

async function loadDraft() {
  if (!store.driverName || !tripDate.value) return
  const draft = await loadTripDraft(store.driverName, tripDate.value)
  if (!draft) return false
  nopol.value = draft.nopol || nopol.value
  kmAwal.value = draft.kmAwal || 0
  kmAkhir.value = draft.kmAkhir || 0
  jamBerangkat.value = draft.jamBerangkat || ''
  jamTiba.value = draft.jamTiba || ''
  rows.value = (draft.rows && draft.rows.length) ? draft.rows : []
  if (!rows.value.length) addRow()
  return true
}

// Watch semua field untuk auto-save
watch([nopol, kmAwal, kmAkhir, jamBerangkat, jamTiba, rows], scheduleAutoSave, { deep: true })

async function loadAppointments() {
  if (!store.driverName || !tripDate.value) { appointments.value = []; return }
  apptLoading.value = true
  try {
    const list = await api('/api/appointments/driver-today', {
      params: { driver: store.driverName, date: tripDate.value },
    })
    appointments.value = Array.isArray(list) ? list : []
  } catch { appointments.value = [] }
  finally { apptLoading.value = false }
}

watch([() => store.driverName, tripDate], async () => {
  await loadAppointments()
  // Load draft setelah appointments (agar tidak ke-overwrite)
  const hasDraft = await loadDraft()
  if (hasDraft) emit('toast', '📥 Draft lokal dimuat', 'info')
})

function gpsForRow(row, which) {
  const addr = store.gps.addr || (store.gps.lat && store.gps.lon ? `${store.gps.lat.toFixed(5)}, ${store.gps.lon.toFixed(5)}` : '')
  if (!addr) { emit('toast', '⚠️ GPS belum terdeteksi. Tekan 📍 Isi Lokasi dulu.', 'error'); return }
  const now = new Date()
  const timeStr = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`
  if (which === 'berangkat') { row.berangkat = addr; row.pukulB = timeStr }
  else { row.tujuan = addr; row.pukulT = timeStr }
}

function fillFromAppointments() {
  if (!appointments.value.length) { emit('toast', 'Tidak ada appointment ditugaskan hari ini', 'error'); return }
  rows.value = []
  let prevTujuan = ''
  let prevPukul = ''
  for (const a of appointments.value) {
    const waktu = a.sesi === '1' ? '08:30' : '14:30'
    rows.value.push({
      berangkat: prevTujuan, pukulB: prevPukul || waktu, kmB: 0,
      tujuan: a.alamat || '', pukulT: waktu, kmT: 0, apptId: a.id,
    })
    prevTujuan = a.alamat || ''
    prevPukul = waktu
  }
  emit('toast', `📥 ${appointments.value.length} rute appointment dimuat. Lengkapi KM & pukul bila perlu.`, 'success')
}

function openVisit(a) {
  visitAppt.value = a
  visitForm.value = { result: '', note: '' }
}

async function submitVisit() {
  if (!visitForm.value.result) { emit('toast', '⚠️ Pilih hasil kunjungan terlebih dahulu', 'error'); return }
  savingVisit.value = true
  try {
    const fd = new FormData()
    fd.append('driver', store.driverName)
    fd.append('result', visitForm.value.result)
    fd.append('note', visitForm.value.note)
    const csrf = localStorage.getItem('bpf_csrf') || sessionStorage.getItem('bpf_csrf')
    const r = await fetch(`/api/appointments/driver-complete/${visitAppt.value.id}`, {
      method: 'POST', body: fd,
      headers: { ...(csrf ? { 'X-CSRF-Token': csrf } : {}) },
    })
    const j = await r.json().catch(() => null)
    if (r.ok && j?.status === 'success') {
      emit('toast', `✅ ${j.msg || 'Selesai dikunjungi'}`, 'success')
      visitAppt.value = null
      loadAppointments()
    } else {
      emit('toast', '❌ ' + (j?.msg || 'Gagal'), 'error')
    }
  } catch { emit('toast', '❌ Error koneksi', 'error') }
  finally { savingVisit.value = false }
}

async function submit() {
  const validRows = rows.value.filter((r) => r.berangkat && r.tujuan)
  if (!nopol.value || !jamBerangkat.value || !(kmAwal.value > 0)) {
    emit('toast', '⚠️ Nopol, Jam Berangkat, dan KM Awal wajib diisi', 'error'); return
  }
  if (!validRows.length) { emit('toast', '⚠️ Minimal 1 rute (lokasi berangkat & tujuan)', 'error'); return }

  // Simpan sebagai ARRAY per key agar rute ganda tidak saling menimpa
  // (object biasa tidak bisa menampung key duplikat — bug multi-rute).
  const payload = {
    driver_name: store.driverName,
    nopol: nopol.value,
    trip_date: tripDate.value,
    jam_keberangkatan: jamBerangkat.value,
    jam_tiba: jamTiba.value,
    km_awal: Number(kmAwal.value) || 0,
    km_akhir: Number(kmAkhir.value) || 0,
    'lokasi_berangkat[]': validRows.map((r) => r.berangkat),
    'pukul_berangkat[]': validRows.map((r) => r.pukulB),
    'km_berangkat[]': validRows.map((r) => r.kmB || 0),
    'lokasi_tujuan[]': validRows.map((r) => r.tujuan),
    'pukul_tujuan[]': validRows.map((r) => r.pukulT),
    'km_tujuan[]': validRows.map((r) => r.kmT || 0),
    'appointment_id[]': validRows.map((r) => r.apptId || ''),
  }

  if (store.online) {
    saving.value = true
    try {
      const fd = new FormData()
      for (const [k, v] of Object.entries(payload)) {
        if (Array.isArray(v)) { for (const item of v) fd.append(k, String(item)) }
        else fd.append(k, String(v))
      }
      const csrf = localStorage.getItem('bpf_csrf') || sessionStorage.getItem('bpf_csrf')
      const r = await fetch('/submit-trip', {
        method: 'POST', body: fd,
        headers: { ...(csrf ? { 'X-CSRF-Token': csrf } : {}), 'X-Requested-With': 'XMLHttpRequest', Accept: 'application/json' },
      })
      const j = await r.json().catch(() => null)
      if (r.ok && j?.status === 'success') {
        emit('toast', `✅ Log perjalanan terkirim (${j.routes || validRows.length} rute)`, 'success')
        await deleteTripDraft(store.driverName, tripDate.value)
        rows.value = []; kmAwal.value = 0; kmAkhir.value = 0; jamBerangkat.value = ''; jamTiba.value = ''
        loadAppointments()
      } else {
        emit('toast', '❌ ' + (j?.msg || 'Gagal mengirim'), 'error')
      }
    } catch { emit('toast', '❌ Error koneksi', 'error') }
    finally { saving.value = false }
  } else {
    await store.enqueue('trip_queue', payload)
    await deleteTripDraft(store.driverName, tripDate.value)
    rows.value = []; kmAwal.value = 0; kmAkhir.value = 0; jamBerangkat.value = ''; jamTiba.value = ''
    emit('toast', '🟡 Offline — data disimpan lokal, akan dikirim otomatis', 'warning')
  }
}

function visitBadge(a) { return a.visit_result ? (VISIT_LABELS[a.visit_result] || a.visit_result) : '' }

onMounted(async () => {
  addRow()
  // Load draft jika ada
  const hasDraft = await loadDraft()
  if (hasDraft) emit('toast', '📥 Draft lokal dimuat', 'info')
})

onUnmounted(() => { if (saveTimer) clearTimeout(saveTimer) })
</script>

<template>
  <!-- Satu root element (bukan fragment) — wajib agar v-show tab di DriverView
       bisa menyembunyikan tab ini saat bukan tab aktif. Sebelumnya fragment
       (2 root) membuat v-show tidak bekerja: konten Trip selalu tampil di tab lain. -->
  <div class="tab-page">
    <!-- GPS Box -->
    <div class="gps-box" :class="{ ok: store.gps.addr }">
      <div class="gps-title">
        <template v-if="store.gps.locating">🔍 Mencari lokasi…</template>
        <template v-else-if="store.gps.addr">📍 Lokasi Terdeteksi</template>
        <template v-else>⚠ GPS Belum Aktif</template>
      </div>
      <div class="gps-addr">{{ store.gps.addr || 'Tekan tombol di bawah untuk deteksi lokasi.' }}</div>
      <div v-if="store.gps.detail && store.gps.addr" class="gps-detail">
        <div v-if="store.gps.detail.kelurahan" class="gps-detail-row"><span class="gps-label">Kelurahan</span><span>{{ store.gps.detail.kelurahan }}</span></div>
        <div v-if="store.gps.detail.kecamatan" class="gps-detail-row"><span class="gps-label">Kecamatan</span><span>{{ store.gps.detail.kecamatan }}</span></div>
        <div v-if="store.gps.detail.kota" class="gps-detail-row"><span class="gps-label">Kota/Kab</span><span>{{ store.gps.detail.kota }}</span></div>
        <div v-if="store.gps.detail.provinsi" class="gps-detail-row"><span class="gps-label">Provinsi</span><span>{{ store.gps.detail.provinsi }}</span></div>
        <div v-if="store.gps.detail.kode_pos" class="gps-detail-row"><span class="gps-label">Kode Pos</span><span>{{ store.gps.detail.kode_pos }}</span></div>
        <div class="gps-detail-row" style="opacity:0.6;"><span class="gps-label">Koordinat</span><span>{{ store.gps.lat?.toFixed(6) }}, {{ store.gps.lon?.toFixed(6) }}</span></div>
      </div>
      <div v-if="store.gps.spbu" class="gps-spbu">⛽ {{ store.gps.spbu }}</div>
      <button class="btn btn-sm" :disabled="store.gps.locating" style="margin-top:6px;" @click="store.locate()">📍 Isi Lokasi & Jam</button>
    </div>

    <div class="row" style="gap:8px;">
      <div class="field"><label>Tanggal</label><input class="input" type="date" v-model="tripDate" /></div>
      <div class="field"><label>Nopol</label><input class="input" v-model="nopol" /></div>
    </div>

    <!-- Jadwal Appointment Saya -->
    <div v-if="appointments.length" class="appt-panel">
      <div class="row" style="margin-bottom:8px;">
        <h4 style="margin:0;">📅 Jadwal Appointment Saya ({{ appointments.length }})</h4>
        <div class="spacer"></div>
        <button class="btn btn-sm btn-primary" @click="fillFromAppointments">📥 Muat Semua ke Rute</button>
      </div>
      <div v-if="apptLoading" class="muted skeleton" style="font-size:12px;">⏳ Memuat…</div>
      <div v-for="a in appointments" :key="a.id" class="appt-item">
        <span class="appt-time">{{ a.sesi === '2' ? '🌆 14.30' : '🌅 08.30' }}</span>
        <div class="appt-body">
          <strong>{{ a.nasabah_name }}</strong>
          <span class="badge" :class="a.status === 'completed' ? 'badge-green' : 'badge-blue'">
            {{ a.status === 'completed' ? '✅ Selesai' : '🚗 Ditugaskan' }}
          </span>
          <span v-if="visitBadge(a)" class="badge badge-green">{{ visitBadge(a) }}</span>
          <div>📍 {{ a.alamat }}</div>
          <div class="muted" style="font-size:11px;">{{ a.display_id }}<span v-if="a.area"> · {{ a.area }}</span><span v-if="a.marketing_member"> · 👤 {{ a.marketing_member }}</span></div>
          <div class="row" style="gap:6px;margin-top:6px;">
            <a v-if="a.nasabah_phone" class="btn btn-sm" :href="'tel:' + a.nasabah_phone">📞</a>
            <a class="btn btn-sm" target="_blank" rel="noopener" :href="'https://www.google.com/maps/search/?api=1&query=' + encodeURIComponent(a.alamat || '')">🌍</a>
            <button v-if="a.status === 'assigned'" class="btn btn-sm btn-primary" @click="openVisit(a)">🏁 Selesai Dikunjungi</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Form Trip -->
    <div class="row">
      <div class="field"><label>Jam Berangkat <span class="req">*</span></label><input class="input" type="time" v-model="jamBerangkat" /></div>
      <div class="field"><label>Jam Tiba</label><input class="input" type="time" v-model="jamTiba" /></div>
    </div>
    <div class="row">
      <div class="field"><label>KM Awal <span class="req">*</span></label><input class="input" type="number" v-model.number="kmAwal" min="0" placeholder="0" /></div>
      <div class="field"><label>KM Akhir</label><input class="input" type="number" v-model.number="kmAkhir" min="0" placeholder="0" /></div>
    </div>

    <h4 style="margin:10px 0 6px;">🗺️ Rute Perjalanan</h4>
    <div v-for="(row, i) in rows" :key="i" class="trip-row">
      <button type="button" class="btn-icon" style="align-self:flex-start;" title="Hapus baris" @click="rows.splice(i, 1)">✕</button>
      <div class="trip-grid">
        <div class="field"><label>Lokasi Berangkat</label>
          <input class="input" v-model="row.berangkat" placeholder="Nama tempat…" />
          <button type="button" class="btn btn-sm" style="margin-top:4px;" @click="gpsForRow(row, 'berangkat')">📍 GPS + Jam</button>
        </div>
        <div class="field"><label>Pukul</label><input class="input" type="time" v-model="row.pukulB" /></div>
        <div class="field"><label>KM</label><input class="input" type="number" v-model.number="row.kmB" min="0" /></div>
        <div class="field"><label>Lokasi Tujuan</label>
          <input class="input" v-model="row.tujuan" placeholder="Nama tempat…" />
          <button type="button" class="btn btn-sm" style="margin-top:4px;" @click="gpsForRow(row, 'tujuan')">📍 GPS + Jam</button>
        </div>
        <div class="field"><label>Pukul</label><input class="input" type="time" v-model="row.pukulT" /></div>
        <div class="field"><label>KM</label><input class="input" type="number" v-model.number="row.kmT" min="0" /></div>
      </div>
    </div>
    <button class="btn" style="width:100%;margin-top:8px;" @click="addRow()">➕ Tambah Rute</button>

    <button class="btn btn-primary" style="width:100%;justify-content:center;padding:12px;margin-top:10px;" :disabled="saving">
      {{ saving ? '⏳ Mengirim…' : '📤 Kirim Log Perjalanan' }}
    </button>

    <!-- Modal Hasil Kunjungan -->
    <div v-if="visitAppt" class="modal-overlay" role="dialog" aria-modal="true" :aria-label="'Hasil kunjungan ' + visitAppt.display_id" @click.self="visitAppt = null" @keydown.esc="visitAppt = null">
      <div class="modal-box" tabindex="-1">
        <div class="row" style="justify-content:space-between;margin-bottom:10px;">
          <h3 style="margin:0;">🏁 {{ visitAppt.display_id }}</h3>
          <button class="btn-icon" aria-label="Tutup" title="Tutup (Esc)" @click="visitAppt = null">✕</button>
        </div>
        <p class="muted" style="font-size:12px;margin-bottom:10px;">{{ visitAppt.nasabah_name }} · {{ visitAppt.alamat }}</p>
        <div class="field"><label>Hasil kunjungan <span class="req">*</span></label>
          <select class="select" v-model="visitForm.result">
            <option value="">— Pilih hasil —</option>
            <option value="ditemui">😊 Ditemui</option>
            <option value="prospek">🤝 Prospek</option>
            <option value="gagal">❌ Gagal</option>
          </select>
        </div>
        <div class="field" style="margin-top:8px;"><label>Alasan / catatan (opsional)</label>
          <textarea class="textarea" v-model="visitForm.note" rows="2" placeholder="Catatan…"></textarea>
        </div>
        <div class="row" style="justify-content:flex-end;gap:6px;margin-top:10px;">
          <button class="btn" @click="visitAppt = null">Batal</button>
          <button class="btn btn-primary" :disabled="savingVisit" @click="submitVisit">✅ Kirim Hasil</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.gps-box { border: 1px dashed var(--border); border-radius: 10px; padding: 10px 12px; margin-bottom: 12px; background: var(--bg-2, #fef3c7); }
.gps-box.ok { background: var(--bg-3, #f0fdf4); border-color: #059669; }
.gps-title { font-size: 13px; font-weight: 700; }
.gps-addr { font-size: 11px; opacity: .8; margin-top: 2px; }
.gps-spbu { font-size: 11px; margin-top: 2px; }
.gps-detail { margin-top: 8px; padding-top: 8px; border-top: 1px solid rgba(0,0,0,0.08); display: grid; grid-template-columns: auto 1fr; gap: 2px 10px; font-size: 11px; }
.gps-detail-row { display: contents; }
.gps-label { font-weight: 600; opacity: 0.7; }
.appt-panel { border: 1px solid var(--border); border-radius: 12px; padding: 10px; margin: 10px 0; background: var(--bg-2, #f8fafc); }
.appt-item { display: flex; gap: 10px; padding: 8px 0; border-bottom: 1px dashed var(--border); }
.appt-item:last-child { border-bottom: none; }
.appt-time { font-size: 11px; font-weight: 700; opacity: .7; min-width: 60px; }
.appt-body { font-size: 12px; flex: 1; }
.trip-row { border: 1px solid var(--border); border-radius: 10px; padding: 8px; margin-bottom: 8px; display: flex; gap: 8px; }
.trip-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 6px; flex: 1; min-width: 0; }
.trip-grid .field { margin: 0; min-width: 0; }
.trip-grid label { font-size: 10px; }
.trip-grid .input { font-size: 12px; padding: 6px 8px; }
@media (max-width: 480px) {
  .trip-row { flex-direction: column; }
  .trip-grid { grid-template-columns: 1fr 1fr; }
  .trip-grid .field:nth-child(1),
  .trip-grid .field:nth-child(4) { grid-column: 1 / -1; }
}
.tab-page { padding-bottom: 0; }
</style>
