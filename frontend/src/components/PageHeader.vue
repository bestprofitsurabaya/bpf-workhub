<script setup>
// v2.54.0 — Fase-2 design system: komponen PageHeader standar semua halaman.
// Meneruskan pola card + judul/aksi agar setiap view memakai satu bentuk yang
// sama (puncaknya: Dashboard Finance dulu, view lain menyusul bertahap).
defineProps({
  icon: { type: String, default: '' },
  title: { type: String, required: true },
  subtitle: { type: String, default: '' },
})
</script>

<template>
  <div class="card card-pad page-header">
    <div class="ph-main">
      <span v-if="icon" class="ph-icon" aria-hidden="true">{{ icon }}</span>
      <div>
        <h2 class="ph-title">{{ title }}</h2>
        <div v-if="subtitle" class="ph-sub">{{ subtitle }}</div>
      </div>
    </div>
    <div class="ph-actions">
      <slot />
    </div>
  </div>
</template>
