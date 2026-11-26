<script setup>
/** Detail orang + linimasa kejadian rekrutmen (Rilis C). */
import { onMounted, ref } from 'vue'
import { api } from '../api'

const props = defineProps({
  person: { type: Object, required: true },
  readOnly: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'saved'])

const detail = ref(null)
const timeline = ref([])
const error = ref('')
const reason = ref('')

async function load() {
  if (!props.person.case_id) {
    detail.value = { case: { nama: props.person.nama } }
    timeline.value = []
    return
  }
  try {
    const [d, t] = await Promise.all([
      api(`/api/recruitment/people/${encodeURIComponent(props.person.case_id)}`),
      api(`/api/recruitment/people/${encodeURIComponent(props.person.case_id)}/timeline`),
    ])
    detail.value = d?.data || null
    timeline.value = t?.data || []
  } catch (e) {
    error.value = e?.message || 'Detail tidak dapat dimuat.'
  }
}

async function act(path, body = {}) {
  if (!props.person.display_id) return
  try {
    await api(path, { method: 'POST', body })
    reason.value = ''
    await load()
    emit('saved')
  } catch (e) {
    error.value = e?.message || 'Aksi gagal.'
  }
}

onMounted(load)
</script>

<template>
  <aside class="rp-detail" aria-label="Detail orang">
    <header><h3>{{ person.nama || detail?.case?.nama || 'Detail' }}</h3>
      <button type="button" class="btn btn-sm" @click="emit('close')">Tutup</button></header>
    <p v-if="error" class="rp-error" role="alert">{{ error }}</p>

    <div v-if="detail" class="rp-sections">
      <section><h4>Identitas</h4>
        <p>NIK: {{ person.nik_masked || '—' }}</p>
        <p>CV: {{ detail.cv?.nama ? 'Selesai' : 'Belum ada' }}</p>
        <p>Kartu: {{ detail.first_work?.registration_no || 'Belum ada' }}</p>
      </section>
      <section><h4>Linimasa</h4>
        <ol class="rp-timeline">
          <li v-for="event in timeline" :key="event.id">
            <b>{{ event.event_type }}</b>
            <span>{{ event.event_at }} · {{ event.branch_code }} · {{ event.actor_name || event.actor_role }}</span>
            <em v-if="event.note">{{ event.note }}</em>
          </li>
        </ol>
        <p v-if="!timeline.length" class="rp-empty">Belum ada kejadian.</p>
      </section>
    </div>

    <div v-if="!readOnly && person.display_id" class="rp-actions">
      <input v-model="reason" aria-label="Alasan" placeholder="Alasan (wajib untuk pulang)" />
      <button type="button" class="btn btn-sm" @click="act(`/api/applicants/${person.id}/verify`)">Verifikasi</button>
      <button type="button" class="btn btn-sm" @click="act(`/api/applicants/${person.id}/status`, { status: 'resigned', reason })">Pulang</button>
      <button type="button" class="btn btn-sm" @click="act(`/api/applicants/${person.id}/status`, { status: 'lulus' })">Lulus</button>
      <button v-if="!person.nik" type="button" class="btn btn-sm"
              @click="act(`/api/applicants/${person.id}/link-nik`, { nik: reason })">Tautkan NIK</button>
    </div>
  </aside>
</template>

<style scoped>
.rp-detail { margin-top: 16px; padding: 16px; border: 1px solid var(--border); border-radius: 8px; }
.rp-detail header { display: flex; justify-content: space-between; align-items: center; }
.rp-sections { display: grid; gap: 12px; }
.rp-timeline { list-style: none; padding: 0; margin: 0; }
.rp-timeline li { padding: 6px 0; border-bottom: 1px solid var(--border); display: grid; gap: 2px; }
.rp-timeline span, .rp-timeline em { font-size: 12px; color: var(--muted); }
.rp-actions { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 12px; }
.rp-actions input { padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px; }
.rp-error { color: var(--danger); }
.rp-empty { color: var(--muted); }
</style>
