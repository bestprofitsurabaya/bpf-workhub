<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { api } from '../../api'
import StatCard from '../../components/StatCard.vue'
import PageHeader from '../../components/PageHeader.vue'
import Modal from '../../components/Modal.vue'
import ConfirmDialog from '../../components/ConfirmDialog.vue'
import ClaimVerifyCard from '../../components/ClaimVerifyCard.vue'
import { useStepupStore } from '../../stores/stepup'

const stepup = useStepupStore()
const confirmRef = ref(null)
const ask = (message, opts) => confirmRef.value?.open(message, opts) ?? Promise.resolve(false)

const from = ref('')
const to = ref('')
const loading = ref(true)
const data = ref(null)

const fmtRp = (n) => 'Rp ' + (Number(n) || 0).toLocaleString('id-ID')
const fmtNum = (n) => (Number(n) || 0).toLocaleString('id-ID')

// v2.53.0: Klaim BBM — pintasan pekerjaan utama Finance (restrukturisasi UI)
const bbm = ref({ ready: 0, confirm: 0, readyList: [], confirmList: [] })
const arrLen = (v) => (Array.isArray(v) ? v.length : 0)
async function loadBbm() {
  try {
    const [finQ, drvQ] = await Promise.all([
      api('/api/queue', { params: { tab: 'finance' } }).catch(() => null),
      api('/api/queue', { params: { tab: 'driver_confirm' } }).catch(() => null),
    ])
    bbm.value = {
      ready: arrLen(finQ), confirm: arrLen(drvQ),
      readyList: Array.isArray(finQ) ? finQ : [], confirmList: Array.isArray(drvQ) ? drvQ : [],
    }
  } catch { bbm.value = { ready: 0, confirm: 0, readyList: [], confirmList: [] } }
}

// ============================================================
// Antrean Klaim BBM + instrumen verifikasi (Detail/Subsidi Tepat)
// ============================================================
const bbmTab = ref('ready')
const bbmMsg = ref('')

const visibleBbm = computed(() => (bbmTab.value === 'ready' ? bbm.value.readyList : bbm.value.confirmList))

async function switchBbmTab(tab) {
  bbmTab.value = tab
  await loadBbm()
}

// Modal instrumen Detail — ClaimVerifyCard + jodohkan (link) / putuskan (unlink)
const detailFor = ref(null)
const cardRef = ref(null)
const cardSubsidy = ref(null)
const linkBusy = ref(false)

// ============================================================
// wave-18A: Verifikasi Finance BERTINGKAT — langkah aktif mengikuti
// rantai status klaim: verified_ga → Pencairan, os_finance → Arsip (LPJ).
// ============================================================
const cardDetail = ref(null)   // payload detail (status terbaru) dari ClaimVerifyCard
const detailMsg = ref('')      // hasil aksi server — ditampilkan di bawah modal
const stageBusy = ref(false)

// Urutan pipeline: 1 Verifikasi GA → 2 Pencairan → 3 LPJ/Arsip (+4 selesai)
const stageOn = computed(() => ({
  pending: 1, modified: 1, verified_ga: 2, os_finance: 3, archived: 4,
}[cardDetail.value?.status] || 0))

const detailStatus = computed(() => cardDetail.value?.status || detailFor.value?.status || '')

const STAGE_META = {
  verified_ga: {
    label: '2️⃣ Pencairan (Finance)',
    hint: 'Klaim sudah ACC GA — jodohkan Subsidi Tepat (riwayat SPBU resmi) dulu bila belum, lalu cairkan.',
  },
  os_finance: {
    label: '3️⃣ Arsip (LPJ driver)',
    hint: 'Dana sudah dicairkan. Catatan LPJ harusnya LENGKAP (pertanggungjawaban Subsidi Tepat) sebelum arsip.',
  },
  archived: {
    label: '4️⃣ Arsip — Selesai',
    hint: 'Selesai — dokumen tersimpan.',
  },
  pending: {
    label: '1️⃣ Verifikasi GA',
    hint: 'Klaim masih menunggu verifikasi GA — belum masuk kewenangan Finance.',
  },
}

// Tombol 📄 PDF per transaksi — hanya bila status bukan 'pending'
const showPdf = computed(() => !!detailStatus.value && detailStatus.value !== 'pending')

function openDetail(tx) {
  detailFor.value = tx
  cardSubsidy.value = null
  cardDetail.value = null
  detailMsg.value = ''
}

function onCardLoaded(payload) {
  cardSubsidy.value = payload?.subsidy || null
  cardDetail.value = payload?.detail || null
}

// wave-18A: langkah 2 — Disbursement (payout) via ask() + step-up PIN backend
async function doPayout() {
  const d = detailFor.value
  if (!d || stageBusy.value) return
  const ok = await ask(
    `Cairkan klaim ${d.display_id || d.id} (${fmtRp(d.nominal)}) untuk ${d.driver_name}? `
    + 'Klaim ber-flag anomali wajib di-clear GA dulu (sistem menolak bila belum).',
    {
      title: 'Disbursement — Pencairan klaim',
      confirmText: '💰 Cairkan',
      input: true,
      required: false,
      placeholder: 'PIN/Catatan disbursement (opsional)',
    },
  )
  if (ok === null || ok === false) return
  stageBusy.value = true; detailMsg.value = ''
  try {
    const r = await stepup.require(
      () => api(`/api/queue/payout/${d.id}`, { method: 'POST' }),
      `pencairan klaim ${d.display_id || d.id}`,
    )
    detailMsg.value = '✅ ' + (r.msg || r.message || 'Dana dicairkan — lanjut ke tahap LPJ driver')
    if (cardRef.value?.reload) await cardRef.value.reload()
    loadBbm()
  } catch (e) {
    // 409: klaim anomali belum di-clear GA (disampaikan backend) / sudah diproses
    detailMsg.value = '❌ ' + (e.status === 409 ? 'Pencairan ditahan — ' : '') + (e.message || 'Gagal mencairkan.')
  } finally { stageBusy.value = false }
}

// wave-18A: langkah 3 — Arsip (LPJ driver), konfirmasi bilingual
async function doArchive() {
  const d = detailFor.value
  if (!d || stageBusy.value) return
  const ok = await ask(
    `Arsipkan klaim ${d.display_id || d.id} (${d.driver_name})?\nArchive this claim? (English)\n\n`
    + '⚠️ Catatan LPJ harusnya LENGKAP (pertanggungjawaban Subsidi Tepat) sebelum arsip — '
    + 'arsip menutup jejak verifikasi klaim ini.',
    {
      title: 'Arsip — LPJ driver',
      confirmText: '📦 Arsipkan',
    },
  )
  if (ok === null || ok === false) return
  stageBusy.value = true; detailMsg.value = ''
  try {
    const r = await api(`/api/queue/archive/${d.id}`, { method: 'POST' })
    detailMsg.value = '✅ ' + (r.msg || r.message || 'Klaim diarsipkan — dokumen tersimpan')
    if (cardRef.value?.reload) await cardRef.value.reload()
    loadBbm()
  } catch (e) {
    detailMsg.value = '❌ ' + (e.status === 409 ? 'Arsip ditahan — ' : '') + (e.message || 'Gagal mengarsipkan.')
  } finally { stageBusy.value = false }
}

// wave-18A: 📄 PDF per transaksi (GA/Finance/Admin diizinkan backend)
function openTxPdf() {
  const id = cardDetail.value?.id || detailFor.value?.id
  if (id) window.open('/admin/report/' + id)
}

async function reloadAfterSubsidy(msg) {
  bbmMsg.value = msg
  if (cardRef.value?.reload) await cardRef.value.reload()
  loadBbm()
}

async function linkSubsidy(st) {
  if (!detailFor.value || !st || linkBusy.value) return
  const ok = await ask(`Jodohkan klaim ini ke transaksi SPBU ${st.transaction_id} (${st.volume} L, ${st.spbu_id} ${st.witel || st.city}, ${st.transaction_date})?`, {
    title: 'Subsidi Tepat — Penjodohan',
    confirmText: 'Jodohkan',
  })
  if (!ok) return
  linkBusy.value = true
  try {
    const r = await api(`/api/subsidy/link/${detailFor.value.id}`, { method: 'POST', body: { subsidy_transaction_id: st.id } })
    await reloadAfterSubsidy('✅ ' + (r.msg || 'Tertaut ke SPBU resmi'))
  } catch (e) { bbmMsg.value = '❌ ' + e.message }
  finally { linkBusy.value = false }
}

async function unlinkSubsidy() {
  if (!detailFor.value || linkBusy.value) return
  const ok = await ask('Lepas penjodohan (tautan) verifikasi Subsidi Tepat klaim ini?', {
    title: 'Subsidi Tepat — Putuskan', confirmText: 'Putuskan', danger: true,
  })
  if (!ok) return
  linkBusy.value = true
  try {
    await api(`/api/subsidy/unlink/${detailFor.value.id}`, { method: 'POST' })
    await reloadAfterSubsidy('✅ Tautan dilepas')
  } catch (e) { bbmMsg.value = '❌ ' + e.message }
  finally { linkBusy.value = false }
}

// ============================================================
// v2.68.0 — Data SPBU Subsidi Tepat (agen menarik otomatis harian 06:15);
// Finance memantau kesiapan data + memicu pencocokan advisory 1 klik.
// ============================================================
const subsidy = ref({ count: 0, last_pull: '', oldest: '', newest: '', coverage: {} })
const subsidyBusy = ref(false)
const subsidyMsg = ref('')

async function loadSubsidy() {
  try { subsidy.value = await api('/api/subsidy/status') }
  catch { subsidy.value = { count: 0, last_pull: '', coverage: {} } }
}

async function autoMatch() {
  if (subsidyBusy.value) return
  subsidyBusy.value = true; subsidyMsg.value = ''
  try {
    const r = await api('/api/subsidy/auto-match', { method: 'POST' })
    subsidyMsg.value = '✅ ' + (r.msg || 'Pencocokan selesai')
    await Promise.all([loadSubsidy(), loadBbm()])
  } catch (e) {
    subsidyMsg.value = '❌ ' + (e.message || 'Gagal pencocokan otomatis')
  } finally { subsidyBusy.value = false }
}

const covLabel = { linked: '🔗 Dijodohkan', match: '✅ Match', close: '≈ Hampir', mismatch: '⚠ Selisih', no_record: '∅ Tanpa catatan', belum: '· Belum diproses' }
const covOrder = ['linked', 'match', 'close', 'mismatch', 'no_record', 'belum']
const covChips = computed(() =>
  covOrder.filter((k) => subsidy.value.coverage?.[k])
    .map((k) => ({ k, label: covLabel[k] || k, n: subsidy.value.coverage[k] })))

// ------------------------------------------------------------
// v2.69.0 — Login ulang agen Subsidi Tepat langsung dari dashboard:
// Finance minta OTP (email akun) → agen host login → ketik OTP di sini →
// verify token baru + pull/import/auto-match otomatis (state dari agen).
// ------------------------------------------------------------
const otp = ref({ state: 'idle', msg: '' })
const otpCode = ref('')
const otpBusy = ref(false)
let otpTimer = null

const OTP_LABELS = {
  idle: 'Idle', starting: 'Browser login berjalan…', waiting_otp: 'Menunggu OTP',
  verifying: 'Memverifikasi OTP…', syncing: 'Sinkron data…', done: 'Selesai — token baru', error: 'Gagal',
}
const otpLabel = computed(() => OTP_LABELS[otp.value?.state] || 'Idle')
const otpInputShown = computed(() => ['starting', 'waiting_otp'].includes(otp.value?.state))
const otpReady = computed(() => /^\d{6}$/.test(otpCode.value))
const otpTone = computed(() => (otp.value?.state === 'done' ? 'alert-success'
  : otp.value?.state === 'error' ? 'alert-error' : ''))

function otpPollStop() { if (otpTimer) { clearInterval(otpTimer); otpTimer = null } }

async function loadOtpStatus() {
  try {
    const st = await api('/api/subsidy/otp/status') || { state: 'idle' }
    const prev = otp.value?.state
    otp.value = st
    if (['starting', 'waiting_otp', 'verifying', 'syncing'].includes(st.state) && !otpTimer) {
      otpTimer = setInterval(loadOtpStatus, 4000)
    }
    if (st.state === 'done' || st.state === 'error') {
      otpPollStop()
      if (st.state === 'done' && prev && prev !== 'idle') {
        await Promise.all([loadSubsidy(), loadBbm()])
      }
    }
  } catch { /* gate belum ada — biarkan */ }
}

async function otpRequest() {
  if (otpBusy.value) return
  otpBusy.value = true
  try {
    const r = await api('/api/subsidy/otp/request', { method: 'POST' })
    if (r?.status === 'success') {
      otp.value = { state: 'starting', msg: r.msg }
      otpPollStop()
      otpTimer = setInterval(loadOtpStatus, 4000)
    } else {
      otp.value = { state: otp.value?.state || 'idle', msg: r?.msg || 'Gagal meminta login' }
    }
  } catch (e) {
    otp.value = { state: otp.value?.state || 'idle', msg: '❌ ' + (e.message || 'Gagal meminta login') }
  } finally { otpBusy.value = false }
}

async function otpSubmit() {
  if (otpBusy.value || !otpReady.value) return
  otpBusy.value = true
  try {
    const r = await api('/api/subsidy/otp/submit', { method: 'POST', body: { code: otpCode.value } })
    if (r?.status === 'success') {
      otpCode.value = ''
      otp.value = { state: 'verifying', msg: r.msg }
    } else {
      otp.value = { ...otp.value, msg: r?.msg || 'Kode OTP ditolak' }
    }
  } catch (e) {
    otp.value = { ...otp.value, msg: '❌ ' + (e.message || 'Kode OTP ditolak') }
  } finally { otpBusy.value = false }
}

onMounted(loadOtpStatus)
onBeforeUnmount(otpPollStop)

// ============================================================
// Berita Acara Rekonsiliasi — Subsidi Tepat (daftar BA + unduh PDF)
// ============================================================
const attestList = ref([])
const attestLoading = ref(false)

async function loadAttest() {
  attestLoading.value = true
  try { attestList.value = (await api('/api/subsidy/attest'))?.attestations || [] }
  catch { attestList.value = [] }
  finally { attestLoading.value = false }
}

function downloadAttest(a) {
  window.open(`/api/subsidy/attest/${a.id}/pdf`, '_blank')
}

function buildQuery() {
  const q = new URLSearchParams()
  if (from.value) q.set('from', from.value)
  if (to.value) q.set('to', to.value)
  const s = q.toString()
  return s ? '?' + s : ''
}

async function load() {
  loading.value = true
  try {
    data.value = await api('/api/water/recap' + buildQuery())
  } catch {
    data.value = null
  } finally {
    loading.value = false
  }
}

function exportCsv() {
  window.location.href = '/api/water/recap/export' + buildQuery()
}

function statusBadge(s) {
  return (
    { pending: ['⏳', 'badge-amber'], verified: ['✅', 'badge-blue'], rejected: ['✕', 'badge-gray'] }[s] || [s, 'badge-gray']
  )
}

onMounted(() => { load(); loadBbm(); loadAttest(); loadSubsidy() })
</script>

<template>
  <div class="page">
    <!-- Header + filter (v2.54.0: PageHeader standar) -->
    <PageHeader icon="💰" title="Dashboard Finance" subtitle="Rekap air minum & pekerjaan yang menunggu Anda">
      <label class="ph-filter">Dari
        <input v-model="from" type="date" class="inp" />
      </label>
      <label class="ph-filter">Sampai
        <input v-model="to" type="date" class="inp" />
      </label>
      <button class="btn btn-primary" @click="load">🔍 Terapkan</button>
      <button class="btn" @click="exportCsv" title="Unduh rekap sebagai CSV">⬇️ Export CSV</button>
    </PageHeader>

    <div v-if="loading" class="card card-pad muted skeleton">Memuat…</div>
    <template v-else-if="data">
      <!-- v2.53.0/wave-18A: kartu paling atas — Klaim BBM Menunggu Finance (lebih informatif) -->
      <div class="card card-pad attention-card" data-testid="bbm-quick">
        <div class="ac-icon">⛽</div>
        <div class="grow">
          <div class="ac-title">Klaim BBM Menunggu Finance</div>
          <div class="row" style="gap:18px;flex-wrap:wrap;margin:6px 0;" data-testid="bbm-quick-figures">
            <span style="font-size:13px;">💰 Siap Cair <small class="muted">(verified_ga)</small>
              · <b :style="bbm.ready ? 'color:var(--warning);font-size:17px;' : 'font-size:17px;'">{{ bbm.ready }}</b></span>
            <span style="font-size:13px;">🧾 Menunggu LPJ driver <small class="muted">(os_finance)</small>
              · <b style="font-size:17px;">{{ bbm.confirm }}</b></span>
          </div>
          <div class="ac-sub" style="user-select:text;">
            Alur bertingkat: <b>1 Verifikasi GA</b> → <b>2 Pencairan</b> → <b>3 LPJ/Arsip</b>.
            Klaim anomali wajib di-clear GA dulu sebelum bisa dicairkan. Verifikasi detail + foto bukti
            driver &amp; penjodohan Subsidi Tepat (riwayat SPBU resmi) langsung dari modal 👁 Detail.
          </div>
        </div>
        <router-link to="/dashboard" class="btn btn-primary" style="text-decoration:none;">🕐 Buka Antrean Verifikasi →</router-link>
      </div>

      <!-- p2: Antrean klaim BBM + instrumen verifikasi (turunan Admin Dashboard) -->
      <div class="card card-pad" style="margin-bottom:16px;" data-testid="bbm-verify-card">
        <div class="row" style="flex-wrap:wrap;gap:8px;align-items:center;">
          <h3 style="margin:0;">⛽ Antrean Klaim BBM</h3>
          <button class="btn btn-sm" :class="bbmTab === 'ready' ? 'btn-primary' : ''" @click="switchBbmTab('ready')">💰 Siap Dicairkan</button>
          <button class="btn btn-sm" :class="bbmTab === 'driver_confirm' ? 'btn-primary' : ''" @click="switchBbmTab('driver_confirm')">🤝 Konfirmasi Driver</button>
          <span v-if="bbmMsg" class="alert" style="margin:0;font-size:12px;" :class="bbmMsg.startsWith('✅') ? 'alert-success' : 'alert-error'">{{ bbmMsg }}</span>
        </div>
        <p class="muted" style="font-size:11px;margin:8px 0 0;">
          Klik <b>👁 Detail</b> untuk instrumen verifikasi: foto bukti, cross-check otomatis (ODO/budget/sinyal foto)
          dan penjodohan Subsidi Tepat (riwayat SPBU resmi akun perseroan).
        </p>
        <table class="table" style="margin-top:8px;">
          <thead><tr><th>Nomor</th><th>Driver / Nopol</th><th>Nominal</th><th>Status</th><th></th></tr></thead>
          <tbody>
            <tr v-for="t in visibleBbm" :key="t.id">
              <td><b>{{ t.display_id }}</b></td>
              <td>{{ t.driver_name }}<div class="muted" style="font-size:10px;">{{ t.nopol }}</div></td>
              <td>{{ fmtRp(t.nominal) }}</td>
              <td>
                <span v-if="t.ml_anomaly_flag" class="badge badge-amber">⚠️ Anomali ML</span>
                <span v-else class="badge badge-blue">{{ t.status === 'verified_ga' ? 'Siap Cair' : t.status }}</span>
              </td>
              <td><button class="btn btn-sm" :title="'Instrumen verifikasi ' + t.display_id" @click="openDetail(t)">👁 Detail</button></td>
            </tr>
            <tr v-if="!visibleBbm.length"><td colspan="5" class="muted">Antrean kosong 🎉</td></tr>
          </tbody>
        </table>
      </div>

      <!-- v2.68.0: kesiapan data SPBU Subsidi Tepat + pencocokan advisory 1 klik -->
      <div class="card card-pad" style="margin-bottom:16px;" data-testid="subsidy-data-card">
        <div class="row" style="flex-wrap:wrap;gap:8px;align-items:center;">
          <h3 style="margin:0;">⛽ Data SPBU — Subsidi Tepat</h3>
          <span v-if="subsidy.count" class="badge badge-blue" data-testid="subsidy-count">{{ subsidy.count }} transaksi terimpor</span>
          <span v-else class="badge badge-amber">Belum ada data</span>
          <div class="spacer"></div>
          <button class="btn btn-primary" :disabled="subsidyBusy" @click="autoMatch"
                  title="Bandingkan semua klaim BBM terbuka ke riwayat SPBU (advisory — putusan tetap saat verifikasi detail)">
            {{ subsidyBusy ? '⏳ Mencocokkan…' : '🤝 Cocokkan Klaim Otomatis' }}
          </button>
        </div>
        <div class="row" style="gap:18px;flex-wrap:wrap;margin:8px 0 4px;font-size:12px;">
          <span>📅 Rentang data: <b>{{ subsidy.oldest || '—' }}</b> s/d <b>{{ subsidy.newest || '—' }}</b></span>
          <span>⏱️ Tarik terakhir agen: <b>{{ (subsidy.last_pull || '—').slice(0, 19) }}</b> <span class="muted">(otomatis harian 06:15)</span></span>
        </div>
        <div v-if="covChips.length" class="row" style="gap:6px;flex-wrap:wrap;" data-testid="subsidy-coverage">
          <span v-for="c in covChips" :key="c.k" class="badge badge-gray">{{ c.label }}: <b>{{ c.n }}</b></span>
        </div>
        <span v-if="subsidyMsg" class="alert" style="margin-top:8px;font-size:12px;display:inline-block;"
              :class="subsidyMsg.startsWith('✅') ? 'alert-success' : 'alert-error'">{{ subsidyMsg }}</span>
        <div class="mini-tips" style="margin-top:8px;">
          💡 Kandidat kecocokan teperinci (nopol, tanggal, liter) tampil di modal <b>👁 Detail</b> klaim —
          tautkan di sana agar nomor transaksi resmi Pertamina ikut ke Berita Acara.
        </div>

        <!-- v2.69.0: login ulang agen (OTP) langsung dari Finance -->
        <div style="margin-top:10px;border-top:1px dashed var(--border, #e2e8f0);padding-top:10px;"
             data-testid="subsidy-otp">
          <div class="row" style="gap:8px;align-items:center;flex-wrap:wrap;">
            <b style="font-size:13px;">🔑 Login ulang agen</b>
            <span style="font-size:12px;">status: <b data-testid="otp-state">{{ otpLabel }}</b></span>
            <div class="spacer"></div>
            <button class="btn btn-sm" data-testid="otp-request" :disabled="otpBusy"
                    :title="'Browser login agen dijalankan — OTP dikirim ke email akun Subsidi Tepat'"
                    @click="otpRequest">✉ Minta OTP Email</button>
          </div>
          <div v-if="otpInputShown" class="row" style="gap:6px;margin-top:7px;align-items:center;flex-wrap:wrap;"
               data-testid="otp-input">
            <input v-model="otpCode" class="inp" data-testid="otp-code" inputmode="numeric"
                   maxlength="6" placeholder="6 digit OTP dari email" style="width:190px;"
                   @keyup.enter="otpSubmit" />
            <button class="btn btn-sm btn-primary" data-testid="otp-submit"
                    :disabled="otpBusy || !otpReady" @click="otpSubmit">✔ Kirim OTP</button>
            <span class="muted" style="font-size:11px;">Cek email akun Subsidi Tepat — kode berlaku singkat.</span>
          </div>
          <div v-if="otp.msg" class="alert" style="margin-top:6px;font-size:12px;display:inline-block;"
               :class="otpTone" data-testid="otp-msg">{{ otp.msg }}</div>
        </div>
      </div>

      <!-- Statistik air minum -->
      <div class="stat-grid" style="margin-bottom:16px;">
        <StatCard icon="📄" label="Total Pengajuan" :value="fmtNum(data.summary.total)" color="#2563eb" />
        <StatCard icon="⏳" label="Menunggu Verifikasi" :value="fmtNum(data.summary.pending)" color="#d97706" />
        <StatCard icon="✅" label="Terverifikasi" :value="fmtNum(data.summary.verified)" color="#059669" />
        <StatCard icon="✕" label="Ditolak" :value="fmtNum(data.summary.rejected)" color="#dc2626" />
        <StatCard icon="🚰" label="Total Kuantitas" :value="fmtNum(data.summary.qty)" color="#0d9488" />
      </div>

      <!-- Kasbon menunggu Finance -->
      <div class="stat-grid" style="margin-bottom:16px;">
        <StatCard icon="💵" label="Kasbon Menunggu Approve" :value="fmtRp(data.kasbon.waiting_approve.nominal)" color="#059669" :sub="data.kasbon.waiting_approve.count + ' pengajuan'" />
        <StatCard icon="🧾" label="LPJ Menunggu Approve" :value="fmtNum(data.kasbon.waiting_lpj.count) + ' pengajuan'" color="#7c3aed" sub="link ke halaman Kasbon" />
        <div class="stat-card">
          <span class="s-icon" style="background:#0d94881a;">🚰</span>
          <div class="s-value" style="color:#0d9488;">{{ data.per_ob.length }} OB</div>
          <div class="s-label">OB Aktif</div>
          <div class="s-bar" style="background:#0d9488;"></div>
        </div>
      </div>

      <div class="row" style="align-items:flex-start;gap:16px;margin-bottom:16px;">
        <!-- Antrean verifikasi -->
        <div class="card card-pad grow">
          <h3 style="margin-top:0;">🛡 Antrean Verifikasi Air Minum</h3>
          <table class="table">
            <thead><tr><th>Nomor</th><th>OB</th><th>Tanggal</th><th>Item</th><th></th></tr></thead>
            <tbody>
              <tr v-for="q in data.queue" :key="q.id">
                <td>{{ q.display_id }}</td>
                <td>{{ q.ob_name }}</td>
                <td>{{ q.purchase_date }}</td>
                <td>{{ q.item_count }}</td>
                <td><router-link class="btn btn-sm" to="/water">Verifikasi →</router-link></td>
              </tr>
              <tr v-if="!data.queue.length"><td colspan="5" class="muted">Tidak ada pengajuan menunggu verifikasi 🎉</td></tr>
            </tbody>
          </table>
          <div class="muted" style="font-size:11px;margin-top:8px;">
            {{ data.summary.pending }} pengajuan menunggu — verifikasi di halaman <router-link to="/water">Air Minum</router-link>
          </div>
        </div>

        <!-- Per OB -->
        <div class="card card-pad" style="min-width:320px;">
          <h3 style="margin-top:0;">👥 Ringkasan per OB</h3>
          <table class="table">
            <thead><tr><th>OB</th><th>Total</th><th>⏳</th><th>✅</th><th>✕</th></tr></thead>
            <tbody>
              <tr v-for="o in data.per_ob" :key="o.ob_name">
                <td>{{ o.ob_name }}</td>
                <td>{{ o.total }}</td>
                <td class="muted">{{ o.pending }}</td>
                <td class="muted">{{ o.verified }}</td>
                <td class="muted">{{ o.rejected }}</td>
              </tr>
              <tr v-if="!data.per_ob.length"><td colspan="5" class="muted">Belum ada pengajuan</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="row" style="align-items:flex-start;gap:16px;">
        <!-- Per jenis -->
        <div class="card card-pad grow">
          <h3 style="margin-top:0;">🥤 Per Jenis</h3>
          <div v-for="t in data.per_type" :key="t.name" class="bar-row">
            <span class="bar-label">{{ t.name }} — {{ fmtNum(t.qty) }} unit ({{ t.purchases }} pengajuan)</span>
            <div class="bar-track"><div class="bar-fill" :style="{ width: Math.min(100, t.qty / Math.max(1, data.per_type[0].qty) * 100) + '%' }"></div></div>
          </div>
          <div v-if="!data.per_type.length" class="muted">Belum ada data</div>
        </div>
        <!-- Per merk -->
        <div class="card card-pad grow">
          <h3 style="margin-top:0;">🏷️ Per Merk</h3>
          <div v-for="b in data.per_brand" :key="b.name" class="bar-row">
            <span class="bar-label">{{ b.name }} — {{ fmtNum(b.qty) }} unit ({{ b.purchases }} pengajuan)</span>
            <div class="bar-track"><div class="bar-fill" style="background:#0d9488;" :style="{ width: Math.min(100, b.qty / Math.max(1, data.per_brand[0].qty) * 100) + '%' }"></div></div>
          </div>
          <div v-if="!data.per_brand.length" class="muted">Belum ada data</div>
        </div>
      </div>

      <!-- m2: Berita Acara Rekonsiliasi — Subsidi Tepat (arsip server) -->
      <div class="card card-pad" style="margin-bottom:16px;" data-testid="attest-card">
        <div class="row" style="flex-wrap:wrap;gap:8px;align-items:center;">
          <h3 style="margin:0;">🖨 Berita Acara Rekonsiliasi — Subsidi Tepat</h3>
          <div class="spacer"></div>
          <button class="btn btn-sm" @click="loadAttest" title="Muat ulang daftar BA">🔄</button>
        </div>
        <p class="muted" style="font-size:11px;margin:6px 0 8px;">
          Kepastian hukum pencairan subsidi: klaim yang dijodohkan ke nomor transaksi resmi SPBU diikat per
          periode (root hash SHA-256) untuk kantor pusat/reguler.
        </p>
        <div v-if="attestLoading" class="muted" style="font-size:12px;">⏳ Memuat daftar BA…</div>
        <table v-else class="table">
          <thead><tr><th>BA</th><th>Periode</th><th>Klaim</th><th>Dibuat oleh</th><th>Waktu</th><th></th></tr></thead>
          <tbody>
            <tr v-for="a in attestList" :key="a.id">
              <td><b>#{{ a.id }}</b></td>
              <td>{{ a.period_start }} s/d {{ a.period_end }}</td>
              <td>{{ a.record_count }}</td>
              <td>{{ a.generated_by }}</td>
              <td class="muted" style="font-size:11px;">{{ (a.generated_at || '').slice(0, 19) }}</td>
              <td><button class="btn btn-sm" :title="'Unduh PDF BA #' + a.id" @click="downloadAttest(a)">📄 PDF</button></td>
            </tr>
            <tr v-if="!attestList.length"><td colspan="6" class="muted">Belum ada BA diterbitkan.</td></tr>
          </tbody>
        </table>
        <div class="mini-tips">
          💡 <b>Tips:</b> BA diterbitkan per periode bulanan dari Antrean Verifikasi (menu 💰 Finance di
          halaman Dashboard Admin/GA → <i>🖨 Berita Acara SPBU</i>) — pilih periode lalu <i>Terbitkan</i>.
          Pastikan semua klaim periode itu sudah dijodohkan (Subsidi Tepat) di modal 👁 Detail sebelum menerbitkan BA.
        </div>
      </div>
    </template>
    <div v-else class="card card-pad muted">Gagal memuat data.</div>

    <!-- Modal instrumen Detail klaim — ClaimVerifyCard + penjodohan Subsidi Tepat -->
    <Modal v-if="detailFor" :title="'⛽ ' + (detailFor.display_id || detailFor.id)" @close="detailFor = null">
      <ClaimVerifyCard ref="cardRef" :tx-id="detailFor.id" can-link @loaded="onCardLoaded">
        <template #link="{ candidate }">
          <button class="btn btn-sm btn-primary" :disabled="linkBusy" :title="'Jodohkan ke SPBU ' + candidate.spbu_id"
                  @click="linkSubsidy(candidate)">🔗 Jodohkan</button>
        </template>
      </ClaimVerifyCard>

      <!-- wave-18A: verifikasi BERTINGKAT — chip sewarna pipeline, langkah aktif menyala -->
      <div v-if="stageOn" class="stage-chips" data-testid="bbm-stage-chips">
        <span class="stage-chip" :class="{ on: stageOn >= 1 }">1️⃣ Verifikasi GA</span>
        <span class="stage-chip" :class="{ on: stageOn >= 2 }">2️⃣ Pencairan</span>
        <span class="stage-chip" :class="{ on: stageOn >= 3 }">3️⃣ LPJ/Arsip</span>
      </div>
      <p v-if="STAGE_META[detailStatus]" class="stage-active" data-testid="bbm-stage-active">
        ⛓ Langkah aktif: <b>{{ STAGE_META[detailStatus].label }}</b> — <span class="muted">{{ STAGE_META[detailStatus].hint }}</span>
      </p>

      <!-- hasil aksi server langsung di bawah modal -->
      <div v-if="detailMsg" style="margin-top:10px;">
        <span class="alert" style="font-size:12px;" :class="detailMsg.startsWith('✅') ? 'alert-success' : 'alert-error'">{{ detailMsg }}</span>
      </div>

      <div class="row" style="justify-content:flex-end;gap:8px;margin-top:12px;flex-wrap:wrap;">
        <!-- langkah aktif: aksi bertingkat berdasarkan detail.status -->
        <template v-if="detailStatus === 'verified_ga'">
          <button class="btn btn-primary" :disabled="stageBusy" title="Cairkan dana klaim (Disbursement) — wajib step-up PIN"
                  @click="doPayout">💰 Disbursement — Cairkan</button>
        </template>
        <template v-else-if="detailStatus === 'os_finance'">
          <button class="btn btn-primary" :disabled="stageBusy" title="Catatan LPJ harusnya LENGKAP sebelum arsip"
                  @click="doArchive">📦 Arsipkan</button>
        </template>
        <template v-else-if="detailStatus === 'archived'">
          <span class="badge badge-green" data-testid="bbm-archived-chip">4️⃣ Arsip · Selesai — dokumen tersimpan</span>
        </template>

        <!-- 📄 PDF per transaksi (tampil kecuali status pending) -->
        <button v-if="showPdf" class="btn" @click="openTxPdf" title="Unduh PDF laporan transaksi ini">📄 PDF</button>

        <button v-if="cardSubsidy?.linked" class="btn btn-danger" :disabled="linkBusy" @click="unlinkSubsidy">🔓 Putuskan</button>
        <button class="btn" @click="detailFor = null">Tutup</button>
      </div>
    </Modal>

    <ConfirmDialog ref="confirmRef" />
  </div>
</template>

<style scoped>
.row { display: flex; flex-wrap: wrap; }
.grow { flex: 1; min-width: 280px; }
.inp { padding: 6px 10px; border: 1px solid var(--border, #e2e8f0); border-radius: 8px; background: var(--card, #fff); color: var(--text, #0f172a); }
.table { width: 100%; border-collapse: collapse; font-size: 13px; }
.table th, .table td { text-align: left; padding: 7px 8px; border-bottom: 1px solid var(--border, #e2e8f0); }
.bar-row { margin-bottom: 8px; }
.bar-label { font-size: 12px; display: block; margin-bottom: 3px; }
.bar-track { height: 8px; background: var(--border, #e2e8f0); border-radius: 6px; overflow: hidden; }
.bar-fill { height: 100%; background: #2563eb; border-radius: 6px; transition: width .3s; }
.btn-sm { padding: 4px 10px; font-size: 12px; }
.mini-tips {
  margin-top: 10px; font-size: 12px; color: var(--text-2, #475569);
  border: 1px dashed var(--border, #e2e8f0); border-radius: var(--radius-sm, 8px);
  padding: 8px 10px; background: var(--surface-2, #f8fafc);
}
.spacer { flex: 1; }

/* wave-18A: verifikasi bertingkat — chip pipeline (langkah aktif menyala) */
.stage-chips { display: flex; gap: 7px; flex-wrap: wrap; margin-top: 14px; }
.stage-chip {
  font-size: 11px; font-weight: 600; padding: 4px 10px;
  border: 1px solid var(--border, #e2e8f0); border-radius: 999px;
  color: var(--text-3, #64748b); background: var(--surface-2, #f8fafc);
  opacity: .75;
}
.stage-chip.on {
  color: var(--surface, #fff);
  background: var(--primary, #2563eb);
  border-color: var(--primary, #2563eb);
  opacity: 1;
}
.stage-active { font-size: 12px; margin: 8px 0 0; }
</style>
