<script setup>
/** Detail orang + seluruh data rekrutmen (Rilis C/D). */
import { onMounted, ref } from 'vue'
import { api } from '../api'

const props = defineProps({
  person: { type: Object, required: true },
  readOnly: { type: Boolean, default: false },
  view: { type: String, default: '' },
})
const emit = defineEmits(['close', 'saved'])

const detail = ref(null)
const timeline = ref([])
const error = ref('')
const reason = ref('')

const applicantId = () => props.person.id || props.person.applicant_id || ''
const query = () => (props.view ? { params: { view: props.view } } : {})

async function load() {
  if (!props.person.case_id) {
    detail.value = { case: { nama: props.person.nama }, cv: {}, first_work: {},
                     training: [], steps: [], branches: [], tkd: {} }
    timeline.value = []
    return
  }
  const id = encodeURIComponent(props.person.case_id)
  try {
    const [d, t] = await Promise.all([
      api(`/api/recruitment/people/${id}`, query()),
      api(`/api/recruitment/people/${id}/timeline`, query()),
    ])
    detail.value = d?.data || null
    timeline.value = t?.data || []
  } catch (e) {
    error.value = e?.message || 'Detail tidak dapat dimuat.'
  }
}

function stepStatus(type) {
  const step = (detail.value?.steps || []).find((s) => s.step_type === type)
  return step?.status || 'BELUM'
}

async function act(path, body = {}) {
  if (!applicantId()) return
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
    <header class="rp-head">
      <h3>{{ person.nama || detail?.case?.nama || 'Detail' }}</h3>
      <button type="button" class="btn btn-sm" @click="emit('close')">Tutup</button>
    </header>
    <p v-if="error" class="rp-error" role="alert">{{ error }}</p>

    <template v-if="detail && !readOnly">
      <section class="rp-section">
        <h4>Identitas & kasus</h4>
        <p>NIK: {{ detail.case?.nik || person.nik || person.nik_masked || '—' }}</p>
        <p>Cabang: {{ detail.case?.first_branch || person.branch_code || '—' }}</p>
        <p>Status kasus: {{ detail.case?.status || person.status || '—' }}</p>
        <p>CV: {{ stepStatus('CV') }} · Training: {{ stepStatus('TRAINING') }} ·
           TKD: {{ stepStatus('TKD') }} · FirstWork: {{ stepStatus('FIRSTWORK') }}</p>
      </section>

      <section class="rp-section">
        <h4>Riwayat cabang</h4>
        <p v-if="!detail.branches?.length" class="rp-muted">Belum ada riwayat.</p>
        <ul v-else>
          <li v-for="branch in detail.branches" :key="branch.branch_code">
            {{ branch.branch_code }}
            <small>{{ branch.first_seen_at || '' }} — {{ branch.last_seen_at || '' }}</small>
          </li>
        </ul>
      </section>

      <section class="rp-section">
        <h4>CV Online</h4>
        <template v-if="detail.cv?.nama">
          <p>{{ detail.cv.nama }} · {{ detail.cv.tempat_lahir || '—' }},
             {{ String(detail.cv.tanggal_lahir || '').slice(0, 10) || '—' }}</p>
          <p>Jenis kelamin: {{ detail.cv.jenis_kelamin || '—' }} ·
             HP: {{ detail.cv.no_hp || '—' }}</p>
          <p>Pendidikan: {{ detail.cv.pendidikan_terakhir || '—' }}</p>
          <p>Alamat: {{ detail.cv.alamat || '—' }} · Domisili: {{ detail.cv.domisili || '—' }}</p>
          <p>Pengalaman: {{ detail.cv.pengalaman_status || '—' }}
             {{ detail.cv.pengalaman_lama ? '· ' + detail.cv.pengalaman_lama : '' }}</p>
        </template>
        <p v-else class="rp-muted">CV belum diisi.</p>
      </section>

      <section class="rp-section">
        <h4>Training H1/H2</h4>
        <p v-if="!detail.training?.length" class="rp-muted">Belum ada absensi training.</p>
        <ul v-else>
          <li v-for="event in detail.training" :key="event.id || event.day">
            Hari {{ event.day }} — {{ event.attended_at }}
            <small>{{ event.link_status || '' }}</small>
          </li>
        </ul>
      </section>

      <section class="rp-section">
        <h4>TKD</h4>
        <p>Status langkah: {{ stepStatus('TKD') }}</p>
        <p v-if="detail.tkd?.score != null">Skor: {{ detail.tkd.score }} ·
           Percobaan: {{ detail.tkd.attempt_no || '—' }}</p>
        <p v-else class="rp-muted">Belum ada hasil TKD.</p>
      </section>

      <section class="rp-section">
        <h4>FirstWork</h4>
        <template v-if="detail.first_work?.registration_no">
          <p>No. registrasi: {{ detail.first_work.registration_no }}</p>
          <p>Cabang: {{ detail.first_work.branch_code || '—' }} ·
             {{ detail.first_work.submitted_at || '' }}</p>
          <p>ID Fingerprint: {{ detail.first_work.fingerprint_no || '—' }} ·
             ID BPF: {{ detail.first_work.bpf_no || '—' }}</p>
          <a v-if="detail.card_token" class="btn btn-sm"
             :href="`/api/first-work/card/${detail.first_work.id}.pdf?t=${detail.card_token}`">
            Unduh Kartu</a>
        </template>
        <p v-else class="rp-muted">FirstWork belum diisi.</p>
      </section>

      <section class="rp-section">
        <h4>Linimasa</h4>
        <ol class="rp-timeline">
          <li v-for="event in timeline" :key="event.id">
            <b>{{ event.event_type }}</b>
            <span>{{ event.event_at }} · {{ event.branch_code }} ·
              {{ event.actor_name || event.actor_role }}</span>
            <em v-if="event.note">{{ event.note }}</em>
          </li>
        </ol>
        <p v-if="!timeline.length" class="rp-muted">Belum ada kejadian.</p>
      </section>

      <section v-if="applicantId()" class="rp-section">
        <h4>Aksi</h4>
        <input v-model="reason" aria-label="Alasan" placeholder="Alasan (wajib untuk pulang)" />
        <div class="rp-actions">
          <button type="button" class="btn btn-sm"
                  @click="act(`/api/applicants/${applicantId()}/verify`)">Verifikasi</button>
          <button v-for="stage in ['interview','training_1','training_2','training_3','training_4']"
                  :key="stage" type="button" class="btn btn-sm"
                  @click="act(`/api/applicants/${applicantId()}/attendance`, { stage })">
            {{ stage.replace('training_', 'H') }}
          </button>
          <button type="button" class="btn btn-sm"
                  @click="act(`/api/applicants/${applicantId()}/status`, { status: 'resigned', reason })">
            Pulang
          </button>
          <button type="button" class="btn btn-sm"
                  @click="act(`/api/applicants/${applicantId()}/status`, { status: 'lulus' })">
            Lulus
          </button>
          <button v-if="!person.nik && !person.nik_masked" type="button" class="btn btn-sm"
                  @click="act(`/api/applicants/${applicantId()}/link-nik`, { nik: reason })">
            Tautkan NIK
          </button>
        </div>
      </section>
    </template>

    <section v-else-if="detail?.first_work" class="rp-section">
      <h4>FirstWork (akses finance)</h4>
      <p>No. registrasi: {{ detail.first_work.registration_no || '—' }}</p>
      <p>Cabang: {{ detail.first_work.branch_code || '—' }}</p>
    </section>
  </aside>
</template>

<style scoped>
.rp-detail { margin-top: 16px; padding: 16px; border: 1px solid var(--border); border-radius: 8px; }
.rp-head { display: flex; justify-content: space-between; align-items: center; }
.rp-section { padding: 10px 0; border-bottom: 1px solid var(--border); }
.rp-section h4 { margin: 0 0 6px; }
.rp-section p { margin: 2px 0; font-size: 13px; }
.rp-section ul { margin: 4px 0; padding-left: 18px; font-size: 13px; }
.rp-timeline { list-style: none; padding: 0; margin: 0; }
.rp-timeline li { padding: 6px 0; border-bottom: 1px solid var(--border); display: grid; gap: 2px; }
.rp-timeline span, .rp-timeline em, .rp-muted, .rp-section small { font-size: 12px; color: var(--muted); }
.rp-actions { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
.rp-section input { padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px; }
.rp-error { color: var(--danger); }
</style>
