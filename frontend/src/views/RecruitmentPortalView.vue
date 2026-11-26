<script setup>
/**
 * Rilis A (Task 7) — portal satu tautan per cabang dengan empat kartu langkah.
 *
 * Token cabang diambil dari query (?token=..., alias ?t=...) dan diteruskan apa
 * adanya ke form publik. Endpoint lookup sengaja boolean-only: komponen ini
 * membaca SATU field (`known`) dan tidak pernah menyimpan/merender cabang,
 * tahap, atau data pribadi lain dari respons. Tidak ada POST di halaman ini —
 * lookup hanya pertanyaan "sudah dikenal atau belum", bukan pembuatan kasus.
 */
import { ref } from 'vue'
import { api } from '../api'
import RecruitmentTkdPanel from '../components/RecruitmentTkdPanel.vue'

const brandIcon = '/static/icon-192.png'

const linkParams = new URLSearchParams(window.location.search)
const branchToken = (linkParams.get('token') || linkParams.get('t') || '').trim()
const formHref = (path) => `/app/${path}?token=${encodeURIComponent(branchToken)}`

const STEPS = [
  {
    type: 'CV',
    label: 'CV Online',
    desc: 'Registrasi data diri, pendidikan, dan pengalaman.',
    href: formHref('cv-online-form'),
    future: false,
  },
  {
    type: 'TRAINING',
    label: 'Training Absensi',
    desc: 'Absensi Hari 1 dan Hari 2 training.',
    href: formHref('training-form'),
    future: false,
  },
  {
    type: 'TKD',
    label: 'Test Kemampuan Dasar',
    desc: 'Penilaian kemampuan dasar peserta.',
    href: '',
    future: false,
    action: 'tkd',
  },
  {
    type: 'FIRSTWORK',
    label: 'FirstWork Absensi',
    desc: 'Absensi peserta dan cetak kartu.',
    href: formHref('first-work-form'),
    future: false,
  },
]

const nik = ref('')
const error = ref('')
const checking = ref(false)
const known = ref(false)
const tkdOpen = ref(false)
const tkdNik = ref('')
const summary = ref(null)

const STEP_LABELS = {
  CV: 'CV Online',
  TRAINING: 'Training Absensi',
  TKD: 'Test Kemampuan Dasar',
  FIRSTWORK: 'FirstWork Absensi',
}
function greetingName() {
  return (summary.value?.nama_masked || '').replace(/\.$/, '')
}

function summaryText(step) {
  if (isDone(step)) {
    const time = stageInfo(step.type).completed_at || ''
    return time ? `Data tersimpan pada ${time}` : 'Data tersimpan.'
  }
  const note = stepNote(step)
  if (!note) return ''
  const first = note.split('.')[0]
  return first ? `${first}.` : note
}

function onNik(event) {
  nik.value = String(event.target.value || '').replace(/\D/g, '').slice(0, 16)
}

// Sebelum dikenal hanya CV yang bisa diisi; tiga kartu lain sengaja dikunci.
function isLocked(step) {
  return step.type !== 'CV' && !known.value
}

function stageInfo(type) {
  return (summary.value?.stages || []).find((s) => s.type === type) || {}
}

function isDone(step) {
  return stageInfo(step.type).status === 'SELESAI'
}

function stepNote(step) {
  const time = stageInfo(step.type).completed_at || ''
  if (isDone(step)) {
    const notes = {
      CV: `✓ Selesai — CV Online diterima ${time}. Data diri dan pendidikan Anda tersimpan. Tahap ini tidak perlu diulang.`,
      TRAINING: `✓ Selesai — Absensi training tercatat ${time}. Tahap ini tidak perlu diulang.`,
      TKD: `✓ Selesai — TKD tercatat ${time}. Bukti penilaian tersimpan; tidak perlu diulang.`,
      FIRSTWORK: `✓ Selesai — KTP dan kartu peserta sudah tercatat ${time}. Tahap ini tidak perlu diulang; hubungi cabang bila kartu perlu dicetak ulang.`,
    }
    return notes[step.type]
  }
  if (isLocked(step)) return ''
  const pending = {
    CV: 'Belum tercatat. Isi CV Online agar data Anda tersimpan.',
    TRAINING: 'Belum tercatat. Absensi training menunggu kehadiran Anda. Hari 2 dibuka setelah Hari 1 tercatat.',
    TKD: 'Belum tercatat. Tes kemampuan dasar tersedia setelah data Anda dikenali.',
    FIRSTWORK: 'Belum tercatat. Setelah CV tersedia, Anda bisa mengunggah KTP dan mencetak kartu peserta.',
  }
  return pending[step.type]
}

// TKD terbuka setelah lookup, tetapi bukan tautan: ia membuka panel ujian.
function tkdCardOpen(step) {
  return step.action === 'tkd' && !isLocked(step) && !isDone(step)
}

function cardTag(step) {
  if (isDone(step)) return 'div'
  if (tkdCardOpen(step)) return 'button'
  return step.href && !isLocked(step) ? 'a' : 'div'
}

function cardAttrs(step) {
  if (isDone(step)) return {}
  if (tkdCardOpen(step)) return { type: 'button' }
  return step.href && !isLocked(step) ? { href: step.href } : {}
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

  // Cek ulang dengan NIK lain tidak boleh mewarisi status kartu sebelumnya.
  known.value = false
  summary.value = null
  tkdOpen.value = false
  tkdNik.value = ''
  checking.value = true
  try {
    const result = await api('/api/recruitment/lookup', {
      params: { nik: nik.value },
    })
    known.value = Boolean(result && result.known === true)
    summary.value = {
      nama_masked: result?.nama_masked || '',
      stages: result?.stages || [],
      next_action: result?.next_action || '',
    }
    if (known.value) {
      tkdNik.value = nik.value
    }
    if (!known.value) {
      error.value = 'NIK ini belum kami temukan. Mulai dari CV Online agar data Anda tercatat.'
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
      <div class="rp-brand-line">
        <img class="rp-brand" :src="brandIcon" alt="" />
        <h1>Portal Rekrutmen</h1>
      </div>
      <p>Masukkan NIK untuk melihat rangkuman dan melanjutkan proses rekrutmen.</p>
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
        {{ checking ? 'Mengecek…' : 'Cek Status' }}
      </button>
      <p v-if="error" class="rp-error" role="alert">{{ error }}</p>
      <p class="rp-privacy">NIK hanya dipakai untuk mencocokkan data Anda. NIK lengkap tidak ditampilkan di halaman ini.</p>
    </form>

    <section v-if="summary && known && summary.nama_masked" class="rp-greeting" aria-live="polite">
      <p>Data Anda sudah cocok. Halo, {{ greetingName() }}. Berikut rangkuman rekrutmen di cabang ini.</p>
      <p v-if="summary.next_action && summary.next_action !== 'DONE'" class="rp-next">
        Langkah berikutnya: {{ STEP_LABELS[summary.next_action] || summary.next_action }}. Ikuti jadwal dari cabang.
      </p>
      <p v-else class="rp-next">Semua tahap sudah tercatat. Hubungi cabang bila perlu cetak ulang kartu atau koreksi data.</p>
    </section>

    <section class="rp-cards" aria-label="Langkah rekrutmen">
      <component
        v-for="(step, index) in STEPS"
        :key="step.type"
        :is="cardTag(step)"
        class="rp-card"
        :class="{ 'rp-card--locked': isLocked(step), 'rp-card--done': isDone(step), 'rp-card--next': summary?.next_action === step.type }"
        :data-step="step.type"
        :data-locked="isLocked(step) ? 'true' : 'false'"
        :data-status="stageInfo(step.type).status || 'BELUM'"
        :aria-disabled="isLocked(step) ? 'true' : undefined"
        v-bind="cardAttrs(step)"
        @click="onCardClick(step)"
      >
        <div class="rp-card-head">
          <span class="rp-step-no">{{ index + 1 }}</span>
          <h2 class="rp-card-title">{{ step.label }}</h2>
          <span class="rp-status" :class="{ 'rp-status--done': isDone(step) }">
            {{ isDone(step) ? '✓ Selesai' : 'Belum' }}
          </span>
        </div>
        <p class="rp-card-desc">{{ step.desc }}</p>
        <p v-if="isLocked(step)" class="rp-lock-hint">Lengkapi CV Online terlebih dahulu.</p>
        <template v-else>
          <p class="rp-summary">{{ summaryText(step) }}</p>
          <p v-if="!isDone(step)" class="rp-open">{{ tkdCardOpen(step) ? 'Buka tes →' : 'Buka langkah →' }}</p>
          <details v-if="stepNote(step)" class="rp-details" data-expand>
            <summary>Lihat keterangan</summary>
            <p class="rp-full-note">{{ stepNote(step) }}</p>
          </details>
        </template>
      </component>
    </section>

    <RecruitmentTkdPanel
      v-if="tkdOpen"
      :token="branchToken"
      :nik="tkdNik"
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
.rp-header { text-align: center; margin-bottom: 16px; }
.rp-brand-line { display: flex; align-items: center; justify-content: center; gap: 8px; }
.rp-brand { width: 32px; height: 32px; object-fit: contain; }
.rp-header h1 { font-size: 1.3rem; margin: 0; }
.rp-header p { color: #6b7280; margin: 4px 0 0; font-size: 0.85rem; }
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
.rp-privacy { color: #6b7280; font-size: 0.8rem; margin: 2px 0 0; }
.rp-greeting { margin-bottom: 20px; padding: 14px 16px; border-left: 3px solid #1d4ed8; background: #f8fafc; }
.rp-greeting p { margin: 0; font-size: 0.9rem; }
.rp-next { margin-top: 8px !important; color: #1d4ed8; font-weight: 600; }
.rp-card--done { opacity: 0.68; }
.rp-card--done .rp-status { background: #dcfce7; color: #166534; }
.rp-card--next { border-color: #1d4ed8; box-shadow: 0 0 0 1px #1d4ed8 inset; }
.rp-card-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.rp-status {
  margin-left: auto; padding: 2px 8px; border-radius: 999px;
  background: #f1f5f9; color: #475569; font-size: 0.75rem; font-weight: 600;
  white-space: nowrap;
}
.rp-summary { color: #374151; font-size: 0.85rem; margin: 8px 0 0; }
.rp-details { margin-top: 6px; }
.rp-details summary {
  min-height: 44px; display: flex; align-items: center;
  color: #1d4ed8; font-size: 0.85rem; font-weight: 600; cursor: pointer;
}
.rp-full-note { color: #374151; font-size: 0.82rem; margin: 0 0 8px; }
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
.rp-soon { color: #92400e; font-size: 0.85rem; margin: 0; }
.rp-open { color: #1d4ed8; font-size: 0.85rem; margin: 0; font-weight: 600; }

@media (max-width: 639px) {
  .rp-page { padding: 16px 12px calc(24px + env(safe-area-inset-bottom)); }
  .rp-check { margin-bottom: 16px; padding: 12px; }
  .rp-input, .rp-button { min-height: 44px; }
  .rp-cards { grid-template-columns: 1fr; gap: 8px; }
  .rp-card { padding: 12px; min-height: auto; }
  .rp-card-desc { display: none; }
  .rp-summary {
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .rp-full-note { white-space: normal; }
  .rp-details summary { min-height: 44px; padding: 8px 0; }
  .rp-step-no { width: 24px; height: 24px; font-size: 0.8rem; }
  .rp-card-title { margin: 0; font-size: 1rem; }
}
</style>
