<script setup>
/**
 * Rilis C — portal satu tautan per cabang: cek NIK sekali (tanpa tanggal
 * lahir), lalu tampilkan ringkasan empat langkah dan langkah berikutnya.
 * Cabang selalu berasal dari token tautan; NIK lengkap tidak disimpan di
 * komponen ini setelah sesi diterbitkan.
 */
import { computed, ref } from 'vue'
import { api } from '../api'
import RecruitmentTkdPanel from '../components/RecruitmentTkdPanel.vue'

const brandIcon = '/static/icon-192.png'

const linkParams = new URLSearchParams(window.location.search)
const branchToken = (linkParams.get('token') || linkParams.get('t') || '').trim()

const nik = ref('')
const error = ref('')
const checking = ref(false)
const sessionToken = ref('')
const summary = ref(null)
const tkdOpen = ref(false)

const stageByType = computed(() => {
  const stages = summary.value?.stages || []
  return Object.fromEntries(stages.map((stage) => [stage.type, stage]))
})

const formHref = (path) => {
  const query = new URLSearchParams({ token: branchToken })
  if (sessionToken.value) query.set('s', sessionToken.value)
  return `/app/${path}?${query.toString()}`
}

const STEPS = [
  { type: 'CV', label: 'CV Online', desc: 'Registrasi data diri, pendidikan, dan pengalaman.', path: 'cv-online-form' },
  { type: 'TRAINING', label: 'Training Absensi', desc: 'Absensi Hari 1 dan Hari 2 training.', path: 'training-form' },
  { type: 'TKD', label: 'Test Kemampuan Dasar', desc: 'Penilaian kemampuan dasar peserta.', path: '' },
  { type: 'FIRSTWORK', label: 'FirstWork Absensi', desc: 'Absensi peserta dan cetak kartu.', path: 'first-work-form' },
]

function onNik(event) {
  nik.value = String(event.target.value || '').replace(/\D/g, '').slice(0, 16)
}

function stepStatus(step) {
  const stage = stageByType.value[step.type]
  if (!stage) return 'BELUM'
  return stage.status || 'BELUM'
}

function isLocked(step) {
  if (!sessionToken.value) return step.type !== 'CV'
  if (step.type === 'CV') return false
  const stage = stageByType.value[step.type]
  return stage ? stage.can_start === false : false
}

function isDone(step) {
  return stepStatus(step) === 'SELESAI'
}

function tkdCardOpen(step) {
  return step.type === 'TKD' && !isLocked(step)
}

function cardTag(step) {
  if (tkdCardOpen(step)) return 'button'
  return step.path && !isLocked(step) ? 'a' : 'div'
}

function cardAttrs(step) {
  if (tkdCardOpen(step)) return { type: 'button' }
  return step.path && !isLocked(step) ? { href: formHref(step.path) } : {}
}

function onCardClick(step) {
  if (tkdCardOpen(step)) tkdOpen.value = true
}

async function check() {
  error.value = ''
  if (nik.value.length !== 16) {
    error.value = 'NIK wajib 16 digit angka.'
    return
  }
  if (!branchToken) {
    error.value = 'Tautan portal cabang tidak valid. Minta tautan terbaru ke resepsionis.'
    return
  }

  summary.value = null
  sessionToken.value = ''
  tkdOpen.value = false
  checking.value = true
  try {
    const result = await api('/api/recruitment/lookup', {
      params: { nik: nik.value, token: branchToken },
    })
    if (!result || !result.session_token) {
      error.value = 'NIK tidak dapat diverifikasi. Periksa kembali atau minta tautan cabang.'
      return
    }
    sessionToken.value = result.session_token
    const response = await api('/api/recruitment/portal/summary', {
      params: { token: sessionToken.value },
    })
    summary.value = response?.data || null
    if (!result.known) {
      error.value = 'NIK belum dikenal. Mulai dari CV Online.'
    }
  } catch (e) {
    error.value = e?.message || 'Pengecekan gagal. Coba lagi sebentar.'
  } finally {
    checking.value = false
  }
}
</script>

<template>
  <main class="rp-page">
    <header class="rp-header">
      <img class="rp-brand" :src="brandIcon" alt="" />
      <h1>Portal Rekrutmen</h1>
      <p>Masukkan NIK untuk melihat langkah rekrutmen Anda.</p>
    </header>

    <form class="rp-check" @submit.prevent="check">
      <label class="rp-label" for="rp-nik">NIK (16 digit)</label>
      <input
        id="rp-nik"
        class="rp-input"
        type="text"
        inputmode="numeric"
        autocomplete="off"
        maxlength="16"
        aria-label="NIK 16 digit"
        placeholder="16 digit angka"
        :value="nik"
        @input="onNik"
      />

      <button class="rp-button" type="submit" :disabled="checking">
        {{ checking ? 'Mengecek…' : 'Cek' }}
      </button>
      <p v-if="error" class="rp-error" role="alert">{{ error }}</p>
    </form>

    <section v-if="summary" class="rp-greeting" aria-live="polite">
      <p class="rp-hello">Halo, {{ summary.nama_masked || 'Peserta' }}</p>
      <p class="rp-branch">{{ summary.branch_name || summary.branch_code }}</p>
      <p class="rp-next">Langkah berikutnya: {{ summary.next_action }}</p>
    </section>

    <section class="rp-cards" aria-label="Langkah rekrutmen">
      <component
        v-for="(step, index) in STEPS"
        :key="step.type"
        :is="cardTag(step)"
        class="rp-card"
        :class="{ 'rp-card--locked': isLocked(step), 'rp-card--done': isDone(step) }"
        :data-step="step.type"
        :data-locked="isLocked(step) ? 'true' : 'false'"
        :data-status="stepStatus(step)"
        :aria-disabled="isLocked(step) ? 'true' : undefined"
        v-bind="cardAttrs(step)"
        @click="onCardClick(step)"
      >
        <span class="rp-step-no">{{ index + 1 }}</span>
        <h2 class="rp-card-title">{{ step.label }}</h2>
        <p class="rp-card-desc">{{ step.desc }}</p>
        <p v-if="isLocked(step)" class="rp-lock-hint">lengkapi CV Online dulu</p>
        <p v-else-if="isDone(step)" class="rp-open">Selesai — boleh dibuka kembali</p>
        <p v-else-if="tkdCardOpen(step)" class="rp-open">Buka tes</p>
        <p v-else class="rp-open">Buka langkah</p>
      </component>
    </section>

    <RecruitmentTkdPanel
      v-if="tkdOpen"
      :token="branchToken"
      :session="sessionToken"
      @close="tkdOpen = false"
    />
  </main>
</template>

<style scoped>
.rp-page {
  max-width: 720px;
  margin: 0 auto;
  padding: 24px 16px 48px;
  font-family: system-ui, -apple-system, sans-serif;
  color: #1f2937;
}
.rp-header { text-align: center; margin-bottom: 24px; }
.rp-brand { width: 56px; height: 56px; }
.rp-header h1 { font-size: 1.5rem; margin: 8px 0; }
.rp-header p { color: #6b7280; margin: 0; }
.rp-check {
  display: grid;
  gap: 8px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 24px;
}
.rp-label { font-weight: 600; font-size: 0.9rem; }
.rp-input {
  width: 100%;
  padding: 12px;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  font-size: 1rem;
  box-sizing: border-box;
}
.rp-button {
  padding: 12px 20px;
  border: 0;
  border-radius: 8px;
  background: #1d4ed8;
  color: #fff;
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
}
.rp-button:disabled { opacity: 0.6; cursor: default; }
.rp-error { color: #b91c1c; margin: 4px 0 0; font-size: 0.9rem; }
.rp-greeting { margin-bottom: 20px; padding: 16px; border-left: 3px solid #1d4ed8; background: #f8fafc; }
.rp-hello { font-size: 1.1rem; font-weight: 600; margin: 0; }
.rp-branch { color: #6b7280; margin: 4px 0; }
.rp-next { margin: 8px 0 0; color: #1d4ed8; font-weight: 600; }
.rp-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 12px;
}
.rp-card {
  display: block;
  padding: 16px;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  background: #fff;
  overflow: hidden;
  text-decoration: none;
  color: inherit;
  min-height: 140px;
  box-sizing: border-box;
  width: 100%;
  text-align: left;
  font: inherit;
  cursor: pointer;
}
.rp-card--locked { background: #f9fafb; border-color: #e5e7eb; opacity: 0.65; }
.rp-card--done { opacity: 0.78; }
.rp-step-no {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #dbeafe;
  color: #1d4ed8;
  font-weight: 700;
}
.rp-card-title { font-size: 1.05rem; margin: 12px 0 4px; }
.rp-card-desc { color: #6b7280; font-size: 0.85rem; margin: 0 0 12px; }
.rp-lock-hint { color: #6b7280; font-size: 0.85rem; margin: 0; }
.rp-open { color: #1d4ed8; font-size: 0.85rem; margin: 0; font-weight: 600; }
</style>
