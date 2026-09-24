import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { useRealtimeStore } from './stores/realtime'
import './styles/main.css'

// v2.43.3 — pulih otomatis dari chunk-lama setelah deploy: bila import
// dinamis gagal (asset hash lama sudah dihapus di server), SW mengembalikan
// error bersih dan halaman di-reload SEKALI untuk mengambil shell baru.
// Tanpa ini user terjebak error MIME sampai refresh manual.
// Didataftarkan SEBELUM router dipasang agar error navigasi awal ikut tertangkap.
const CHUNK_RELOAD_KEY = 'bpf-chunk-reload'
router.onError((err, to) => {
  const msg = String(err?.message || err || '')
  const isChunkErr = /Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module/i.test(msg)
  if (import.meta.env.PROD && isChunkErr && !sessionStorage.getItem(CHUNK_RELOAD_KEY)) {
    sessionStorage.setItem(CHUNK_RELOAD_KEY, String(Date.now()))
    window.location.replace((to && to.fullPath) ? to.fullPath : window.location.pathname)
    return
  }
  sessionStorage.removeItem(CHUNK_RELOAD_KEY)
  console.error('[router]', err)
})

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
app.use(router)

// Error boundary global (v2.21): kesalahan tak tertangkap di komponen tidak
// lagi berakhir layar kosong — tampilkan toast ringkas + log ke console.
app.config.errorHandler = (err, instance, info) => {
  console.error('[error-boundary]', info, err)
  try {
    useRealtimeStore(pinia).push(`⚠️ ${err?.message || 'Terjadi kesalahan'}`, 'error')
  } catch { /* store belum siap — abaikan */ }
}

app.mount('#app')

// PWA: daftarkan service worker khusus SPA (scope /app/) saat produksi
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/app/sw.js', { scope: '/app/' }).catch(() => {})
  })
}
