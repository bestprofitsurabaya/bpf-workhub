<script setup>
/**
 * ClaimVerifyCard — instrumen verifikasi keabsahan klaim BBM yang ringkas,
 * dapat dipakai ulang di Dashboard GA/Finance (turunan dari modal Detail
 * AdminDashboard, tanpa tab): Data Klaim + Cross-Check Otomatis + Subsidi Tepat.
 *
 * Role boleh GET: /api/transactions/detail, /api/cross-check, /api/subsidy/match
 * (ga/finance/admin). Penjodohan (link/unlink) hanya finance/admin — komponen
 * tidak pernah memanggil endpoint itu sendiri; lewat slot `link` + event
 * `link`/`unlink` yang dipancarkan ke view pemakai.
 */
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import LoadingState from './LoadingState.vue'
import ErrorState from './ErrorState.vue'

const props = defineProps({
  txId: { type: [Number, String], required: true },
  // tampilkan kolom slot jodohkan per kandidat (true = dilanjutkan finance/admin)
  canLink: { type: Boolean, default: false },
})
const emit = defineEmits(['link', 'unlink', 'loaded'])

const data = ref(null)      // /api/transactions/detail
const cross = ref(null)     // /api/cross-check
const subsidy = ref(null)   // /api/subsidy/match
const loading = ref(true)
const err = ref('')

async function load() {
  loading.value = true
  err.value = ''
  try {
    const [d, c, st] = await Promise.all([
      api(`/api/transactions/detail/${props.txId}`),
      api(`/api/cross-check/${props.txId}`).catch(() => null),
      api(`/api/subsidy/match/${props.txId}`).catch(() => null),
    ])
    data.value = d
    cross.value = c
    subsidy.value = st
    emit('loaded', { detail: d, cross: c, subsidy: st })
  } catch (e) {
    err.value = e.message || 'Gagal memuat detail klaim.'
  } finally {
    loading.value = false
  }
}

function reload() { return load() } // dipanggil view setelah link/unlink sukses
defineExpose({ reload })

// ------------- tampilan bantu -------------
const fmtRp = (n) => 'Rp ' + (Number(n) || 0).toLocaleString('id-ID')
const fmtNum = (n) => (Number(n) || 0).toLocaleString('id-ID')
const flagCls = (lv) =>
  lv === 'danger' ? ['badge-red', '🔴'] : lv === 'warning' ? ['badge-amber', '🟡'] : ['badge-green', '🟢']

const hsColor = computed(() => {
  const hs = Number(cross.value?.health_score ?? 0)
  return hs >= 80 ? 'var(--success, #059669)' : hs >= 60 ? 'var(--warning, #d97706)' : 'var(--danger, #dc2626)'
})

const VERDICT_META = {
  match: { cls: 'badge-green', label: '🟢 Cocok' },
  close: { cls: 'badge-amber', label: '🟡 Dekat' },
  mismatch: { cls: 'badge-amber', label: '🟡 Tidak pas' },
  no_record: { cls: 'badge-red', label: '🔴 Tak ada riwayat SPBU' },
  no_match: { cls: 'badge-amber', label: '🟡 Tak ada yang pas' },
  linked: { cls: 'badge-green', label: '🟢 Tertaut' },
}
const verdictMeta = (v) => VERDICT_META[v || 'no_record'] || { cls: 'badge-gray', label: (v || '—').toUpperCase() }

const dVolFmt = (v) => (v > 0 ? '+' : '') + fmtNum(v)

// kandidat: tandai yang terpilih, maksimal 5 baris
const candidates = computed(() => (subsidy.value?.candidates || []).slice(0, 5))

// wave-17: rantai verifikasi per-peran — dibaca dari field aktor+waktu detail
const gaDone = computed(() => !!data.value?.ga_approved_by || !!data.value?.anomaly_cleared_by)
const finDone = computed(() => !!data.value?.finance_payout_by)
const archDone = computed(() => !!data.value?.archived_by)

onMounted(load)
</script>

<template>
  <div class="cvc" data-testid="claim-verify-card">
    <div v-if="loading"><LoadingState rows="3" label="Memuat detail klaim…" /></div>

    <ErrorState v-else-if="err" :message="err" @retry="load" />

    <template v-else-if="data">
      <!-- (1) Data Klaim -->
      <section class="cvc-block">
        <h4 class="cvc-title">📋 Data Klaim</h4>
        <div class="cvc-data">
          <div class="cvc-photos">
            <template v-if="data.photos?.length">
              <figure v-for="p in data.photos" :key="p.url" class="cvc-photo">
                <img :src="p.url" :alt="'Foto ' + p.label" loading="lazy" />
                <figcaption>{{ p.label }}</figcaption>
              </figure>
            </template>
            <div v-else class="muted" style="font-size:12px;">Tidak ada foto bukti.</div>
          </div>
          <table class="cvc-tbl">
            <tbody>
              <tr><th>Nomor</th><td><b>{{ data.display_id || data.id }}</b></td></tr>
              <tr><th>Driver</th><td>{{ data.driver_name }}</td></tr>
              <tr><th>Nopol</th><td>{{ data.nopol }}<span v-if="data.vehicle_type" class="muted"> · {{ data.vehicle_type }}</span></td></tr>
              <tr><th>Liter / Nominal</th><td>{{ fmtNum(data.liter) }} L · <b>{{ fmtRp(data.nominal) }}</b></td></tr>
              <tr><th>ODO</th><td>{{ fmtNum(data.odo_km) }} km<span v-if="data.km_per_liter" class="muted"> · {{ Number(data.km_per_liter).toFixed(1) }} km/L</span></td></tr>
              <tr><th>Waktu Klaim</th><td class="muted">{{ data.created_at }}</td></tr>
              <tr v-if="data.gps_address"><th>Lokasi GPS</th><td>📍 {{ data.gps_address }}</td></tr>
              <tr v-if="data.ml_anomaly_flag || data.is_mypertamina_error">
                <th>Penanda</th>
                <td>
                  <span v-if="data.ml_anomaly_flag" class="badge badge-red">⚠️ Anomali ML</span>
                  <span v-if="data.is_mypertamina_error" class="badge badge-amber" style="margin-left:4px;">⚠️ Error MyPertamina</span>
                </td>
              </tr>
              <tr v-if="data.rejection_reason"><th>Alasan Tolak</th><td style="color:var(--danger, #dc2626);">{{ data.rejection_reason }}</td></tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- (2) Cross-Check Otomatis -->
      <section class="cvc-block">
        <h4 class="cvc-title">🩺 Cross-Check Otomatis</h4>
        <template v-if="cross">
          <div class="cvc-hs">
            <span class="cvc-hs-val" :style="{ color: hsColor }">{{ fmtNum(cross.health_score || 0) }}<small>/100</small></span>
            <div class="cvc-hs-meta">
              <span>Health Score</span>
              <span class="muted" style="font-size:11px;">
                Budget {{ fmtNum(cross.budget_usage_percent ?? 0) }}% · Selisih ODO {{ dVolFmt(cross.odo_diff || 0) }} km
              </span>
            </div>
            <div v-if="cross.previous_odo" class="cvc-odo" style="border-color:var(--border);background:var(--surface-2);">
              <b>ODO sebelumnya</b>
              <span class="muted" style="font-size:11px;">{{ fmtNum(cross.previous_odo.odo_km) }} km</span>
            </div>
          </div>
          <ul class="cvc-flags">
            <li v-for="(f, i) in cross.flags || []" :key="'f' + i" :class="f.level === 'danger' ? 'alert-error' : f.level === 'warning' ? 'alert-info' : 'alert-success'">
              {{ f.level === 'danger' ? '🔴' : f.level === 'warning' ? '🟡' : '🟢' }} {{ f.msg }}
            </li>
            <li v-if="!(cross.flags || [])?.length" class="muted" style="list-style:none;">Tidak ada flag — transaksi bersih ✅</li>
            <li v-for="(f, i) in cross.proof_signals || []" :key="'p' + i" :class="f.level === 'danger' ? 'alert-error' : f.level === 'warning' ? 'alert-info' : 'alert-success'">
              {{ f.level === 'warning' ? '🟡' : '📷' }} {{ f.msg }}
            </li>
          </ul>
          <p class="muted" style="font-size:11px;margin:6px 0 0;">
            Rekomendasi: <b>{{ cross.recommendation || '—' }}</b>
            <template v-if="cross.avg_3months"> · Rata-rata 3 bulan: {{ cross.avg_3months.avg_kml || '—' }} km/L ({{ fmtNum(cross.avg_3months.tx_count || 0) }} tx)</template>
          </p>
        </template>
        <p v-else class="muted" style="font-size:12px;margin:0;">Cross-check tidak tersedia untuk transaksi ini.</p>
      </section>

      <!-- (3) Subsidi Tepat -->
      <section class="cvc-block">
        <h4 class="cvc-title">⛽ Subsidi Tepat</h4>
        <template v-if="subsidy">
          <!-- Terpasang: tampilkan riwayat SPBU yang dijodohkan -->
          <div v-if="subsidy.linked" class="cvc-note" style="border-color:#05966933;background:#05966914;color:var(--success, #059669);">
            <b>✅ Terpasang ke SPBU resmi:</b>
            <div style="color:var(--text);">
              <b>{{ subsidy.linked.transaction_id }}</b> · {{ fmtNum(subsidy.linked.volume) }} L · {{ fmtRp(subsidy.linked.amount) }}
              · {{ subsidy.linked.transaction_date }} · SPBU {{ subsidy.linked.spbu_id }}<span v-if="subsidy.linked.witel || subsidy.linked.city"> {{ subsidy.linked.witel || subsidy.linked.city }}</span>
              <span v-if="subsidy.linked_by" class="muted"> — dijodohkan oleh {{ subsidy.linked_by }}</span>
            </div>
            <span class="badge badge-green" style="margin-top:4px;">Terpasang</span>
          </div>

          <!-- Belum: kandidat penjodohan -->
          <template v-else>
            <div class="cvc-note"
                 :style="subsidy.verdict === 'no_record' ? 'border-color:#dc262633;background:#dc26260d;' : 'border-color:#d9770633;background:#d977060d;color:var(--text);'">
              <span v-if="subsidy.verdict === 'no_record'" style="color:var(--danger, #b91c1c);">
                🔴 Tidak ada transaksi SPBU untuk nopol ini ±1 hari dari tanggal klaim.
              </span>
              <span v-else-if="subsidy.verdict === 'no_match'" style="color:#b45309;">🟡 Ada kandidat, tapi tidak ada yang sesuai liter/nominal.</span>
              <span v-else-if="subsidy.verdict === 'close'" style="color:#b45309;">🟡 Kandidat mendekati (selisih kecil) — periksa sebelum menjodohkan.</span>
              <span v-else style="color:var(--success, #059669);">🟢 Ada kandidat yang cocok (liter &amp; nominal).</span>
            </div>
            <table v-if="candidates.length || subsidy.candidates?.length" class="tbl" style="margin-top:6px;font-size:12px;">
              <thead><tr><th>Transaksi SPBU</th><th>Waktu</th><th>Volume</th><th>Nominal</th><th>SPBU</th><th>Verifikasi</th><th v-if="canLink"></th></tr></thead>
              <tbody>
                <tr v-for="c in candidates" :key="c.id">
                  <td><b>{{ c.transaction_id }}</b><div class="muted" style="font-size:10px;">{{ c.product }}</div></td>
                  <td class="muted">{{ c.transaction_date }}</td>
                  <td>{{ fmtNum(c.volume) }} L <span v-if="c.dvol" class="muted">({{ dVolFmt(c.dvol) }})</span></td>
                  <td>{{ fmtRp(c.amount) }} <span v-if="c.dnom" class="muted">({{ dVolFmt(c.dnom) }})</span></td>
                  <td>{{ c.spbu_id }}<span v-if="c.witel || c.city" class="muted"> · {{ c.witel || c.city }}</span></td>
                  <td><span class="badge" :class="verdictMeta(c.verdict).cls">{{ verdictMeta(c.verdict).label }}</span></td>
                  <td v-if="canLink" class="cvc-link-slot"><slot name="link" :candidate="c" /></td>
                </tr>
              </tbody>
            </table>
            <p v-else class="muted" style="font-size:12px;margin:6px 0 0;">Tidak ada riwayat SPBU kandidat untuk klaim ini.</p>
            <p v-if="canLink" class="muted" style="font-size:11px;margin:6px 0 0;">
              Data riwayat diimpor dari portal Subsidi Tepat (read-only) — bantuan verifikasi, keputusan tetap Anda.
            </p>
            <p v-else class="muted" style="font-size:11px;margin:6px 0 0;">
              Penjodohan klaim ↔ SPBU dilakukan oleh Finance setelah ACC GA.
            </p>
          </template>
        </template>
        <p v-else class="muted" style="font-size:12px;margin:0;">Data Subsidi Tepat tidak tersedia.</p>
      </section>

      <!-- (4) Rantai Verifikasi — per-peran (wave-17) -->
      <section class="cvc-block">
        <h4 class="cvc-title">⛓ Rantai Verifikasi</h4>
        <ul class="cvc-chain">
          <!-- 1: driver submit -->
          <li class="cvc-step">
            <span class="cvc-dot cvc-dot-done" aria-hidden="true"></span>
            <div class="cvc-step-body">
              <b>🚗 Klaim diajukan driver</b>
              <span class="muted">{{ data.driver_name }}<template v-if="data.display_id"> · {{ data.display_id }}</template> · {{ data.created_at }}</span>
            </div>
          </li>
          <!-- 2: GA -->
          <li class="cvc-step" :class="{ 'cvc-step-pending': !gaDone }">
            <span class="cvc-dot" :class="gaDone ? 'cvc-dot-done' : 'cvc-dot-pending'" aria-hidden="true"></span>
            <div class="cvc-step-body">
              <template v-if="gaDone">
                <div class="cvc-step-head">
                  <b>🛡 Verifikasi GA</b>
                  <span class="badge badge-green" style="font-size:10px;">Selesai</span>
                </div>
                <span class="muted">
                  {{ data.ga_approved_by || data.anomaly_cleared_by }}<template v-if="data.ga_approved_at"> · {{ data.ga_approved_at }}</template>
                  <template v-if="data.anomaly_cleared_by && data.anomaly_cleared_at"> · anomali diklarifikasi {{ data.anomaly_cleared_at }}</template>
                </span>
              </template>
              <template v-else><b class="muted">🛡 Verifikasi GA</b><span class="muted">Menunggu verifikasi GA…</span></template>
            </div>
          </li>
          <!-- 3: Finance -->
          <li class="cvc-step" :class="{ 'cvc-step-pending': !finDone }">
            <span class="cvc-dot" :class="finDone ? 'cvc-dot-done' : 'cvc-dot-pending'" aria-hidden="true"></span>
            <div class="cvc-step-body">
              <template v-if="finDone">
                <b>🏦 Verifikasi &amp; Pencairan Finance</b>
                <span class="muted">{{ data.finance_payout_by }}<template v-if="data.finance_payout_at"> · {{ data.finance_payout_at }}</template></span>
                <span v-if="subsidy?.linked" class="muted cvc-subrow">
                  ⛽ Penjodohan SPBU: {{ data.subsidy_linked_by || '—' }}<template v-if="data.subsidy_linked_at"> · {{ data.subsidy_linked_at }}</template>
                </span>
              </template>
              <template v-else><b class="muted">🏦 Verifikasi &amp; Pencairan Finance</b><span class="muted">Menunggu Finance…</span></template>
            </div>
          </li>
          <!-- 4: Arsip -->
          <li class="cvc-step" :class="{ 'cvc-step-pending': !archDone }">
            <span class="cvc-dot" :class="archDone ? 'cvc-dot-done' : 'cvc-dot-pending'" aria-hidden="true"></span>
            <div class="cvc-step-body">
              <template v-if="archDone">
                <b>🗄 Arsip</b>
                <span class="muted">{{ data.archived_by }}<template v-if="data.archived_at"> · {{ data.archived_at }}</template></span>
              </template>
              <template v-else><b class="muted">🗄 Arsip</b><span class="muted">Belum diarsipkan…</span></template>
            </div>
          </li>
          <!-- catatan modifikasi (jika ada) -->
          <li v-if="data.modified_by || data.modification_note" class="cvc-step">
            <span class="cvc-dot" aria-hidden="true"></span>
            <div class="cvc-step-body">
              <b>✏️ Data dikoreksi</b>
              <span class="muted">{{ data.modified_by || '—' }} — {{ data.modification_note || '—' }}</span>
            </div>
          </li>
          <!-- ditolak -->
          <li v-if="data.status === 'rejected' && data.rejection_reason" class="cvc-step cvc-step-rejected">
            <span class="cvc-dot cvc-dot-rejected" aria-hidden="true"></span>
            <div class="cvc-step-body">
              <b>❌ Ditolak — {{ data.rejection_reason }}</b>
            </div>
          </li>
        </ul>
      </section>
    </template>
  </div>
</template>

<style scoped>
.cvc { display: flex; flex-direction: column; gap: 14px; }
.cvc-block { border: 1px solid var(--border); border-radius: var(--radius, 12px); background: var(--surface-2, #f8fafc); padding: 10px 12px; }
.cvc-title { margin: 0 0 8px; font-size: 13px; font-weight: 700; }
.cvc-data { display: flex; gap: 12px; flex-wrap: wrap; }
.cvc-photos { display: flex; gap: 10px; flex-wrap: wrap; }
.cvc-photo { margin: 0; text-align: center; }
.cvc-photo img {
  width: 110px; height: 110px; object-fit: cover; display: block;
  border-radius: var(--radius-sm, 8px); border: 1px solid var(--border); background: var(--surface);
}
.cvc-photo figcaption { font-size: 10px; color: var(--text-3); margin-top: 3px; }
.cvc-tbl { flex: 1; min-width: 240px; border-collapse: collapse; font-size: 12.5px; }
.cvc-tbl th { text-align: left; padding: 4px 10px 4px 0; color: var(--text-3); font-weight: 600; white-space: nowrap; }
.cvc-tbl td { padding: 4px 0; }
.cvc-hs { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 6px; }
.cvc-hs-val { font-size: 22px; font-weight: 800; }
.cvc-hs-val small { font-size: 12px; color: var(--text-3); font-weight: 500; }
.cvc-hs-meta { display: flex; flex-direction: column; gap: 2px; font-size: 12px; }
.cvc-odo { border: 1px solid var(--border); border-radius: var(--radius-sm, 8px); padding: 6px 10px; font-size: 12px; display: flex; flex-direction: column; gap: 2px; }
.cvc-note { border: 1px solid var(--border); border-radius: var(--radius-sm, 8px); padding: 8px 10px; font-size: 12px; }
.cvc-flags { margin: 6px 0 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 4px; }
.cvc-flags li { padding: 4px 8px; border-radius: 6px; font-size: 12px; }
.muted { color: var(--text-3, #64748b); }

/* wave-17: rantai verifikasi vertikal (dot + garis, CSS murni) */
.cvc-chain { margin: 0; padding: 0; list-style: none; }
.cvc-step {
  position: relative;
  display: flex;
  gap: 8px;
  padding: 0 0 12px 0;
  font-size: 12px;
}
/* garis penghubung antardot */
.cvc-step:not(:last-child)::before {
  content: '';
  position: absolute;
  left: 4px;
  top: 14px;
  bottom: 0;
  width: 1px;
  background: var(--border);
}
.cvc-dot { flex: none; width: 8px; height: 8px; border-radius: 50%; margin-top: 4px; }
.cvc-dot-done { background: var(--success, #059669); }
.cvc-dot-pending { background: var(--border, #cbd5e1); box-shadow: 0 0 0 2px var(--surface-2, #f8fafc); }
.cvc-dot-rejected { background: var(--danger, #dc2626); }
.cvc-step-body { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.cvc-step-head { display: flex; align-items: center; gap: 6px; }
.cvc-step-pending .cvc-step-body b { color: var(--text-3, #64748b); font-weight: 500; }
.cvc-subrow { font-size: 11px; }
.cvc-step-rejected { color: var(--danger, #dc2626); }

</style>
