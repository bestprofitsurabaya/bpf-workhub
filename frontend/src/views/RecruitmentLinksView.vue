<script setup>
import { onMounted, reactive, ref } from 'vue'
import QRCode from 'qrcode'
import { api } from '../api'
import PageHeader from '../components/PageHeader.vue'
import Modal from '../components/Modal.vue'

// Dipakai sebagai tab di hub rekrutmen: PageHeader induk tidak dirender di sini.
defineProps({ embedded: { type: Boolean, default: false } })

const loading = ref(true)
const err = ref('')
const msg = ref('')
const links = ref([])
const scopeBranch = ref('')

// Satu tautan portal per cabang; token hanya ada di dalam URL portal dan
// tidak pernah disimpan/ditampilkan sebagai field tersendiri.
function portalUrl(entry) {
  return entry?.portal_path ? window.location.origin + entry.portal_path : ''
}
function hasToken(entry) {
  return Boolean(entry?.active && portalUrl(entry))
}

async function loadLinks() {
  loading.value = true
  err.value = ''
  try {
    const data = await api('/api/recruitment/portal-links')
    links.value = Array.isArray(data?.data) ? data.data : []
    scopeBranch.value = data?.scope_branch || ''
  } catch (e) {
    links.value = []
    err.value = 'Gagal memuat tautan portal: ' + (e?.message || e)
  } finally {
    loading.value = false
  }
}

async function copyLink(entry) {
  const url = portalUrl(entry)
  if (!hasToken(entry)) {
    err.value = 'Belum ada token; hubungi Admin.'
    return
  }
  err.value = ''
  msg.value = ''
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(url)
      msg.value = 'Tautan portal disalin.'
      return
    }
  } catch {
    // Clipboard API bisa gagal (non-HTTPS / izin ditolak) → coba fallback.
  }
  let copied = false
  let area = null
  try {
    area = document.createElement('textarea')
    area.value = url
    area.setAttribute('readonly', '')
    area.style.position = 'fixed'
    area.style.top = '-1000px'
    area.style.opacity = '0'
    document.body.appendChild(area)
    area.select()
    copied = Boolean(document.execCommand?.('copy'))
  } catch {
    copied = false
  } finally {
    area?.remove?.()
  }
  msg.value = copied ? 'Tautan portal disalin.' : `Salin manual tautan ini: ${url}`
}

// QR dibuat lokal di browser. URL mengandung token rahasia, jadi jangan
// dikirim ke layanan pembuat QR pihak ketiga.
const qrModal = reactive({ show: false, code: '', label: '', url: '', dataUrl: '' })

async function showQr(entry) {
  const url = portalUrl(entry)
  if (!hasToken(entry)) {
    err.value = 'Belum ada token; hubungi Admin.'
    return
  }
  Object.assign(qrModal, {
    show: true,
    code: entry.branch_code || '',
    label: entry.branch_name || entry.branch_code || '',
    url,
    dataUrl: '',
  })
  try {
    qrModal.dataUrl = await QRCode.toDataURL(url, { width: 420, margin: 2 })
  } catch (e) {
    err.value = 'Gagal membuat QR: ' + (e?.message || e)
    qrModal.show = false
  }
}

function escapeHtml(value) {
  return String(value || '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]))
}

function printQr() {
  if (!qrModal.dataUrl || !qrModal.url) {
    err.value = 'QR belum siap untuk dicetak.'
    return
  }
  const win = window.open('', '_blank', 'width=520,height=680')
  if (!win) {
    err.value = 'Popup diblokir browser. Izinkan popup untuk mencetak QR.'
    return
  }
  const title = `QR Portal Rekrutmen ${qrModal.code}`
  try {
    win.document.write(
      '<!doctype html><html><head><title>' + escapeHtml(title) + '</title></head>' +
      '<body style="text-align:center;font-family:sans-serif;margin:24px">' +
      '<h3 style="margin:0 0 4px">' + escapeHtml(title) + '</h3>' +
      '<p style="margin:0 0 4px">' + escapeHtml(qrModal.label) + '</p>' +
      '<p style="margin:0 0 12px;font-size:12px">Scan untuk membuka portal rekrutmen</p>' +
      '<img src="' + escapeHtml(qrModal.dataUrl) + '" style="width:360px" ' +
      'onload="window.focus();window.print()" />' +
      '<p style="font-size:10px;color:#555;word-break:break-all">' +
      escapeHtml(qrModal.url) + '</p></body></html>')
    win.document.close()
    win.focus?.()
  } catch {
    err.value = 'Gagal membuka jendela cetak QR.'
  }
}

onMounted(loadLinks)
</script>

<template>
  <div class="links-view">
    <PageHeader v-if="!embedded" icon="🔗" title="Tautan Portal Rekrutmen"
                subtitle="Satu tautan per cabang untuk CV, FirstWork, dan TKD." />

    <div v-if="err" class="alert alert-error">{{ err }}</div>
    <div v-if="msg" class="alert alert-success">{{ msg }}</div>

    <div class="card card-pad">
      <p class="fw-hint">Bagikan satu tautan ini; pelamar memilih CV, FirstWork, atau TKD dari portal.</p>
      <div v-if="scopeBranch" class="fw-sub">Cakupan cabang: <b>{{ scopeBranch }}</b></div>

      <div v-if="loading" class="fw-empty">⏳ Memuat tautan portal…</div>
      <div v-else-if="err && !links.length" class="fw-empty">
        Tautan tidak tersedia.
        <button class="btn btn-sm" type="button" @click="loadLinks">↻ Coba lagi</button>
      </div>
      <div v-else-if="!links.length" class="fw-empty">
        Belum ada cabang untuk ditampilkan.
        <button class="btn btn-sm" type="button" @click="loadLinks">↻ Muat ulang</button>
      </div>
      <div v-else class="links-grid">
        <div v-for="link in links" :key="link.branch_code || link.branch_name"
             class="card card-pad link-card" data-portal-link>
          <div class="link-head">
            <h3 class="link-title">{{ link.branch_name || link.branch_code }}</h3>
            <span class="fw-badge" :class="hasToken(link) ? 'badge-ok' : 'badge-warn'">
              {{ hasToken(link) ? 'Aktif' : 'Nonaktif' }}
            </span>
          </div>
          <div class="fw-sub">Kode cabang: <b>{{ link.branch_code }}</b></div>

          <template v-if="hasToken(link)">
            <a class="link-url" :href="portalUrl(link)" target="_blank" rel="noopener noreferrer">
              {{ portalUrl(link) }}
            </a>
            <div class="link-actions">
              <button class="btn btn-sm" type="button" :data-copy="link.branch_code"
                      @click="copyLink(link)">🔗 Salin tautan</button>
              <button class="btn btn-sm" type="button" :data-qr="link.branch_code"
                      @click="showQr(link)">▦ QR</button>
            </div>
          </template>
          <div v-else class="alert alert-error">Belum ada token; hubungi Admin.</div>
        </div>
      </div>
    </div>

    <Modal v-if="qrModal.show" :title="`QR Portal Rekrutmen ${qrModal.code}`"
           @close="qrModal.show = false">
      <div class="qr-body">
        <img v-if="qrModal.dataUrl" class="qr-image" :src="qrModal.dataUrl"
             alt="QR portal rekrutmen" />
        <div v-else class="fw-empty">⏳ Membuat QR…</div>
        <div class="fw-sub qr-url">{{ qrModal.url }}</div>
        <div class="link-actions">
          <button class="btn btn-sm btn-primary" type="button" :disabled="!qrModal.dataUrl"
                  @click="printQr">🖨️ Cetak QR</button>
          <button class="btn btn-sm" type="button" @click="qrModal.show = false">Tutup</button>
        </div>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
/* Kelas fw-* di sini didefinisikan ulang karena style scoped view lain tidak menembus. */
.fw-sub { font-size: 11px; color: var(--text-3); margin-top: 2px; }
.fw-hint { font-size: 12px; color: var(--text-3); margin: 0 0 4px; }
.fw-empty { padding: 26px; text-align: center; color: var(--text-3); font-size: 12px; }
.fw-badge {
  display: inline-block; padding: 2px 7px; border-radius: 20px;
  font-size: 10px; font-weight: 700; white-space: nowrap;
}
.fw-badge.badge-ok { background: #d1fae5; color: #065f46; }
.fw-badge.badge-warn { background: #fef3c7; color: #92400e; }
.links-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px; margin-top: 12px;
}
.link-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.link-title { margin: 0; font-size: 15px; font-weight: 700; }
.link-url {
  display: block; margin: 10px 0; font-size: 12px; word-break: break-all;
  color: var(--primary);
}
.link-actions { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.qr-body { text-align: center; }
.qr-image { width: 320px; max-width: 100%; }
.qr-url { margin: 10px 0; word-break: break-all; }
</style>
