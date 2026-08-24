<script setup>
import { ref, watch, onMounted } from 'vue'
import { api } from '../../api'
import { useDriverStore } from '../../stores/driverStore'

const store = useDriverStore()
const nopol = ref('')
const result = ref(null)
const loading = ref(false)

// Pre-fill nopol dari profile
watch(() => store.profile, (p) => { if (p && p.nopol && !nopol.value) nopol.value = p.nopol }, { immediate: true })
watch(() => nopol.value, () => { result.value = null })

async function check() {
  const n = nopol.value.trim().toUpperCase()
  if (!n) return
  loading.value = true
  result.value = null
  try {
    const d = await api('/api/get-feedback/' + encodeURIComponent(n))
    if (d?.status === 'success') {
      result.value = {
        performa: d.performa,
        avg: d.avg_km_per_liter,
        msg: d.msg,
        cls: d.performa === 'BOROS' ? 'badge-red' : d.performa === 'CUKUP' ? 'badge-amber' : 'badge-green',
      }
    } else {
      result.value = { error: d?.msg || 'Data tidak ditemukan' }
    }
  } catch (e) {
    result.value = { error: e.message || 'Data tidak ditemukan' }
  } finally { loading.value = false }
}
</script>

<template>
  <div class="tab-page">
    <h4 style="margin:0 0 8px;">📊 Rapor Performa</h4>
    <p class="muted" style="font-size:12px;">Cek efisiensi bahan bakar kendaraan Anda (rata-rata km/liter).</p>
    <div class="row" style="gap:8px;">
      <div class="field" style="flex:1;"><label>No. Polisi</label>
        <input class="input" v-model="nopol" placeholder="cth: L 1413 CBI" @keyup.enter="check" />
      </div>
      <button class="btn btn-primary" style="margin-top:18px;" :disabled="loading || !nopol.trim()" @click="check">
        {{ loading ? '⏳…' : '🔍 Cek' }}
      </button>
    </div>

    <div v-if="result" class="card" style="margin-top:12px;padding:14px;">
      <template v-if="result.error">
        <p class="muted" style="font-size:12px;">{{ result.error }}</p>
      </template>
      <template v-else>
        <div class="row" style="align-items:center;gap:10px;">
          <span class="badge" :class="result.cls" style="font-size:13px;">{{ result.performa }}</span>
          <b style="font-size:16px;">{{ result.avg }} KM/L</b>
        </div>
        <p class="muted" style="font-size:12px;margin-top:8px;">{{ result.msg }}</p>
      </template>
    </div>
  </div>
</template>
