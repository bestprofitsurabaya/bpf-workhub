<script setup>
/**
 * Pager sederhana untuk daftar panjang (v2.129.0).
 *
 * Dipakai beberapa halaman yang sebelumnya merender seluruh baris sekaligus
 * (Riwayat Overtime Security/OB, Daftar User, Review Akses). Tidak melakukan
 * pemotongan data — indeks halaman dihitung pemanggil via computed, sehingga
 * filter/pencarian tetap bekerja pada dataset penuh.
 */
import { computed } from 'vue'

const props = defineProps({
  page: { type: Number, default: 1 },
  pageCount: { type: Number, default: 1 },
  total: { type: Number, default: 0 },
  unit: { type: String, default: 'entri' },
})
const emit = defineEmits(['update:page'])

const info = computed(
  () => `Halaman ${props.page} / ${props.pageCount} · ${props.total} ${props.unit}`,
)

function go(target) {
  const max = Math.max(1, props.pageCount)
  const next = Math.min(Math.max(1, target), max)
  if (next !== props.page) emit('update:page', next)
}
</script>

<template>
  <div v-if="pageCount > 1" class="pager">
    <button type="button" class="btn btn-sm" :disabled="page <= 1" @click="go(page - 1)">
      ← Sebelumnya
    </button>
    <span class="muted pager-info">{{ info }}</span>
    <button type="button" class="btn btn-sm" :disabled="page >= pageCount" @click="go(page + 1)">
      Berikutnya →
    </button>
  </div>
</template>

<style scoped>
.pager {
  display: flex; align-items: center; gap: 10px; justify-content: center;
  padding: 12px; flex-wrap: wrap;
}
.pager-info { font-size: 12px; }
</style>
