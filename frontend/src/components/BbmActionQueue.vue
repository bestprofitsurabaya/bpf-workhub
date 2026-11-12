<script setup>
/**
 * Antrean "Perlu Tindakan" (v2.103.0 — Fase 3; v2.104.0 — baris & aksi).
 *
 * Menampilkan pekerjaan yang menua: klaim menunggu GA, dana di driver yang
 * belum LPJ, LPJ yang menunggu verifikasi, dan nilai BBM yang tidak cocok
 * dengan data SPBU.
 *
 * v2.104.0: antrean tidak lagi berhenti di "pindah tab". Setiap baris antrean
 * bisa langsung ditindak dari sini — dengan satu syarat: aksinya memakai
 * endpoint + step-up PIN yang sudah ada (tidak ada jalur uang baru), jadi
 * peran tetap menentukan apa yang boleh ditampilkan:
 *   - GA/Admin  → verifikasi klaim, approve/tolak LPJ
 *   - Finance   → membuka daftar (pencairan tetap lewat panel tab)
 */
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { useAuthStore } from '../stores/auth'

const emit = defineEmits(['open', 'act'])
const props = defineProps({ reloadKey: { type: Number, default: 0 } })

const auth = useAuthStore()
const role = computed(() => String(auth.role || '').toLowerCase())
const isGa = computed(() => ['ga', 'admin'].includes(role.value))

const data = ref(null)
const loading = ref(true)
const expanded = ref({})

const thresholds = computed(() => data.value?.thresholds || {
  claim_days: 2, driver_days: 14, lpj_days: 7,
})
const items = computed(() => (Array.isArray(data.value?.items) ? data.value.items : []))
const total = computed(() => items.value.reduce((a, i) => a + (Number(i.count) || 0), 0))
const fmt = (n) => 'Rp ' + Number(n || 0).toLocaleString('id-ID')

/** Aksi yang boleh ditampilkan untuk sebuah item antrean. */
function actionsFor(item) {
  if (item.key === 'claim_pending' && isGa.value) {
    return [{ kind: 'verify_claim', label: '✅ Verifikasi GA', cls: 'btn-primary' }]
  }
  if (item.key === 'lpj_pending' && isGa.value) {
    return [
      { kind: 'approve_lpj', label: '✅ Approve LPJ', cls: 'btn-success' },
      { kind: 'reject_lpj', label: '❌ Tolak LPJ', cls: 'btn-danger' },
    ]
  }
  return []
}

function toggle(key) {
  expanded.value = { ...expanded.value, [key]: !expanded.value[key] }
}

function act(kind, item) {
  emit('act', { kind, item })
}

async function load() {
  try {
    data.value = await api('/api/bbm/workspace/actions')
  } catch {
    data.value = null
  } finally {
    loading.value = false
  }
}

watch(() => props.reloadKey, load)
onMounted(load)
</script>

<template>
  <div v-if="!loading && data" class="card card-pad action-queue" data-testid="action-queue">
    <div class="row" style="gap:10px;flex-wrap:wrap;align-items:center;">
      <b>🚨 Perlu Tindakan</b>
      <span v-if="!items.length" class="badge badge-green" data-testid="action-clear">✅ Tidak ada antrean menua</span>
      <span v-else class="badge badge-amber">{{ total }} item menunggu</span>
      <div class="spacer"></div>
      <span class="muted" style="font-size:11px;">
        Ambang: klaim &gt; {{ thresholds.claim_days }} hari ·
        dana di driver &gt; {{ thresholds.driver_days }} hari ·
        LPJ &gt; {{ thresholds.lpj_days }} hari
      </span>
    </div>

    <div v-if="items.length" class="row" style="gap:10px;flex-wrap:wrap;margin-top:10px;">
      <div v-for="it in items" :key="it.key" class="aq-item" :data-testid="'action-' + it.key">
        <div class="row" style="gap:6px;align-items:baseline;">
          <b style="font-size:18px;">{{ it.count }}</b>
          <span class="muted" style="font-size:12px;">{{ it.label }}</span>
        </div>
        <div class="muted" style="font-size:11px;margin-top:2px;">
          {{ fmt(it.amount) }} · paling lama {{ it.oldest_days ?? '—' }} hari
        </div>

        <div class="row" style="gap:6px;margin-top:8px;flex-wrap:wrap;">
          <button class="btn btn-sm btn-primary" :data-testid="'action-open-' + it.key"
                  @click="emit('open', it.target)">
            Buka antrean →
          </button>
          <button v-if="it.rows && it.rows.length" class="btn btn-sm"
                  :data-testid="'action-rows-' + it.key"
                  :aria-expanded="expanded[it.key] ? 'true' : 'false'"
                  @click="toggle(it.key)">
            {{ expanded[it.key] ? '▲ Sembunyikan baris' : '▾ Lihat baris (' + it.rows.length + ')' }}
          </button>
        </div>

        <div v-if="expanded[it.key] && it.rows.length" class="aq-rows" :data-testid="'action-rows-list-' + it.key">
          <div v-for="r in it.rows" :key="it.key + '-' + r.id" class="aq-row"
               :data-testid="'action-row-' + it.key + '-' + r.id">
            <div class="grow">
              <b style="font-size:12px;">{{ r.ref || ('#' + r.id) }}</b>
              <div class="muted" style="font-size:10px;">
                {{ r.driver_name || '—' }}<span v-if="r.nopol"> · {{ r.nopol }}</span>
                · {{ fmt(r.amount) }} · {{ r.age_days ?? '—' }} hari
              </div>
            </div>
            <div class="row" style="gap:4px;flex-wrap:wrap;justify-content:flex-end;">
              <button v-for="a in actionsFor(it)" :key="a.kind" class="btn btn-sm" :class="a.cls"
                      :data-testid="'action-do-' + it.key + '-' + a.kind + '-' + r.id"
                      @click="act(a.kind, r)">
                {{ a.label }}
              </button>
            </div>
          </div>
          <div v-if="it.count > it.rows.length" class="muted" style="font-size:10px;margin-top:6px;">
            Menampilkan {{ it.rows.length }} dari {{ it.count }} baris — sisanya bisa dibuka lewat tab tujuan.
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.action-queue { margin-bottom: 14px; }
.aq-item {
  border: 1px solid var(--border, #e5e7eb); border-radius: 10px;
  padding: 10px 12px; min-width: 190px; background: var(--surface, #fff);
}
.aq-rows { margin-top: 8px; border-top: 1px dashed var(--border, #e5e7eb); padding-top: 8px; }
.aq-row {
  display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
  padding: 6px 0; border-bottom: 1px solid var(--border, #e5e7eb);
}
.aq-row:last-child { border-bottom: none; }
</style>
