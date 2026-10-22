<script setup>
import { computed, ref, watch } from 'vue'
import Modal from './Modal.vue'
import { GLOSSARY, helpForPath } from '../content/help.js'
import { firstAction, formatDuration, isUsabilityMode, resetUsabilitySession } from '../utils/usability.js'

const props = defineProps({
  open: { type: Boolean, default: false },
  path: { type: String, default: '/' },
  role: { type: String, default: '' },
})
const emit = defineEmits(['close', 'replay-tour'])

const tab = ref('page')
const q = ref('')
const p5Mode = ref(isUsabilityMode())
const p5 = ref(firstAction())

const pageHelp = computed(() => helpForPath(props.path))
const glossary = computed(() => {
  const needle = q.value.trim().toLowerCase()
  if (!needle) return GLOSSARY
  return GLOSSARY.filter((g) =>
    `${g.term} ${g.full} ${g.category} ${g.desc}`.toLowerCase().includes(needle))
})
const grouped = computed(() => {
  const out = {}
  for (const g of glossary.value) (out[g.category] ||= []).push(g)
  return out
})

watch(() => props.open, (v) => {
  if (!v) return
  tab.value = 'page'
  q.value = ''
  p5Mode.value = isUsabilityMode()
  p5.value = firstAction()
})

function showTerm(term) {
  tab.value = 'glossary'
  q.value = term
}

function resetP5() {
  resetUsabilitySession()
  p5.value = null
}
</script>

<template>
  <Modal v-if="open" title="❓ Bantuan & Glosarium" wide @close="emit('close')">
    <div class="help-tabs" role="tablist" aria-label="Bagian bantuan">
      <button type="button" role="tab" :aria-selected="tab === 'page'" :class="{ on: tab === 'page' }" @click="tab = 'page'">
        📄 Halaman ini
      </button>
      <button type="button" role="tab" :aria-selected="tab === 'glossary'" :class="{ on: tab === 'glossary' }" @click="tab = 'glossary'">
        📚 Glosarium
      </button>
    </div>

    <section v-if="tab === 'page'" class="help-page">
      <template v-if="pageHelp">
        <h4>{{ pageHelp.title }}</h4>
        <p class="muted">{{ pageHelp.summary }}</p>
        <ol class="help-steps">
          <li v-for="(s, i) in pageHelp.steps" :key="i">{{ s }}</li>
        </ol>
        <div v-if="pageHelp.terms?.length" class="help-terms">
          <span class="muted" style="font-size:11px;">Istilah terkait:</span>
          <button v-for="t in pageHelp.terms" :key="t" type="button" class="term-chip" @click="showTerm(t)">{{ t }}</button>
        </div>
      </template>
      <template v-else>
        <h4>Panduan halaman</h4>
        <p class="muted">Halaman ini belum punya panduan khusus. Gunakan pencarian menu (Ctrl+K) atau buka glosarium untuk memahami istilah yang muncul.</p>
      </template>
      <div class="help-actions">
        <button type="button" class="btn btn-sm" @click="$emit('replay-tour')">↻ Tampilkan tur singkat</button>
      </div>
    </section>

    <section v-else class="help-glossary">
      <label class="field" style="margin:0 0 10px;">
        <span class="muted" style="font-size:11px;">Cari istilah</span>
        <input v-model="q" class="input" type="search" placeholder="mis. LPJ, ODO, step-up" />
      </label>
      <div v-if="!glossary.length" class="muted" style="padding:12px 0;">Istilah tidak ditemukan.</div>
      <div v-for="(items, cat) in grouped" :key="cat" class="glossary-group">
        <div class="glossary-cat">{{ cat }}</div>
        <div class="glossary-grid">
          <article v-for="g in items" :key="g.term" class="glossary-item">
            <b>{{ g.term }}</b>
            <span v-if="g.full && g.full !== g.term" class="muted"> · {{ g.full }}</span>
            <p>{{ g.desc }}</p>
          </article>
        </div>
      </div>
    </section>

    <div v-if="p5Mode" class="p5-box">
      <b>🧪 Mode uji kegunaan</b>
      <span v-if="p5">
        Aksi pertama: <b>{{ p5.label }}</b> · {{ formatDuration(p5.ms) }}
        <span :class="p5.ms < 30000 ? 'p5-ok' : 'p5-warn'">{{ p5.ms < 30000 ? '✓ di bawah target' : '⚠ di atas target' }}</span>
      </span>
      <span v-else class="muted">Belum ada aksi tercatat (target &lt; 30 dtk).</span>
      <button type="button" class="btn btn-sm" @click="resetP5">Reset sesi</button>
    </div>

    <div class="help-foot">
      <span class="muted">Tips: tekan <kbd>?</kbd> di halaman mana pun untuk membuka bantuan.</span>
      <button class="btn btn-primary btn-sm" @click="emit('close')">Tutup</button>
    </div>
  </Modal>
</template>

<style scoped>
.help-tabs { display: flex; gap: 6px; border-bottom: 1px solid var(--border); margin-bottom: 14px; }
.help-tabs button {
  border: none; background: transparent; color: var(--text-3);
  font-size: 12px; font-weight: 700; padding: 8px 10px; border-bottom: 2px solid transparent;
}
.help-tabs button.on { color: var(--primary); border-bottom-color: var(--primary); }
.help-page h4, .help-glossary h4 { margin: 0 0 4px; font-size: 15px; }
.help-page p { margin: 0 0 10px; font-size: 12.5px; }
.help-steps { margin: 0 0 12px; padding-left: 20px; font-size: 12.5px; line-height: 1.7; }
.help-terms { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.term-chip {
  border: 1px solid var(--border); background: var(--surface-2); color: var(--text-2);
  border-radius: 20px; padding: 3px 9px; font-size: 11px;
}
.term-chip:hover { border-color: var(--primary); color: var(--primary); }
.help-actions { margin-top: 16px; }
.glossary-group { margin-bottom: 14px; }
.glossary-cat { font-size: 10px; font-weight: 800; letter-spacing: .5px; color: var(--text-3); text-transform: uppercase; margin-bottom: 6px; }
.glossary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 8px; }
.glossary-item { border: 1px solid var(--border); border-radius: 10px; padding: 9px 11px; background: var(--surface-2); }
.glossary-item b { font-size: 12.5px; }
.glossary-item p { margin: 4px 0 0; font-size: 11.5px; line-height: 1.55; color: var(--text-2); }
.p5-box { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-top: 14px; padding: 9px 11px; border: 1px dashed var(--primary); border-radius: 8px; background: var(--surface-2); font-size: 11.5px; }
.p5-ok { color: #059669; font-weight: 700; }
.p5-warn { color: #dc2626; font-weight: 700; }
.help-foot { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; margin-top: 16px; padding-top: 12px; border-top: 1px solid var(--border); font-size: 11px; }
.help-foot kbd { font-family: inherit; border: 1px solid var(--border); border-radius: 4px; padding: 0 5px; background: var(--surface-2); }
</style>
