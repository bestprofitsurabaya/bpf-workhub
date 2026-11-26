<script setup>
/**
 * Absensi Training portal (2 hari).
 *
 * Identitas diverifikasi ke server (NIK + tanggal lahir) sebelum hari dipilih.
 * Hari 2 sengaja dikunci sampai Hari 1 tercatat; server juga menolaknya, jadi
 * UI ini hanya kenyamanan, bukan satu-satunya penjaga.
 */
import { computed, ref } from 'vue'
import { api } from '../api'

const brandIcon = '/static/icon-192.png'
const params = new URLSearchParams(window.location.search)
const token = (params.get('token') || params.get('t') || '').trim()

const nik = ref('')
const dob = ref('')
const status = ref(null)
const day = ref(1)
const consent = ref(false)
const checking = ref(false)
const saving = ref(false)
const error = ref('')
const success = ref('')

const day1 = computed(() => status.value?.days?.[1] || null)
const day2 = computed(() => status.value?.days?.[2] || null)
const day2Locked = computed(() => !day1.value)
const nama = computed(() => status.value?.nama || '')

function onNik(event) {
  nik.value = String(event.target.value || '').replace(/\D/g, '').slice(0, 16)
}

function validDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const parsed = new Date(`${value}T00:00:00Z`)
  return !Number.isNaN(parsed.getTime())
    && parsed.toISOString().slice(0, 10) === value
}

function formatTime(value) {
  if (!value) return ''
  return String(value).slice(0, 16).replace('T', ' ')
}

async function checkStatus() {
  error.value = ''
  success.value = ''
  status.value = null
  if (nik.value.length !== 16) {
    error.value = 'NIK wajib 16 digit angka.'
    return
  }
  if (!validDate(dob.value)) {
    error.value = 'Tanggal lahir wajib diisi.'
    return
  }
  checking.value = true
  try {
    const result = await api('/api/recruitment/training/status', {
      params: { token, nik: nik.value, dob: dob.value },
    })
    status.value = result.data || null
    day.value = status.value?.next_day === 2 ? 2 : 1
  } catch (e) {
    error.value = e?.message || 'Pengecekan gagal. Coba lagi sebentar.'
  } finally {
    checking.value = false
  }
}

async function submit() {
  error.value = ''
  success.value = ''
  if (day2Locked.value && Number(day.value) === 2) {
    error.value = 'Hari 2 terbuka setelah absensi Hari 1 tercatat.'
    return
  }
  if (!consent.value) {
    error.value = 'Centang pernyataan kebenaran data dulu.'
    return
  }
  saving.value = true
  try {
    const result = await api('/api/recruitment/training/attendance', {
      method: 'POST',
      body: {
        token,
        nik: nik.value,
        dob: dob.value,
        day: Number(day.value),
        consent: true,
      },
    })
    const data = result.data || {}
    status.value = {
      nama: nama.value,
      days: data.days || status.value?.days || {},
      next_day: null,
    }
    success.value = `Absensi Hari ${data.day} tercatat`
    consent.value = false
  } catch (e) {
    error.value = e?.message || 'Absensi gagal disimpan. Coba lagi.'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <main class="rp-page">
    <header class="rp-header">
      <img class="rp-brand" :src="brandIcon" alt="" />
      <h1>Absensi Training</h1>
      <p>Catat kehadiran Hari 1 dan Hari 2 training rekrutmen.</p>
    </header>

    <form class="rp-check" @submit.prevent="checkStatus">
      <label class="rp-label" for="tr-nik">NIK (16 digit)</label>
      <input
        id="tr-nik"
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

      <label class="rp-label" for="tr-dob">Tanggal lahir</label>
      <input
        id="tr-dob"
        class="rp-input"
        type="date"
        aria-label="Tanggal lahir"
        v-model="dob"
      />

      <button class="rp-button" type="submit" :disabled="checking">
        {{ checking ? 'Mengecek…' : 'Cek Status' }}
      </button>
      <p v-if="error" class="rp-error" role="alert">{{ error }}</p>
    </form>

    <section v-if="status" class="rp-status" aria-label="Status training">
      <h2 class="rp-card-title">{{ nama }}</h2>
      <ul class="rp-days">
        <li>
          <span>Hari 1</span>
          <strong v-if="day1">{{ formatTime(day1.attended_at) }}</strong>
          <em v-else>belum tercatat</em>
        </li>
        <li>
          <span>Hari 2</span>
          <strong v-if="day2">{{ formatTime(day2.attended_at) }}</strong>
          <em v-else>belum tercatat</em>
        </li>
      </ul>
      <p v-if="day1" class="rp-hint">Hari 1 sudah tercatat.</p>

      <p v-if="success" class="rp-success" role="status">{{ success }}</p>

      <form v-if="!day1 || !day2" class="rp-submit" @submit.prevent="submit">
        <fieldset class="rp-days-choice">
          <legend>Pilih hari yang dihadiri</legend>
          <label>
            <input v-model.number="day" type="radio" value="1" :disabled="!!day1" />
            Hari 1
          </label>
          <label>
            <input v-model.number="day" type="radio" value="2" :disabled="day2Locked" />
            Hari 2
          </label>
        </fieldset>
        <p v-if="day2Locked" class="rp-hint">
          Hari 2 terbuka setelah Hari 1 tercatat.
        </p>

        <label class="rp-consent">
          <input v-model="consent" type="checkbox" />
          Saya menyatakan benar menghadiri training pada hari yang dipilih.
        </label>

        <button class="rp-button" type="submit" :disabled="saving">
          {{ saving ? 'Menyimpan…' : 'Simpan Absensi' }}
        </button>
      </form>

      <a class="rp-back" :href="`/app/recruitment-portal?token=${encodeURIComponent(token)}`">
        ← Kembali ke portal
      </a>
    </section>

    <p class="rp-foot">
      Data hanya dipakai untuk proses rekrutmen PT Bestprofit Futures.
    </p>
  </main>
</template>

<style scoped>
.rp-page {
  max-width: 560px;
  margin: 0 auto;
  padding: 24px 16px 48px;
  font-family: system-ui, -apple-system, sans-serif;
  color: #1f2937;
}
.rp-header { text-align: center; margin-bottom: 20px; }
.rp-brand { width: 56px; height: 56px; }
.rp-header h1 { font-size: 1.4rem; margin: 8px 0; }
.rp-header p { color: #6b7280; margin: 0; font-size: 0.95rem; }
.rp-check, .rp-status {
  display: grid;
  gap: 8px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 20px;
}
.rp-label { font-weight: 600; font-size: 0.9rem; }
.rp-input {
  width: 100%;
  padding: 12px;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  font-size: 1rem;
}
.rp-button {
  width: 100%;
  padding: 12px;
  border: 0;
  border-radius: 8px;
  background: #1d4ed8;
  color: #fff;
  font-weight: 600;
  font-size: 1rem;
}
.rp-button:disabled { opacity: 0.6; }
.rp-error { color: #b91c1c; margin: 4px 0 0; font-size: 0.9rem; }
.rp-card-title { margin: 0; font-size: 1.05rem; }
.rp-days { list-style: none; margin: 8px 0; padding: 0; display: grid; gap: 6px; }
.rp-days li {
  display: flex; justify-content: space-between; gap: 12px;
  background: #f8fafc; border-radius: 8px; padding: 10px 12px;
}
.rp-days em { color: #9ca3af; font-style: normal; }
.rp-hint { color: #92400e; font-size: 0.85rem; margin: 0; }
.rp-success {
  background: #ecfdf5; color: #065f46; border: 1px solid #a7f3d0;
  border-radius: 8px; padding: 10px 12px; margin: 4px 0; font-weight: 600;
}
.rp-submit { display: grid; gap: 10px; margin-top: 4px; }
.rp-days-choice { border: 0; padding: 0; margin: 0; display: grid; gap: 6px; }
.rp-days-choice legend { font-weight: 600; font-size: 0.9rem; margin-bottom: 4px; }
.rp-days-choice label { display: flex; gap: 8px; align-items: center; }
.rp-consent { display: flex; gap: 8px; font-size: 0.88rem; line-height: 1.4; }
.rp-back { color: #1d4ed8; text-decoration: none; font-size: 0.9rem; }
.rp-foot { text-align: center; color: #9ca3af; font-size: 0.8rem; }
</style>
