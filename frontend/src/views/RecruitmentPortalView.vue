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

const brandLogo = '/static/bpf-logo.png'

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
const BULAN = [
  'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli',
  'Agustus', 'September', 'Oktober', 'November', 'Desember',
]

function greetingName() {
  return (summary.value?.nama_masked || '').replace(/\.$/, '')
}

// Tanggal ISO dari server (YYYY-MM-DD) → "12 Oktober 2026".
function tanggalPanjang(value) {
  const cocok = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(value || ''))
  if (!cocok) return ''
  const bulan = BULAN[Number(cocok[2]) - 1]
  if (!bulan) return ''
  return `${Number(cocok[3])} ${bulan} ${cocok[1]}`
}

function daftarCabang(names) {
  const bersih = (names || []).filter((n) => typeof n === 'string' && n.trim())
  if (bersih.length <= 1) return bersih[0] || ''
  if (bersih.length === 2) return `${bersih[0]} dan ${bersih[1]}`
  return `${bersih.slice(0, -1).join(', ')}, dan ${bersih[bersih.length - 1]}`
}

// Informasi saja: tidak pernah mengubah status kartu atau tombol lanjut.
function riwayatText() {
  const info = summary.value?.branch_history
  if (!info) return ''
  const jumlah = Number(info.other_branch_count) || 0
  if (jumlah < 1) return ''
  const nama = (info.branch_names || [])
    .filter((n) => typeof n === 'string' && n.trim())
  const sisa = Math.max(0, jumlah - nama.length)
  const tanggal = tanggalPanjang(info.first_seen_at)
  const lanjut = 'Anda tetap dapat melanjutkan proses rekrutmen di cabang ini.'
  if (jumlah === 1) {
    const di = nama[0] || 'cabang lain'
    return `Data Anda pernah tercatat di ${di}${tanggal ? ` pada ${tanggal}` : ''}. ${lanjut}`
  }
  const daftar = [...nama]
  if (sisa > 0) daftar.push(`${sisa} cabang lain`)
  const rincian = daftar.length ? `, yaitu ${daftarCabang(daftar)}` : ''
  return `Data Anda pernah tercatat di ${jumlah} cabang lain${rincian}.` +
    (tanggal ? ` Pertama tercatat pada ${tanggal}.` : '') + ` ${lanjut}`
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

function isNext(step) {
  return !isDone(step) && summary.value?.next_action === step.type
}

function doneCount() {
  return STEPS.filter((step) => isDone(step)).length
}

function statusText(step) {
  if (isDone(step)) return 'Selesai'
  if (isLocked(step)) return 'Terkunci'
  if (isNext(step)) return 'Berikutnya'
  return 'Belum'
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
    // Token ikut dikirim agar server tahu cabang portal yang sedang dibuka;
    // tanpa token, info riwayat cabang lain sengaja tidak dihitung.
    const params = { nik: nik.value }
    if (branchToken) params.token = branchToken
    const result = await api('/api/recruitment/lookup', { params })
    known.value = Boolean(result && result.known === true)
    const riwayat = result?.branch_history
    summary.value = {
      nama_masked: result?.nama_masked || '',
      stages: result?.stages || [],
      next_action: result?.next_action || '',
      // Ambil field yang dikenal saja; kode cabang/NIK/case_id tidak pernah
      // disimpan walaupun ikut terkirim di respons.
      branch_history: riwayat && typeof riwayat === 'object'
        ? {
            other_branch_count: Number(riwayat.other_branch_count) || 0,
            first_seen_at: typeof riwayat.first_seen_at === 'string'
              ? riwayat.first_seen_at : '',
            branch_names: Array.isArray(riwayat.branch_names)
              ? riwayat.branch_names.filter((n) => typeof n === 'string').slice(0, 5)
              : [],
          }
        : null,
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
    <div class="rp-shell">
      <header class="rp-brandbar">
        <img class="rp-logo" :src="brandLogo" alt="" />
        <div class="rp-brand-text">
          <b>PT Bestprofit Futures</b>
          <span>Portal Rekrutmen</span>
        </div>
        <span class="rp-brand-tag">Situs Resmi</span>
      </header>

      <section class="rp-hero">
        <p class="rp-eyebrow">Rekrutmen Karyawan</p>
        <h1>Pantau proses rekrutmen Anda</h1>
        <p class="rp-lede">
          Masukkan NIK untuk melihat rangkuman dan melanjutkan proses rekrutmen
          di cabang Anda.
        </p>
        <ul class="rp-trust">
          <li>
            <svg class="rp-icon" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M12 3l7 3v6c0 4.2-2.9 7.6-7 9-4.1-1.4-7-4.8-7-9V6l7-3z" />
              <path d="M9 12l2 2 4-4" />
            </svg>
            <span>Data pribadi dilindungi</span>
          </li>
          <li>
            <svg class="rp-icon" viewBox="0 0 24 24" aria-hidden="true">
              <rect x="4" y="10" width="16" height="10" rx="2" />
              <path d="M8 10V7a4 4 0 0 1 8 0v3" />
            </svg>
            <span>Cukup NIK 16 digit</span>
          </li>
        </ul>
      </section>

      <form class="rp-check" @submit.prevent="check">
        <label class="rp-label" for="rp-nik">NIK (16 digit)</label>
        <div class="rp-field">
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
        </div>
        <p v-if="error" class="rp-error" role="alert">{{ error }}</p>
        <p class="rp-privacy">
          <svg class="rp-icon" viewBox="0 0 24 24" aria-hidden="true">
            <rect x="4" y="10" width="16" height="10" rx="2" />
            <path d="M8 10V7a4 4 0 0 1 8 0v3" />
          </svg>
          <span>NIK hanya dipakai untuk mencocokkan data Anda. NIK lengkap tidak ditampilkan di halaman ini.</span>
        </p>
      </form>

      <section v-if="summary && known && summary.nama_masked" class="rp-greeting" aria-live="polite">
        <p class="rp-hello">Data Anda sudah cocok. Halo, <b>{{ greetingName() }}</b>. Berikut rangkuman rekrutmen di cabang ini.</p>
        <p v-if="summary.next_action && summary.next_action !== 'DONE'" class="rp-next">
          <span class="rp-next-label">Langkah berikutnya:</span> {{ STEP_LABELS[summary.next_action] || summary.next_action }}. Ikuti jadwal dari cabang.
        </p>
        <p v-else class="rp-next">Semua tahap sudah tercatat. Hubungi cabang bila perlu cetak ulang kartu atau koreksi data.</p>
      </section>

      <section v-if="riwayatText()" class="rp-history" data-history role="status">
        <svg class="rp-icon" viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="12" cy="12" r="9" />
          <path d="M12 8h.01M11 12h1v4h1" />
        </svg>
        <p>{{ riwayatText() }}</p>
      </section>

      <div class="rp-steps-head">
        <h2>Tahap rekrutmen</h2>
        <span>{{ summary && known ? `${doneCount()} dari 4 tahap selesai` : '4 tahap' }}</span>
      </div>
      <section class="rp-steps" aria-label="Langkah rekrutmen">
        <div
          v-for="(step, index) in STEPS"
          :key="step.type"
          class="rp-card"
          :class="{ 'rp-card--locked': isLocked(step), 'rp-card--done': isDone(step), 'rp-card--next': isNext(step) }"
          :data-step="step.type"
          :data-locked="isLocked(step) ? 'true' : 'false'"
          :data-status="stageInfo(step.type).status || 'BELUM'"
        >
          <component
            :is="cardTag(step)"
            class="rp-card-main"
            :aria-disabled="isLocked(step) ? 'true' : undefined"
            :aria-current="isNext(step) ? 'step' : undefined"
            v-bind="cardAttrs(step)"
            @click="onCardClick(step)"
          >
            <span
              class="rp-node"
              :class="{ 'rp-node--done': isDone(step), 'rp-node--locked': isLocked(step) }"
              aria-hidden="true"
            >{{ isDone(step) ? '✓' : index + 1 }}</span>
            <span class="rp-card-body">
              <span class="rp-card-head">
                <span class="rp-card-title">{{ step.label }}</span>
                <span
                  class="rp-status"
                  :class="{ 'rp-status--done': isDone(step), 'rp-status--next': isNext(step), 'rp-status--locked': isLocked(step) }"
                >{{ statusText(step) }}</span>
              </span>
              <span class="rp-card-desc">{{ step.desc }}</span>
              <span class="rp-card-line">
                <span class="rp-summary">{{ isLocked(step) ? 'Lengkapi CV Online terlebih dahulu.' : summaryText(step) }}</span>
                <span v-if="!isLocked(step) && !isDone(step)" class="rp-action">Buka <span aria-hidden="true">→</span></span>
              </span>
            </span>
          </component>
          <details v-if="stepNote(step)" class="rp-details" data-expand>
            <summary>Lihat keterangan</summary>
            <p class="rp-full-note">{{ stepNote(step) }}</p>
          </details>
        </div>
      </section>

      <RecruitmentTkdPanel
        v-if="tkdOpen"
        :token="branchToken"
        :nik="tkdNik"
        @close="tkdOpen = false"
      />
    </div>
  </main>
</template>

<style scoped>
.rp-page {
  --rp-ink: #0b1f3a;
  --rp-ink-2: #334155;
  --rp-muted: #5c6b7f;
  --rp-bg: #f4f6f8;
  --rp-paper: #ffffff;
  --rp-line: #dce3ea;
  --rp-accent: #b3122e;
  --rp-accent-soft: #fbeaec;
  --rp-success: #166534;
  --rp-focus: #1e4e8c;

  min-height: 100vh;
  background: var(--rp-bg);
  color: var(--rp-ink-2);
  font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
  font-size: 16px;
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}
.rp-shell {
  max-width: 760px;
  margin: 0 auto;
  padding: 0 24px 64px;
}

/* Bilah merek — putih, garis rambut, logo resmi. */
.rp-brandbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 18px 0;
  border-bottom: 1px solid var(--rp-line);
}
.rp-logo { height: 30px; width: auto; object-fit: contain; }
.rp-brand-text { display: flex; flex-direction: column; line-height: 1.25; }
.rp-brand-text b {
  color: var(--rp-ink);
  font-size: 0.95rem;
  font-weight: 650;
  letter-spacing: -0.01em;
}
.rp-brand-text span { color: var(--rp-muted); font-size: 0.75rem; }
.rp-brand-tag {
  margin-left: auto;
  color: var(--rp-muted);
  font-size: 0.68rem;
  font-weight: 600;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  white-space: nowrap;
}

/* Kepala halaman */
.rp-hero { padding: 40px 0 28px; }
.rp-eyebrow {
  margin: 0;
  color: var(--rp-muted);
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}
.rp-hero h1 {
  margin: 8px 0 0;
  color: var(--rp-ink);
  font-size: 1.9rem;
  font-weight: 650;
  line-height: 1.2;
  letter-spacing: -0.02em;
}
.rp-lede {
  margin: 10px 0 0;
  max-width: 54ch;
  color: var(--rp-ink-2);
  font-size: 0.95rem;
}
.rp-trust {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 20px;
  margin: 18px 0 0;
  padding: 0;
  list-style: none;
}
.rp-trust li {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--rp-ink-2);
  font-size: 0.8rem;
  font-weight: 500;
}
.rp-icon {
  flex: none;
  width: 17px;
  height: 17px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.7;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.rp-trust .rp-icon { color: var(--rp-success); }

/* Panel pemeriksaan NIK */
.rp-check {
  display: grid;
  gap: 10px;
  padding: 22px;
  background: var(--rp-paper);
  border: 1px solid var(--rp-line);
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(11, 31, 58, 0.04);
}
.rp-label {
  color: var(--rp-ink);
  font-size: 0.8rem;
  font-weight: 650;
  letter-spacing: 0.01em;
}
.rp-field { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 10px; }
.rp-input {
  width: 100%;
  min-height: 48px;
  padding: 0 14px;
  border: 1px solid #c7d1dc;
  border-radius: 6px;
  background: #fff;
  color: var(--rp-ink);
  font: inherit;
  font-size: 1rem;
  letter-spacing: 0.04em;
  transition: border-color 160ms ease-out, box-shadow 160ms ease-out;
}
.rp-input::placeholder { color: #6b7a8c; letter-spacing: 0; }
.rp-input:focus {
  outline: none;
  border-color: var(--rp-focus);
  box-shadow: 0 0 0 3px rgba(30, 78, 140, 0.16);
}
.rp-button {
  min-height: 48px;
  padding: 0 24px;
  border: 0;
  border-radius: 6px;
  background: var(--rp-ink);
  color: #fff;
  font: inherit;
  font-size: 0.95rem;
  font-weight: 600;
  white-space: nowrap;
  cursor: pointer;
  transition: background-color 160ms ease-out;
}
.rp-button:hover:not(:disabled) { background: #132c4e; }
.rp-button:disabled { opacity: 0.6; cursor: default; }
.rp-button:focus-visible,
.rp-card:focus-visible,
.rp-details summary:focus-visible {
  outline: 2px solid var(--rp-focus);
  outline-offset: 2px;
}
.rp-error { margin: 0; color: #a4161a; font-size: 0.85rem; font-weight: 500; }
.rp-privacy {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  margin: 0;
  color: var(--rp-muted);
  font-size: 0.78rem;
  line-height: 1.5;
}
.rp-privacy .rp-icon { width: 14px; height: 14px; margin-top: 2px; }

/* Ringkasan setelah NIK dikenal */
.rp-greeting {
  margin-top: 20px;
  padding: 18px 20px;
  background: var(--rp-paper);
  border: 1px solid var(--rp-line);
  border-radius: 8px;
}
.rp-hello { margin: 0; color: var(--rp-ink-2); font-size: 0.9rem; }
.rp-hello b { color: var(--rp-ink); }
.rp-next {
  margin: 12px 0 0;
  padding: 10px 14px;
  background: var(--rp-accent-soft);
  border-left: 3px solid var(--rp-accent);
  border-radius: 0 4px 4px 0;
  color: var(--rp-ink);
  font-size: 0.88rem;
  font-weight: 500;
}
.rp-next-label { font-weight: 700; }

/* Info riwayat cabang lain — tenang, informatif, tidak menghalangi. */
.rp-history {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  margin-top: 12px;
  padding: 13px 16px;
  background: #f2f6fc;
  border: 1px solid #cfdcee;
  border-left: 3px solid var(--rp-focus);
  border-radius: 0 6px 6px 0;
}
.rp-history .rp-icon {
  margin-top: 3px;
  color: var(--rp-focus);
}
.rp-history p {
  margin: 0;
  color: var(--rp-ink-2);
  font-size: 0.86rem;
}

/* Daftar tahap vertikal */
.rp-steps-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin: 30px 0 12px;
}
.rp-steps-head h2 {
  margin: 0;
  color: var(--rp-ink);
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}
.rp-steps-head span { color: var(--rp-muted); font-size: 0.75rem; }
.rp-steps { display: grid; gap: 10px; }

.rp-card {
  position: relative;
  width: 100%;
  background: var(--rp-paper);
  border: 1px solid var(--rp-line);
  border-radius: 8px;
  transition: border-color 160ms ease-out, background-color 160ms ease-out,
    box-shadow 160ms ease-out;
}
/* Garis timeline menyambung simpul satu ke simpul berikutnya. */
.rp-card:not(:last-child)::before {
  content: '';
  position: absolute;
  left: 33px;
  top: 48px;
  bottom: -11px;
  width: 1px;
  background: var(--rp-line);
}
.rp-card--done:not(:last-child)::before { background: #bfdccb; }
.rp-card:hover { border-color: #b7c4d2; box-shadow: 0 2px 6px rgba(11, 31, 58, 0.05); }
.rp-card--next {
  background: var(--rp-accent-soft);
  border-color: #e6c4ca;
  box-shadow: inset 3px 0 0 var(--rp-accent);
}
.rp-card--next:hover { border-color: var(--rp-accent); }
.rp-card--locked { background: #f7f9fb; }
.rp-card--locked:hover { border-color: var(--rp-line); box-shadow: none; }
.rp-card--done { background: #fbfcfd; }

.rp-card-main {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  width: 100%;
  margin: 0;
  padding: 16px 18px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  text-decoration: none;
  cursor: pointer;
}
.rp-card-main:focus-visible { outline: 2px solid var(--rp-focus); outline-offset: -2px; }
.rp-card--locked .rp-card-main { cursor: not-allowed; }

.rp-node {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border: 1px solid #d6dfe9;
  border-radius: 50%;
  background: #eef2f7;
  color: var(--rp-ink-2);
  font-size: 0.8rem;
  font-weight: 700;
}
.rp-node--done { background: #e8f3ec; border-color: #bfdccb; color: var(--rp-success); }
.rp-node--locked { color: #5c6b7f; }

.rp-card-body { display: flex; flex: 1; flex-direction: column; gap: 3px; min-width: 0; }
.rp-card-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.rp-card-title {
  color: var(--rp-ink);
  font-size: 1rem;
  font-weight: 600;
  letter-spacing: -0.01em;
}
.rp-status {
  margin-left: auto;
  min-width: 88px;
  padding: 2px 9px;
  border-radius: 999px;
  background: #eef2f7;
  color: #4a5a6d;
  font-size: 0.7rem;
  font-weight: 600;
  text-align: center;
  white-space: nowrap;
}
.rp-status--done { background: #e8f3ec; color: var(--rp-success); }
.rp-status--next {
  background: #fff;
  color: var(--rp-accent);
  box-shadow: inset 0 0 0 1px #e6c4ca;
}
.rp-status--locked { color: #6b7a8c; }
.rp-card-desc { color: var(--rp-muted); font-size: 0.8rem; line-height: 1.45; }
.rp-card-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.rp-summary {
  flex: 1;
  min-width: 0;
  color: var(--rp-ink-2);
  font-size: 0.8rem;
  line-height: 1.45;
}
.rp-card--done .rp-summary { color: #4a5a6d; }
.rp-action {
  color: var(--rp-ink);
  font-size: 0.8rem;
  font-weight: 600;
  white-space: nowrap;
}
.rp-card--next .rp-action { color: var(--rp-accent); }

.rp-details {
  margin: 0;
  padding: 0 18px 8px 62px;
  border-top: 1px solid var(--rp-line);
}
.rp-details summary {
  display: inline-flex;
  align-items: center;
  min-height: 40px;
  color: var(--rp-ink-2);
  font-size: 0.78rem;
  font-weight: 600;
  cursor: pointer;
}
.rp-details summary:hover { color: var(--rp-ink); }
.rp-full-note {
  margin: 0 0 8px;
  color: var(--rp-muted);
  font-size: 0.78rem;
  line-height: 1.55;
}

@media (max-width: 639px) {
  .rp-shell { padding: 0 16px calc(40px + env(safe-area-inset-bottom)); }
  .rp-brandbar { padding: 14px 0; }
  .rp-brand-tag { display: none; }
  .rp-hero { padding: 28px 0 22px; }
  .rp-hero h1 { font-size: 1.55rem; }
  .rp-lede { font-size: 0.9rem; }
  .rp-check { padding: 16px; }
  .rp-field { grid-template-columns: 1fr; }
  .rp-greeting { padding: 16px; }
  .rp-card-main { padding: 14px; gap: 12px; }
  .rp-card:not(:last-child)::before { left: 28px; top: 44px; }
  .rp-node { width: 28px; height: 28px; }
  .rp-card-desc { display: none; }
  .rp-details { padding: 0 14px 6px 54px; }
}

@media (max-width: 380px) {
  .rp-brand-text b { font-size: 0.85rem; }
  .rp-hero h1 { font-size: 1.4rem; }
}

@media (prefers-reduced-motion: reduce) {
  .rp-card, .rp-input, .rp-button { transition: none; }
}
</style>
