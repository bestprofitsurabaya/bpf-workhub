<script setup>
import { computed, h, ref } from 'vue'
import TkdBankPanel from './TkdBankPanel.vue'
import TkdResultsPanel from './TkdResultsPanel.vue'

// Dipakai sebagai tab di hub rekrutmen: PageHeader tidak dirender di sini.
defineProps({ embedded: { type: Boolean, default: false } })

const TABS = [
  { id: 'bank', label: 'Bank Soal' },
  { id: 'hasil', label: 'Hasil' },
  { id: 'pengaturan', label: 'Pengaturan' },
]

// Placeholder untuk panel pengaturan (diganti Task 18).
const PlaceholderPanel = {
  render: () => h('div', { class: 'card card-pad' }, [h('p', 'Segera tersedia.')]),
}

const PANELS = {
  bank: TkdBankPanel,
  hasil: TkdResultsPanel,
  pengaturan: PlaceholderPanel,
}

const activeTab = ref('bank')
const activePanel = computed(() => PANELS[activeTab.value] || TkdBankPanel)
</script>

<template>
  <div class="tkd-shell">
    <nav class="hub-tabs tkd-tabs" aria-label="Sub-tab TKD">
      <button v-for="tab in TABS" :key="tab.id" type="button"
              class="btn btn-sm hub-tab" :class="{ active: activeTab === tab.id }"
              :data-subtab="tab.id" :aria-current="activeTab === tab.id ? 'page' : undefined"
              @click="activeTab = tab.id">
        {{ tab.label }}
      </button>
    </nav>
    <component :is="activePanel" />
  </div>
</template>

<style scoped>
/* Hub-scoped styles tidak menembus komponen ini, jadi tab didefinisikan ulang. */
.tkd-tabs {
  display: flex; gap: 6px; align-items: center;
  overflow-x: auto; -webkit-overflow-scrolling: touch;
  margin-bottom: 12px; padding-bottom: 4px;
}
.tkd-tabs .hub-tab { white-space: nowrap; flex-shrink: 0; }
.tkd-tabs .hub-tab.active { border-color: var(--primary); color: var(--primary); font-weight: 700; }
</style>
