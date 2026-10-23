<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../../api'
import StatCard from '../../components/StatCard.vue'
import PageHeader from '../../components/PageHeader.vue'
import Modal from '../../components/Modal.vue'
import ConfirmDialog from '../../components/ConfirmDialog.vue'
import ClaimVerifyCard from '../../components/ClaimVerifyCard.vue'

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

function openDetail(tx) {
  detailFor.value = tx
  cardSubsidy.value = null
}

function onCardLoaded(payload) {
  cardSubsidy.value = payload?.subsidy || null
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

onMounted(() => { load(); loadBbm(); loadAttest() })
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
      <!-- v2.53.0/v2.54.0: Klaim BBM — pintasan pekerjaan utama Finance -->
      <div class="card card-pad attention-card" data-testid="bbm-quick">
        <div class="ac-icon">⛽</div>
        <div class="grow">
          <div class="ac-title">Klaim BBM menunggu keputusan Anda</div>
          <div class="ac-sub" style="user-select:text;">
            <b :style="bbm.ready ? 'color:var(--warning);' : ''">{{ bbm.ready }}</b> klaim terverifikasi GA siap dicairkan
            <template v-if="bbm.confirm"> · <b>{{ bbm.confirm }}</b> menunggu konfirmasi driver / arsip</template>
            — verifikasi Subsidi Tepat (riwayat SPBU resmi) langsung dari modal detail.
          </div>
        </div>
        <router-link to="/dashboard" class="btn btn-primary" style="text-decoration:none;">🕐 Buka Antrean Verifikasi</router-link>
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
      <div class="row" style="justify-content:flex-end;gap:8px;margin-top:12px;flex-wrap:wrap;">
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
</style>
