<script setup>
/**
 * Pengaturan ujian TKD + indikator kesiapan bank — panel staff.
 *
 * Backend hanya mengirim flag kesiapan per kategori/tier (bukan jumlah soal
 * aktif per kategori), jadi indikator menampilkan ✓/✗ dari flag tersebut.
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '../api'
import { useAuthStore } from '../stores/auth'

const CATEGORIES = ['REGULASI', 'PERUSAHAAN', 'PRODUK', 'HITUNG']
const TIERS = ['30k', '50k', '100k']

const auth = useAuthStore()
const isAdmin = computed(() => auth?.role === 'admin')

function emptyForm() {
  return {
    question_count: '20', duration_minutes: '25', pass_score: '70',
    quota: { REGULASI: '7', PERUSAHAAN: '4', PRODUK: '6', HITUNG: '3' },
    shuffle_options: false, active: false,
  }
}

const form = reactive(emptyForm())
const readiness = ref({ ready: false, active_valued: 0, quota_ok: {}, tier_ok: {}, reasons: [] })
const loading = ref(true)
const saving = ref(false)
const err = ref('')
const errReasons = ref([])
const msg = ref('')

const quotaSum = computed(() =>
  CATEGORIES.reduce((total, category) => total + (Number(form.quota[category]) || 0), 0))
const quotaMatches = computed(() => quotaSum.value === Number(form.question_count))

function messageOf(e, fallback) {
  const text = e?.data?.msg || e?.response?.data?.msg || e?.msg || e?.message
  return typeof text === 'string' && text ? text : fallback
}

function reasonsOf(e) {
  const raw = e?.data?.reasons || e?.response?.data?.reasons || e?.reasons
  return Array.isArray(raw) ? raw.filter((item) => typeof item === 'string' && item) : []
}

function flag(value) {
  return value === true || value === 1 || value === '1' ? '✓' : '✗'
}

function toNumber(value) {
  const number = Number(value)
  return Number.isFinite(number) ? number : 0
}

async function load() {
  loading.value = true
  err.value = ''
  errReasons.value = []
  msg.value = ''
  try {
    const data = (await api('/api/recruitment/tkd/settings'))?.data || {}
    const quota = data.quota || {}
    form.question_count = String(data.question_count ?? '')
    form.duration_minutes = String(data.duration_minutes ?? '')
    form.pass_score = String(data.pass_score ?? '')
    CATEGORIES.forEach((category) => {
      form.quota[category] = String(quota[category] ?? '')
    })
    form.shuffle_options = data.shuffle_options === true || Number(data.shuffle_options) === 1
    form.active = data.active === true || Number(data.active) === 1
    const current = data.readiness || {}
    readiness.value = {
      ready: current.ready === true,
      active_valued: current.active_valued ?? 0,
      quota_ok: current.quota_ok || {},
      tier_ok: current.tier_ok || {},
      reasons: Array.isArray(current.reasons) ? current.reasons : [],
    }
    return true
  } catch (e) {
    err.value = messageOf(e, 'Gagal memuat pengaturan.')
    return false
  } finally {
    loading.value = false
  }
}

async function save() {
  if (!isAdmin.value || saving.value || loading.value) return
  const body = {
    question_count: toNumber(form.question_count),
    duration_minutes: toNumber(form.duration_minutes),
    pass_score: toNumber(form.pass_score),
    max_attempts: 2,
    quota: Object.fromEntries(CATEGORIES.map((category) =>
      [category, toNumber(form.quota[category])])),
    shuffle_options: form.shuffle_options === true,
    active: form.active === true,
  }
  saving.value = true
  err.value = ''
  errReasons.value = []
  msg.value = ''
  try {
    await api('/api/recruitment/tkd/settings', { method: 'PUT', body })
    if (await load()) msg.value = 'Pengaturan berhasil disimpan.'
  } catch (e) {
    err.value = messageOf(e, 'Gagal menyimpan pengaturan.')
    errReasons.value = reasonsOf(e)
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="tks-panel">
    <div v-if="err" class="alert alert-error" data-alert="error">{{ err }}</div>
    <div v-if="msg" class="alert alert-success" data-alert="success">{{ msg }}</div>

    <div class="card card-pad">
      <h3>⚙️ Pengaturan Ujian TKD</h3>
      <p class="muted tks-sub">Atur durasi, ambang kelulusan, dan komposisi soal.</p>

      <div v-if="loading" class="tks-empty">⏳ Memuat pengaturan…</div>
      <template v-else>
        <div class="tks-grid">
          <label class="tks-field">Jumlah soal
            <input class="input" type="number" min="1" max="100" step="1"
                   data-field="question_count" v-model="form.question_count"
                   :disabled="!isAdmin || loading" />
          </label>
          <label class="tks-field">Durasi (menit)
            <input class="input" type="number" min="5" max="180" step="1"
                   data-field="duration_minutes" v-model="form.duration_minutes"
                   :disabled="!isAdmin || loading" />
          </label>
          <label class="tks-field">Nilai lulus
            <input class="input" type="number" min="0" max="100" step="any"
                   data-field="pass_score" v-model="form.pass_score"
                   :disabled="!isAdmin || loading" />
          </label>
          <label class="tks-field">Maksimal percobaan
            <input class="input" type="number" value="2" data-field="max_attempts" disabled />
            <small class="muted">Tetap 2 pada rilis ini.</small>
          </label>
        </div>

        <fieldset class="tks-fieldset" data-fieldset="quota">
          <legend>Kuota per kategori</legend>
          <div class="tks-grid">
            <label v-for="category in CATEGORIES" :key="category" class="tks-field">
              {{ category }}
              <input class="input" type="number" min="0" step="1"
                     :data-field="`quota_${category}`" :data-quota="category"
                     v-model="form.quota[category]" :disabled="!isAdmin || loading" />
            </label>
          </div>
          <p class="tks-sub" :class="{ 'tks-warn': !quotaMatches }" data-quota-summary>
            Jumlah kuota: {{ quotaSum }} dari {{ form.question_count }} soal.
            <template v-if="!quotaMatches">Jumlah kuota harus sama dengan jumlah soal.</template>
          </p>
        </fieldset>

        <div class="tks-flags">
          <label class="tks-check">
            <input type="checkbox" data-field="shuffle_options"
                   v-model="form.shuffle_options" :disabled="!isAdmin || loading" />
            Acak opsi jawaban
          </label>
          <label class="tks-check">
            <input type="checkbox" data-field="active" v-model="form.active"
                   :disabled="!isAdmin || loading" />
            Aktifkan ujian TKD
          </label>
        </div>
      </template>
    </div>

    <div class="card card-pad tks-readiness-card">
      <h3>📈 Kesiapan bank soal</h3>
      <div class="tks-readiness" data-readiness>
        <span><b>Soal aktif:</b> {{ readiness.active_valued }}/{{ form.question_count }}</span>
        <span v-for="category in CATEGORIES" :key="category" :data-quota-status="category">
          {{ category }} {{ flag(readiness.quota_ok?.[category]) }}
        </span>
        <span v-for="tier in TIERS" :key="tier" :data-tier-status="tier">
          {{ tier }} {{ flag(readiness.tier_ok?.[tier]) }}
        </span>
      </div>
      <p class="tks-sub">Tier minimal 3 soal HITUNG aktif per tingkat.</p>
      <ul v-if="!readiness.ready && readiness.reasons.length" class="tks-reasons"
          data-readiness-reasons>
        <li v-for="(reason, i) in readiness.reasons" :key="i">{{ reason }}</li>
      </ul>
    </div>

    <div v-if="errReasons.length" class="alert alert-error" data-error-reasons>
      <div v-for="(reason, i) in errReasons" :key="i">• {{ reason }}</div>
    </div>

    <div class="tks-actions">
      <p v-if="!isAdmin" class="muted tks-sub" data-admin-note>
        Hanya admin dapat mengubah pengaturan.
      </p>
      <button class="btn btn-primary" type="button" data-action="save"
              :disabled="!isAdmin || saving || loading" @click="save">
        {{ saving ? 'Menyimpan…' : 'Simpan pengaturan' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.tks-sub { font-size: 12px; margin-top: 4px; }
.tks-empty { padding: 20px; text-align: center; color: var(--text-3); font-size: 12px; }
.tks-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 10px; margin-top: 12px; }
.tks-field { display: grid; gap: 4px; font-size: 12px; color: var(--text-2); }
.tks-fieldset { border: 1px solid var(--border); border-radius: 10px; padding: 12px; margin-top: 14px; }
.tks-fieldset legend { font-size: 12px; font-weight: 700; padding: 0 6px; }
.tks-warn { color: #b45309; font-weight: 600; }
.tks-flags { display: flex; flex-wrap: wrap; gap: 16px; margin-top: 14px; }
.tks-check { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; }
.tks-readiness-card { margin-top: 12px; }
.tks-readiness { display: flex; flex-wrap: wrap; gap: 8px 16px; margin-top: 8px; font-size: 12px; }
.tks-reasons { margin: 8px 0 0; padding-left: 18px; font-size: 12px; color: #b91c1c; }
.tks-actions { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; justify-content: flex-end; margin-top: 12px; }
.tks-actions .tks-sub { margin: 0 auto 0 0; }
</style>
