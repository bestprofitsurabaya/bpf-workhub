<script setup>
import { computed, ref, watch } from 'vue'
import Modal from './Modal.vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  steps: { type: Array, default: () => [] },
})
const emit = defineEmits(['close', 'done'])

const step = ref(0)
const stepData = computed(() => props.steps[step.value] || null)
const last = computed(() => step.value >= props.steps.length - 1)

watch(() => props.open, (v) => { if (v) step.value = 0 })

function next() {
  if (last.value) emit('done')
  else step.value += 1
}
</script>

<template>
  <Modal v-if="open && stepData" title="👋 Panduan singkat" @close="emit('close')">
    <div class="tour">
      <div class="tour-icon" aria-hidden="true">{{ stepData.icon }}</div>
      <h4>{{ stepData.title }}</h4>
      <p>{{ stepData.body }}</p>
      <ul v-if="stepData.points?.length">
        <li v-for="(p, i) in stepData.points" :key="i">{{ p }}</li>
      </ul>
      <div class="tour-dots" aria-hidden="true">
        <span v-for="(_, i) in steps" :key="i" :class="{ on: i === step }"></span>
      </div>
    </div>
    <div class="tour-foot">
      <button type="button" class="btn btn-sm" @click="emit('close')">Lewati</button>
      <div class="spacer"></div>
      <button type="button" class="btn btn-sm" :disabled="step === 0" @click="step -= 1">← Sebelumnya</button>
      <button type="button" class="btn btn-primary btn-sm" @click="next">
        {{ last ? '✅ Mulai pakai' : 'Lanjut →' }}
      </button>
    </div>
  </Modal>
</template>

<style scoped>
.tour { text-align: center; padding: 4px 2px 0; }
.tour-icon { font-size: 38px; line-height: 1; margin-bottom: 6px; }
.tour h4 { margin: 0 0 6px; font-size: 17px; }
.tour p { margin: 0 auto 10px; max-width: 440px; font-size: 13px; line-height: 1.6; color: var(--text-2); }
.tour ul { margin: 0 auto 12px; max-width: 430px; text-align: left; padding-left: 20px; font-size: 12px; line-height: 1.7; color: var(--text-2); }
.tour-dots { display: flex; justify-content: center; gap: 5px; margin: 4px 0 2px; }
.tour-dots span { width: 6px; height: 6px; border-radius: 50%; background: var(--border); }
.tour-dots span.on { width: 16px; border-radius: 6px; background: var(--primary); }
.tour-foot { display: flex; align-items: center; gap: 8px; margin-top: 16px; padding-top: 12px; border-top: 1px solid var(--border); }
</style>
