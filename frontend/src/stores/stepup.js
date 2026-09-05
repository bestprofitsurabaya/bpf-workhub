import { defineStore } from 'pinia'
import { api } from '../api'

/**
 * Step-up authentication (ISO/IEC 27001 A.8.5) — modal PIN ulang untuk aksi
 * berisiko (approve/pay). Alur:
 *
 *   1. `require(actionFn)` mencoba aksi dulu. Bila server menjawab 428
 *      STEPUP_REQUIRED → buka modal PIN & simpan aksi yang tertunda.
 *   2. User memasukkan PIN → `submit(pin)` memanggil POST /api/step-up
 *      (username diambil dari sesi server, bukan body) → berhasil, aksi
 *      tertunda dijalankan ulang.
 *   3. `require` menyelesaikan promise sesuai hasil akhir (aksi sukses /
 *      gagal ulang), sehingga pemanggil bisa memuat ulang data & pesan.
 *
 * Grant bersifat waktu (default 10 menit) — aksi berisiko berikutnya dalam
 * masa berlaku tidak meminta PIN ulang.
 */
export const useStepupStore = defineStore('stepup', {
  state: () => ({
    open: false,
    label: '',
    busy: false,
    err: '',
    _action: null,
    _resolve: null,
    _reject: null,
  }),
  actions: {
    async require(actionFn, label = '') {
      try {
        return await actionFn()
      } catch (e) {
        if (e?.status === 428 && e?.data?.code === 'STEPUP_REQUIRED') {
          this.open = true
          this.label = label
          this.err = ''
          this._action = actionFn
          return await new Promise((resolve, reject) => {
            this._resolve = resolve
            this._reject = reject
          })
        }
        throw e
      }
    },
    async submit(pin) {
      if (!this._action) return
      this.busy = true
      this.err = ''
      try {
        await api('/api/step-up', { method: 'POST', body: { pin } })
      } catch (e) {
        this.err = e.message
        this.busy = false
        return // modal tetap terbuka — user bisa coba lagi
      }
      const fn = this._action
      this.open = false
      this.busy = false
      this._action = null
      try {
        const r = await fn()
        this._resolve?.(r)
      } catch (e) {
        this._reject?.(e)
      } finally {
        this._resolve = null
        this._reject = null
      }
    },
    cancel() {
      const resolve = this._resolve
      this.open = false
      this.busy = false
      this.err = ''
      this._action = null
      this._resolve = null
      this._reject = null
      // Batal bukan kegagalan — resolve kosong agar pemanggil tetap jalan
      resolve?.(undefined)
    },
  },
})