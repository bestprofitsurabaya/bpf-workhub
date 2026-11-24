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
    desc: 'Latihan dan absensi peserta.',
    href: '',
    future: true,
  },
  {
    type: 'TKD',
    label: 'Test Kemampuan Dasar',
    desc: 'Penilaian kemampuan dasar peserta.',
    href: '',
    future: true,
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
const dob = ref('')
const error = ref('')
const checking = ref(false)
const known = ref(false)

function onNik(event) {
  nik.value = String(event.target.value || '').replace(/\D/g, '').slice(0, 16)
}

function validDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const parsed = new Date(`${value}T00:00:00Z`)
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value
}

// Sebelum dikenal hanya CV yang bisa diisi; tiga kartu lain sengaja dikunci.
function isLocked(step) {
  return step.type !== 'CV' && !known.value
}

async function check() {
  error.value = ''
  if (nik.value.length !== 16) {
    error.value = 'NIK wajib 16 digit angka.'
    return
  }
  if (!validDate(dob.value)) {
    error.value = 'Tanggal lahir wajib berformat YYYY-MM-DD.'
    return
  }

  // Cek ulang dengan NIK lain tidak boleh mewarisi status kartu sebelumnya.
  known.value = false
  checking.value = true
  try {
    const result = await api('/api/recruitment/lookup', {
      params: { nik: nik.value, dob: dob.value },
    })
    // Hanya boolean yang dipakai. Field lain (bola-bali response) diabaikan
    // dan tidak pernah masuk ke state/render.
    known.value = Boolean(result && result.known === true)
    if (!known.value) {
      error.value = 'NIK belum dikenal. Lengkapi CV Online terlebih dahulu.'
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
      <p>Masukkan NIK dan tanggal lahir untuk melanjutkan proses rekrutmen.</p>
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

      <label class="rp-label" for="rp-dob">Tanggal lahir</label>
      <input
        id="rp-dob"
        class="rp-input"
        type="date"
        aria-label="Tanggal lahir"
        v-model="dob"
      />

      <button class="rp-button" type="submit" :disabled="checking">
        {{ checking ? 'Mengecek…' : 'Cek' }}
      </button>
      <p v-if="error" class="rp-error" role="alert">{{ error }}</p>
    </form>

    <section class="rp-cards" aria-label="Langkah rekrutmen">
      <component
        v-for="(step, index) in STEPS"
        :key="step.type"
        :is="step.href && !isLocked(step) ? 'a' : 'div'"
        class="rp-card"
        :class="{ 'rp-card--locked': isLocked(step) }"
        :data-step="step.type"
        :data-locked="isLocked(step) ? 'true' : 'false'"
        :aria-disabled="isLocked(step) ? 'true' : undefined"
        v-bind="step.href && !isLocked(step) ? { href: step.href } : {}"
      >
        <span class="rp-step-no">{{ index + 1 }}</span>
        <h2 class="rp-card-title">{{ step.label }}</h2>
        <p class="rp-card-desc">{{ step.desc }}</p>
        <p v-if="isLocked(step)" class="rp-lock-hint">lengkapi CV Online dulu</p>
        <p v-else-if="step.future" class="rp-soon">Segera tersedia</p>
        <p v-else class="rp-open">Buka langkah →</p>
      </component>
    </section>
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
</style>
