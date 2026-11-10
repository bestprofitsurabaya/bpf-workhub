<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import PageHeader from '../components/PageHeader.vue'
import { formatDateTime } from '../utils/format'
import {
  STATUS_LABEL, STATUS_BADGE, COND_META, assetTitle, categoryLabel,
} from '../utils/itAssets'

const route = useRoute()
const router = useRouter()

const manualTag = ref('')
const asset = ref(null)
const loading = ref(false)
const busy = ref(false)
const msg = ref('')
const msgType = ref('success')
const note = ref('')
const sessionId = ref(route.query.session ? Number(route.query.session) : null)

const cameraOn = ref(false)
const cameraSupported = ref(false)
const cameraError = ref('')
const videoRef = ref(null)
let stream = null
let detector = null
let rafId = null
let lastCode = ''
let lastCodeAt = 0

function flash(text, type = 'success') {
  msg.value = text
  msgType.value = type
  window.clearTimeout(flash._t)
  flash._t = window.setTimeout(() => { msg.value = '' }, 6000)
}

// --------------------------------------------------------------- pencarian tag
function normalizeCode(raw) {
  const s = String(raw || '').trim().toUpperCase()
  // QR berisi URL → ambil segmen terakhir setelah '/it/assets/'
  const m = s.match(/\/IT\/ASSETS\/([^/?#]+)/) || s.match(/BPFIT:([^\s]+)/)
  return m ? decodeURIComponent(m[1]).toUpperCase() : s
}

async function lookup(raw) {
  const tag = normalizeCode(raw)
  if (!tag) return
  loading.value = true
  asset.value = null
  try {
    const res = await api('/api/it/assets/lookup', { params: { tag } })
    asset.value = res.data
    manualTag.value = tag
    if (sessionId.value) await markStocktake(tag)
  } catch (e) {
    flash('❌ ' + e.message, 'error')
  } finally {
    loading.value = false
  }
}

async function markStocktake(tag) {
  try {
    const res = await api(`/api/it/stocktake/${sessionId.value}/scan`, { method: 'POST', body: { tag } })
    flash(`✅ ${res.msg}`)
  } catch (e) {
    flash('❌ Stok opname: ' + e.message, 'error')
  }
}

// ------------------------------------------------------------------- kamera
async function startCamera() {
  cameraError.value = ''
  if (!('BarcodeDetector' in window)) {
    cameraSupported.value = false
    cameraError.value = 'Browser ini belum mendukung pemindai QR bawaan. Gunakan input tag manual di bawah, atau buka dengan Chrome Android.'
    return
  }
  cameraSupported.value = true
  try {
    detector = new window.BarcodeDetector({ formats: ['qr_code'] })
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'environment' }, audio: false,
    })
    if (videoRef.value) {
      videoRef.value.srcObject = stream
      await videoRef.value.play()
    }
    cameraOn.value = true
    scanLoop()
  } catch (e) {
    cameraError.value = 'Tidak bisa membuka kamera: ' + (e.message || e.name)
    await stopCamera()
  }
}

async function scanLoop() {
  if (!cameraOn.value || !detector || !videoRef.value) return
  try {
    const codes = await detector.detect(videoRef.value)
    const value = codes?.[0]?.rawValue
    if (value) {
      const now = Date.now()
      if (value !== lastCode || now - lastCodeAt > 4000) {
        lastCode = value
        lastCodeAt = now
        if (navigator.vibrate) navigator.vibrate(60)
        await stopCamera()
        await lookup(value)
        return
      }
    }
  } catch { /* frame belum siap — lanjut */ }
  rafId = window.setTimeout(scanLoop, 350)
}

async function stopCamera() {
  cameraOn.value = false
  if (rafId) { window.clearTimeout(rafId); rafId = null }
  if (stream) {
    stream.getTracks().forEach((t) => t.stop())
    stream = null
  }
  if (videoRef.value) videoRef.value.srcObject = null
}

// -------------------------------------------------------------- ubah kondisi
async function setCondition(cond) {
  if (!asset.value) return
  busy.value = true
  try {
    const body = { cond, note: note.value }
    if (cond === 'rusak_berat' && asset.value.status === 'aktif') body.status = 'service'
    const res = await api(`/api/it/assets/${encodeURIComponent(asset.value.asset_tag)}/condition`, {
      method: 'POST', body,
    })
    asset.value = res.data
    note.value = ''
    flash(`✅ ${res.msg}`)
  } catch (e) {
    flash('❌ ' + e.message, 'error')
  } finally {
    busy.value = false
  }
}

const condKeys = computed(() => Object.keys(COND_META))

onMounted(() => {
  cameraSupported.value = 'BarcodeDetector' in window
  if (route.query.tag) lookup(route.query.tag)
})
onBeforeUnmount(stopCamera)
</script>

<template>
  <div class="it-scan">
    <PageHeader icon="📷" title="Scan Aset" subtitle="Scan QR pada label lalu ubah kondisi dalam tiga ketukan.">
      <button class="btn" @click="router.push('/it/inventory')">← Inventaris</button>
    </PageHeader>

    <div v-if="sessionId" class="alert alert-info">
      Mode stok opname sesi #{{ sessionId }} — aset yang discan otomatis ditandai ditemukan.
    </div>

    <div v-if="msg" class="alert" :class="msgType === 'error' ? 'alert-error' : 'alert-success'">{{ msg }}</div>

    <div class="scan-grid">
      <!-- kamera -->
      <div class="card card-pad">
        <h3>Kamera QR</h3>
        <div class="cam-box">
          <video v-show="cameraOn" ref="videoRef" playsinline muted aria-label="Pratinjau kamera untuk memindai QR"></video>
          <div v-if="!cameraOn" class="cam-placeholder">
            <span class="cam-icon">📷</span>
            <p class="muted">Arahkan kamera ke QR pada label aset.</p>
          </div>
        </div>
        <div class="row" style="margin-top:10px;">
          <button v-if="!cameraOn" class="btn btn-primary btn-lg" @click="startCamera">▶ Buka Kamera</button>
          <button v-else class="btn btn-danger btn-lg" @click="stopCamera">⏹ Hentikan</button>
        </div>
        <p v-if="cameraError" class="muted tiny" style="margin-top:8px;">{{ cameraError }}</p>
      </div>

      <!-- input manual -->
      <div class="card card-pad">
        <h3>Input Tag Manual</h3>
        <p class="muted tiny">Dipakai bila kamera tidak tersedia atau label rusak.</p>
        <div class="field">
          <label>Tag aset</label>
          <input class="input input-lg" v-model="manualTag" placeholder="SBY-IT-PC-0001"
                 autocapitalize="characters" autocomplete="off" @keyup.enter="lookup(manualTag)" />
        </div>
        <button class="btn btn-primary btn-lg" :disabled="loading" @click="lookup(manualTag)">
          {{ loading ? 'Mencari…' : '🔍 Cari Aset' }}
        </button>
      </div>
    </div>

    <!-- hasil -->
    <div v-if="asset" class="card card-pad" style="margin-top:16px;">
      <div class="row" style="justify-content:space-between;align-items:flex-start;">
        <div>
          <div class="mono strong big">{{ asset.asset_tag }}</div>
          <div>{{ assetTitle(asset) }} · {{ categoryLabel(asset.category) }}</div>
          <div class="muted tiny">
            {{ [asset.location_room, asset.location_detail].filter(Boolean).join(' · ') || 'Lokasi belum diisi' }}
            <span v-if="asset.assigned_to"> · PIC {{ asset.assigned_to }}</span>
          </div>
        </div>
        <div class="row">
          <span class="badge" :class="STATUS_BADGE[asset.status] || 'badge-gray'">{{ STATUS_LABEL[asset.status] || asset.status }}</span>
          <span class="badge" :class="COND_META[asset.cond]?.badge || 'badge-gray'">{{ COND_META[asset.cond]?.icon }} {{ COND_META[asset.cond]?.label }}</span>
        </div>
      </div>

      <h3 style="margin-top:16px;">Kondisi Sekarang</h3>
      <div class="cond-row">
        <button v-for="k in condKeys" :key="k" class="cond-btn" :class="{ on: asset.cond === k }"
                :style="{ '--c': COND_META[k].color }" :disabled="busy" @click="setCondition(k)">
          <span class="cond-icon">{{ COND_META[k].icon }}</span>
          <span>{{ COND_META[k].label }}</span>
        </button>
      </div>
      <div class="field" style="margin-top:10px;">
        <label>Catatan (opsional)</label>
        <input class="input" v-model="note" placeholder="cth: keyboard tidak berfungsi" />
      </div>
      <div class="row" style="justify-content:space-between;">
        <router-link class="btn" :to="`/it/assets/${asset.asset_tag}`">Lihat detail lengkap →</router-link>
        <span class="muted tiny">Terakhir diperbarui {{ formatDateTime(asset.updated_at) }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.scan-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 14px; }
.cam-box {
  position: relative; width: 100%; aspect-ratio: 4 / 3; border-radius: 14px;
  background: #0f172a; overflow: hidden; display: grid; place-items: center;
}
.cam-box video { width: 100%; height: 100%; object-fit: cover; }
.cam-placeholder { text-align: center; color: #cbd5e1; padding: 20px; }
.cam-icon { font-size: 44px; display: block; margin-bottom: 6px; }
.btn-lg { padding: 12px 18px; font-size: 15px; border-radius: 11px; }
.input-lg { padding: 12px 14px; font-size: 16px; letter-spacing: .04em; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.strong { font-weight: 700; }
.big { font-size: 20px; }
.tiny { font-size: 11px; }
.cond-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 10px; }
.cond-btn {
  display: flex; flex-direction: column; align-items: center; gap: 6px;
  padding: 16px 10px; border: 2px solid var(--border); border-radius: 14px;
  background: var(--surface); font: inherit; font-weight: 700; font-size: 13px;
  cursor: pointer; transition: border-color .15s, background .15s;
}
.cond-btn:hover { border-color: var(--c); background: color-mix(in srgb, var(--c) 7%, var(--surface)); }
.cond-btn.on { border-color: var(--c); background: color-mix(in srgb, var(--c) 12%, var(--surface)); color: var(--c); }
.cond-icon { font-size: 26px; }
</style>
