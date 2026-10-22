<script setup>
import { nextTick, ref } from 'vue'
import Modal from './Modal.vue'

const state = ref(null)
const inputRef = ref(null)
let resolver = null

function open(message, opts = {}) {
  return new Promise((resolve) => {
    resolver = resolve
    state.value = {
      message,
      title: opts.title || 'Konfirmasi',
      confirmText: opts.confirmText || 'Ya, lanjutkan',
      cancelText: opts.cancelText || 'Batal',
      danger: !!opts.danger,
      input: !!opts.input,
      required: opts.required !== false,
      value: opts.value || '',
      placeholder: opts.placeholder || '',
      error: '',
    }
    if (opts.input) nextTick(() => inputRef.value?.focus())
  })
}

function close(ok) {
  const s = state.value
  if (!s) return
  if (ok && s.input && s.required && !s.value.trim()) {
    s.error = 'Kolom ini wajib diisi.'
    return
  }
  const r = resolver
  state.value = null
  resolver = null
  if (!ok) return r?.(s.input ? null : false)
  r?.(s.input ? s.value.trim() : true)
}

defineExpose({ open })
</script>

<template>
  <Modal v-if="state" :title="state.title" @close="close(false)">
    <p style="margin-top:0;white-space:pre-line;font-size:13px;">{{ state.message }}</p>
    <textarea
      v-if="state.input"
      ref="inputRef"
      v-model="state.value"
      class="input"
      rows="3"
      :placeholder="state.placeholder"
    ></textarea>
    <p v-if="state.error" class="alert alert-error" style="margin:8px 0 0;padding:6px 10px;">{{ state.error }}</p>
    <div class="row" style="justify-content:flex-end;gap:8px;margin-top:16px;">
      <button class="btn" @click="close(false)">{{ state.cancelText }}</button>
      <button class="btn" :class="state.danger ? 'btn-danger' : 'btn-primary'" @click="close(true)">{{ state.confirmText }}</button>
    </div>
  </Modal>
</template>
