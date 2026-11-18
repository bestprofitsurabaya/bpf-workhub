/**
 * Konteks cabang Admin Pusat (v2.114.0 — Fase 1 "Pusat").
 *
 * Admin Pusat selalu bekerja di satu cabang (session backend menentukan DB
 * operasional). Agar tidak ada aksi yang "nyasar" ke cabang yang salah, saat
 * Pusat membuka cabang lewat panel Pusat / switcher topbar, konteks itu
 * dicatat dan banner peringatan tampil sampai ia kembali ke Pusat.
 *
 * Disimpan di localStorage supaya bertahan saat halaman dimuat ulang —
 * banner tidak boleh hilang hanya karena reload.
 */
import { ref } from 'vue'

export const BRANCH_CTX_KEY = 'bpf_ho_branch_ctx'

function readStored() {
  try {
    const raw = localStorage.getItem(BRANCH_CTX_KEY)
    const parsed = raw ? JSON.parse(raw) : null
    return parsed && parsed.code ? parsed : null
  } catch {
    return null
  }
}

// Module-level ref: semua komponen melihat konteks yang sama.
const active = ref(readStored())

export function useBranchContext() {
  function enter(code, name) {
    if (!code) return
    active.value = { code: String(code).toUpperCase(), name: name || code }
    try { localStorage.setItem(BRANCH_CTX_KEY, JSON.stringify(active.value)) } catch { /* privat mode */ }
  }

  function leave() {
    active.value = null
    try { localStorage.removeItem(BRANCH_CTX_KEY) } catch { /* privat mode */ }
  }

  return { active, enter, leave }
}

/** Khusus tes: paksa state dari localStorage (tanpa reload modul). */
export function _resetBranchContext() {
  active.value = readStored()
}
