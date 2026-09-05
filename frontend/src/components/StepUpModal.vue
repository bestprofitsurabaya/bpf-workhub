<script setup>
import { ref, watch } from 'vue'
import { useStepupStore } from '../stores/stepup'
import { useAuthStore } from '../stores/auth'

const stepup = useStepupStore()
const auth = useAuthStore()
const pin = ref('')

// Saat modal dibuka, reset input & error
watch(() => stepup.open, (open) => {
  if (open) { pin.value = ''; stepup.err = '' }
})

async function submit() {
  if (!pin.value.trim()) { stepup.err = 'PIN wajib diisi'; return }
  await stepup.submit(pin.value)
}
</script>

<template>
  <div v-if="stepup.open" class="modal-overlay" role="dialog" aria-modal="true" aria-label="Verifikasi PIN ulang">
    <div class="modal-box" style="max-width:380px;">
      <div class="row" style="justify-content:space-between;margin-bottom:10px;">
        <h3 style="margin:0;">🔐 Verifikasi PIN Ulang</h3>
      </div>
      <p class="muted" style="font-size:13px;margin:0 0 10px;">
        Aksi ini menggerakkan uang dan memerlukan konfirmasi identitas ulang
        (ISO/IEC 27001).
        <template v-if="stepup.label">Tindakan: <b>{{ stepup.label }}</b>.</template>
      </p>
      <p class="muted" style="font-size:12px;margin:0 0 8px;">
        Sebagai <b>{{ auth.meta?.label || auth.user?.user_name }}</b> — masukkan PIN Anda.
      </p>
      <input
        v-model="pin"
        type="password"
        inputmode="numeric"
        maxlength="6"
        class="inp"
        placeholder="PIN 6 digit"
        style="width:100%;text-align:center;font-size:18px;letter-spacing:6px;"
        :disabled="stepup.busy"
        @keyup.enter="submit"
        autocomplete="off"
      />
      <div v-if="stepup.err" class="alert alert-error" style="margin-top:8px;font-size:12px;">❌ {{ stepup.err }}</div>
      <div class="row" style="justify-content:flex-end;gap:8px;margin-top:12px;">
        <button class="btn" :disabled="stepup.busy" @click="stepup.cancel()">Batal</button>
        <button class="btn btn-primary" :disabled="stepup.busy || !pin.trim()" @click="submit">
          {{ stepup.busy ? 'Memverifikasi…' : '✔ Verifikasi' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.row { display: flex; }
.inp { padding: 10px 12px; border: 1px solid var(--border, #e2e8f0); border-radius: 8px; background: var(--card, #fff); color: var(--text, #0f172a); }
.muted { color: var(--muted, #64748b); }
.alert-error { padding: 8px 10px; border-radius: 8px; background: #fef2f2; border: 1px solid #fca5a5; color: #dc2626; }
</style>