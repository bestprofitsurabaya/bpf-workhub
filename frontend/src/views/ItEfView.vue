<script setup>
import { ref, onMounted, computed } from 'vue'
import { api } from '../api'
import Modal from '../components/Modal.vue'

// --- State ---
const loading = ref(true)
const err = ref('')
const msg = ref('')
const busy = ref(false)

// Sites
const sites = ref([])
const showSiteForm = ref(false)
const siteForm = ref({ name: '', wp_url: '', wp_media_url: '', username: '', app_password: '' })

// Scraper
const scrapePages = ref(2)
const articles = ref([])
const scrapeBusy = ref(false)

// Upload
const selectedSite = ref('')
const uploadBusy = ref(false)
const uploadResult = ref(null)
const settings = ref({
  backlinks: true,
  max_backlinks: 3,
  seo_optimize: true,
  static_tags: 'newsmaker.id, Market, Geopolitics, Financial News',
})

// Duplicates
const dupSite = ref('')
const duplicates = ref([])
const dupBusy = ref(false)

// Backlinks
const showBacklinks = ref(false)
const authoritySites = ref({})
const keywordMapping = ref({})
const newKeyword = ref('')
const newSiteName = ref('')

// Log
const logs = ref([])
const showLog = ref(false)

// --- Computed ---
const siteNames = computed(() => sites.value.map(s => s.name))

// --- Load ---
async function loadSites() {
  loading.value = true; err.value = ''
  try {
    sites.value = await api('/api/scraper/sites')
  } catch (e) { err.value = e.message }
  finally { loading.value = false }
}

// --- WP Site Management ---
function openSiteForm(site) {
  if (site) {
    siteForm.value = { ...site, app_password: '' }
  } else {
    siteForm.value = { name: '', wp_url: '', wp_media_url: '', username: '', app_password: '' }
  }
  showSiteForm.value = true
}

async function saveSite() {
  busy.value = true; msg.value = ''
  try {
    const body = { ...siteForm.value }
    if (!body.app_password && body.name) delete body.app_password
    const r = await api('/api/scraper/sites', { method: 'POST', body })
    msg.value = '✅ ' + (r.message || 'Site disimpan')
    showSiteForm.value = false
    await loadSites()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { busy.value = false }
}

async function deleteSite(name) {
  if (!confirm(`Hapus site "${name}"?`)) return
  busy.value = true; msg.value = ''
  try {
    await api(`/api/scraper/sites/${encodeURIComponent(name)}`, { method: 'DELETE' })
    msg.value = `✅ Site "${name}" dihapus`
    await loadSites()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { busy.value = false }
}

async function testConnection(site) {
  msg.value = '⏳ Menguji koneksi...'
  try {
    const r = await api('/api/scraper/test-connection', {
      method: 'POST',
      body: { wp_url: site.wp_url, username: site.username, app_password: '___test___' },
    })
    msg.value = r.ok ? '✅ ' + r.message : '❌ ' + r.message
  } catch (e) { msg.value = '❌ ' + e.message }
}

// --- Progress ---
const progress = ref(null)
const progressInterval = ref(null)

async function pollProgress(taskId) {
  if (progressInterval.value) clearInterval(progressInterval.value)
  progress.value = { stage: 'start', progress: 0, message: 'Memulai...', total: 0, current: 0 }
  progressInterval.value = setInterval(async () => {
    try {
      const r = await api(`/api/scraper/progress/${taskId}`)
      if (r.ok) {
        progress.value = r
        if (r.stage === 'done') {
          clearInterval(progressInterval.value)
          progressInterval.value = null
        }
      }
    } catch { /* ignore */ }
  }, 800)
}

function stopProgress() {
  if (progressInterval.value) { clearInterval(progressInterval.value); progressInterval.value = null }
  progress.value = null
}

// --- Upload History ---
const showHistory = ref(false)
const historyList = ref([])
const historyFilter = ref({ date_from: '', date_to: '', action: '' })
const historyBusy = ref(false)

async function loadHistory() {
  historyBusy.value = true
  try {
    const params = new URLSearchParams()
    if (historyFilter.value.date_from) params.set('date_from', historyFilter.value.date_from)
    if (historyFilter.value.date_to) params.set('date_to', historyFilter.value.date_to)
    if (historyFilter.value.action) params.set('action', historyFilter.value.action)
    const r = await api(`/api/scraper/history?${params}`)
    historyList.value = r.history || []
  } catch { historyList.value = [] }
  finally { historyBusy.value = false }
}

function openHistory() { loadHistory(); showHistory.value = true }

// --- Scrape ---
async function scrapeArticles() {
  if (!selectedSite.value) { msg.value = '⚠️ Pilih WordPress site dulu'; return }
  scrapeBusy.value = true; msg.value = ''; articles.value = []
  const taskId = `scrape_${Date.now()}`
  pollProgress(taskId)
  try {
    const r = await api(`/api/scraper/check?task_id=${taskId}`, { method: 'POST', body: { pages: scrapePages.value } })
    articles.value = r.articles || []
    msg.value = r.ok ? `✅ Ditemukan ${r.count} artikel` : '⚠️ Tidak ada artikel ditemukan'
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { scrapeBusy.value = false }
}

// --- Upload ---
async function uploadToWP() {
  if (!selectedSite.value) { msg.value = '⚠️ Pilih WordPress site'; return }
  if (!articles.value.length) { msg.value = '⚠️ Scrape artikel dulu'; return }
  uploadBusy.value = true; msg.value = ''; uploadResult.value = null
  const taskId = `upload_${Date.now()}`
  pollProgress(taskId)
  try {
    const r = await api(`/api/scraper/upload?task_id=${taskId}`, {
      method: 'POST',
      body: {
        site_name: selectedSite.value,
        articles: articles.value,
        settings: {
          backlinks: settings.value.backlinks,
          max_backlinks: settings.value.max_backlinks,
          seo_optimize: settings.value.seo_optimize,
          static_tags: settings.value.static_tags,
        },
      },
    })
    uploadResult.value = r
    msg.value = `✅ Upload selesai: ${r.new_posts} baru, ${r.updated_posts} update`
    if (r.errors?.length) msg.value += ` (${r.errors.length} error)`
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { uploadBusy.value = false }
}

// --- Duplicates ---
async function checkDuplicates() {
  if (!dupSite.value) { msg.value = '⚠️ Pilih site'; return }
  dupBusy.value = true; msg.value = ''; duplicates.value = []
  try {
    const r = await api('/api/scraper/duplicates', { method: 'POST', body: { site_name: dupSite.value } })
    duplicates.value = r.duplicates || []
    msg.value = `Ditemukan ${duplicates.value.length} artikel duplikat dari ${r.total_posts} total`
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { dupBusy.value = false }
}

async function deleteDuplicate(postIds) {
  if (!confirm(`Hapus ${postIds.length} post duplikat?`)) return
  dupBusy.value = true; msg.value = ''
  try {
    const r = await api('/api/scraper/duplicates/delete', {
      method: 'POST',
      body: { site_name: dupSite.value, post_ids: postIds },
    })
    msg.value = `✅ ${r.deleted} post dihapus`
    await checkDuplicates()
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { dupBusy.value = false }
}

// --- Backlinks ---
async function loadBacklinks() {
  try {
    const r = await api('/api/scraper/backlinks')
    authoritySites.value = r.authority_sites || {}
    keywordMapping.value = r.keyword_mapping || {}
  } catch (e) { /* noop */ }
}

function openBacklinksModal() {
  loadBacklinks()
  showBacklinks.value = true
}

async function saveKeywordMapping() {
  if (!newKeyword.value || !newSiteName.value) { msg.value = '⚠️ Isi keyword dan site'; return }
  busy.value = true; msg.value = ''
  try {
    await api('/api/scraper/backlinks/add-keyword', {
      method: 'POST',
      body: { keyword: newKeyword.value, site_name: newSiteName.value },
    })
    keywordMapping.value[newKeyword.value] = newSiteName.value
    newKeyword.value = ''; newSiteName.value = ''
    msg.value = '✅ Keyword mapping ditambahkan'
  } catch (e) { msg.value = '❌ ' + e.message }
  finally { busy.value = false }
}

// --- Log ---
async function loadLog() {
  try { logs.value = await api('/api/scraper/log?limit=100') } catch { logs.value = [] }
}

function openLog() { loadLog(); showLog.value = true }

async function clearLog() {
  try {
    await api('/api/scraper/log', { method: 'DELETE' })
    logs.value = []; msg.value = '✅ Log cleared'
  } catch (e) { msg.value = '❌ ' + e.message }
}

// --- Init ---
onMounted(loadSites)
</script>

<template>
  <div>
    <!-- Header -->
    <div class="card card-pad" style="margin-bottom:16px;display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
      <div class="grow">
        <h3 style="margin:0;">📰 News Scraper & Content Management</h3>
        <p class="muted" style="font-size:11px;">Scrape artikel newsmaker.id → Upload ke WordPress dengan SEO optimization & financial backlinks</p>
      </div>
      <button class="btn" @click="openHistory" title="📊 Upload History">📊 History</button>
      <button class="btn" @click="openLog" title="📝 Activity Log">📝 Log</button>
      <button class="btn" @click="openBacklinksModal" title="🔗 Manage Backlinks">🔗 Backlinks</button>
    </div>

    <!-- Progress Bar -->
    <div v-if="progress && progress.stage !== 'done'" class="card card-pad" style="margin-bottom:16px;">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
        <span style="font-size:13px;">⏳ {{ progress.message || 'Memproses...' }}</span>
        <span style="font-size:12px;color:var(--muted,#64748b);">{{ progress.progress }}%</span>
      </div>
      <div style="width:100%;height:8px;background:var(--border,#e2e8f0);border-radius:4px;overflow:hidden;">
        <div :style="{width: progress.progress + '%', height:'100%', background:'linear-gradient(90deg,#3b82f6,#10b981)', borderRadius:'4px', transition:'width 0.3s'}"></div>
      </div>
      <div style="display:flex;justify-content:space-between;margin-top:4px;font-size:11px;color:var(--muted,#64748b);">
        <span>Stage: {{ progress.stage }}</span>
        <span v-if="progress.total">{{ progress.current }}/{{ progress.total }}</span>
      </div>
    </div>

    <!-- Message -->
    <div v-if="msg" class="alert" :class="msg.startsWith('✅') ? 'alert-success' : msg.startsWith('❌') ? 'alert-error' : 'alert-info'" style="margin-bottom:16px;">
      {{ msg }}
    </div>

    <!-- Loading / Error -->
    <div v-if="loading" class="empty skeleton">⏳ Memuat…</div>
    <div v-else-if="err" class="alert alert-error">{{ err }}</div>

    <template v-else>
      <!-- WordPress Sites -->
      <div class="card card-pad" style="margin-bottom:16px;">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">
          <h4 style="margin:0;">🌐 WordPress Sites</h4>
          <button class="btn btn-primary btn-sm" @click="openSiteForm(null)">➕ Add Site</button>
        </div>
        <div v-if="!sites.length" class="empty" style="padding:20px;">
          Belum ada WordPress site. Klik <b>Add Site</b> untuk menambah.
        </div>
        <div v-else class="table-wrap">
          <table class="tbl">
            <thead>
              <tr><th>Nama</th><th>API URL</th><th>Username</th><th>Aksi</th></tr>
            </thead>
            <tbody>
              <tr v-for="s in sites" :key="s.name">
                <td><b>{{ s.name }}</b></td>
                <td style="font-size:12px;max-width:300px;overflow:hidden;text-overflow:ellipsis;">{{ s.wp_url }}</td>
                <td>{{ s.username }}</td>
                <td style="white-space:nowrap;">
                  <button class="btn btn-sm" @click="openSiteForm(s)" title="✏️ Edit">✏️</button>
                  <button class="btn btn-sm" @click="testConnection(s)" title="🔌 Test">🔌</button>
                  <button class="btn btn-sm btn-danger" @click="deleteSite(s.name)" title="🗑 Hapus">🗑</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Scraper Controls -->
      <div class="card card-pad" style="margin-bottom:16px;">
        <h4 style="margin:0 0 12px;">🔍 Scrape & Upload</h4>
        <div class="row" style="gap:8px;flex-wrap:wrap;align-items:end;">
          <div class="field" style="min-width:200px;">
            <label>Target Site</label>
            <select class="select" v-model="selectedSite">
              <option value="">— Pilih Site —</option>
              <option v-for="s in siteNames" :key="s" :value="s">{{ s }}</option>
            </select>
          </div>
          <div class="field" style="min-width:100px;">
            <label>Halaman</label>
            <input class="input" type="number" v-model.number="scrapePages" min="1" max="20" style="width:70px;" />
          </div>
          <button class="btn btn-primary" :disabled="scrapeBusy || !selectedSite" @click="scrapeArticles">
            {{ scrapeBusy ? '⏳ Scraping...' : '🔍 Check Articles' }}
          </button>
          <button class="btn" :disabled="uploadBusy || !articles.length" @click="uploadToWP">
            {{ uploadBusy ? '⏳ Uploading...' : '📤 Upload to WordPress' }}
          </button>
        </div>

        <!-- SEO Settings -->
        <div style="margin-top:12px;padding-top:12px;border-top:1px solid var(--border,#e2e8f0);">
          <div class="row" style="gap:12px;flex-wrap:wrap;align-items:center;">
            <label style="display:flex;align-items:center;gap:4px;font-size:13px;">
              <input type="checkbox" v-model="settings.seo_optimize" /> 🔍 Auto-SEO
            </label>
            <label style="display:flex;align-items:center;gap:4px;font-size:13px;">
              <input type="checkbox" v-model="settings.backlinks" /> 🔗 Authority Backlinks
            </label>
            <div style="display:flex;align-items:center;gap:4px;font-size:13px;">
              Max:
              <input class="input" type="number" v-model.number="settings.max_backlinks" min="1" max="10" style="width:50px;" />
            </div>
            <div class="field" style="flex:1;min-width:250px;">
              <input class="input" v-model="settings.static_tags" placeholder="Static Tags (comma separated)" style="font-size:12px;" />
            </div>
          </div>
        </div>
      </div>

      <!-- Upload Result -->
      <div v-if="uploadResult" class="card card-pad" style="margin-bottom:16px;background:var(--success-bg,#f0fdf4);">
        <h4 style="margin:0 0 8px;">📊 Hasil Upload</h4>
        <div class="row" style="gap:16px;flex-wrap:wrap;">
          <div><span class="badge badge-green">✅ {{ uploadResult.new_posts }} Baru</span></div>
          <div><span class="badge badge-blue">🔄 {{ uploadResult.updated_posts }} Update</span></div>
          <div v-if="uploadResult.errors?.length"><span class="badge badge-red">❌ {{ uploadResult.errors.length }} Error</span></div>
        </div>
        <div v-if="uploadResult.errors?.length" style="margin-top:8px;">
          <details>
            <summary style="font-size:12px;cursor:pointer;">Lihat error</summary>
            <ul style="font-size:11px;margin:4px 0;padding-left:18px;">
              <li v-for="(e, i) in uploadResult.errors" :key="i">{{ e }}</li>
            </ul>
          </details>
        </div>
      </div>

      <!-- Scraped Articles -->
      <div v-if="articles.length" class="card card-pad" style="margin-bottom:16px;">
        <h4 style="margin:0 0 12px;">📄 Artikel Ditemukan ({{ articles.length }})</h4>
        <div class="table-wrap" style="max-height:400px;overflow-y:auto;">
          <table class="tbl">
            <thead>
              <tr><th>Judul</th><th>Kategori</th><th>Tanggal</th><th>Konten</th></tr>
            </thead>
            <tbody>
              <tr v-for="(a, i) in articles" :key="i">
                <td style="max-width:250px;"><b>{{ a.title }}</b></td>
                <td><span class="badge badge-purple">{{ a.category }}</span></td>
                <td style="white-space:nowrap;font-size:12px;">{{ a.publish_date }} {{ a.publish_time }}</td>
                <td style="font-size:11px;max-width:200px;overflow:hidden;text-overflow:ellipsis;">
                  {{ a.content ? a.content.substring(0, 100) + '...' : '⏳ Loading...' }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Duplicate Checker -->
      <div class="card card-pad" style="margin-bottom:16px;">
        <h4 style="margin:0 0 12px;">🔍 Duplicate Article Checker</h4>
        <div class="row" style="gap:8px;align-items:end;">
          <div class="field">
            <label>Site</label>
            <select class="select" v-model="dupSite">
              <option value="">— Pilih —</option>
              <option v-for="s in siteNames" :key="s" :value="s">{{ s }}</option>
            </select>
          </div>
          <button class="btn" :disabled="dupBusy || !dupSite" @click="checkDuplicates">
            {{ dupBusy ? '⏳ Checking...' : '🔍 Check Duplicates' }}
          </button>
        </div>
        <div v-if="duplicates.length" style="margin-top:12px;">
          <div class="table-wrap" style="max-height:300px;overflow-y:auto;">
            <table class="tbl">
              <thead>
                <tr><th>Judul</th><th>Jumlah</th><th>Post IDs</th><th>Aksi</th></tr>
              </thead>
              <tbody>
                <tr v-for="(d, i) in duplicates" :key="i">
                  <td style="max-width:300px;">{{ d.title }}</td>
                  <td><span class="badge badge-red">{{ d.count }}x</span></td>
                  <td style="font-size:11px;">{{ d.post_ids.join(', ') }}</td>
                  <td>
                    <button class="btn btn-sm btn-danger" @click="deleteDuplicate(d.post_ids)">
                      🗑 Delete Duplicates
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <div v-else-if="dupSite && !dupBusy && duplicates.length === 0" class="empty" style="padding:12px;">
          Klik "Check Duplicates" untuk mulai.
        </div>
      </div>
    </template>

    <!-- Modal: Add/Edit Site -->
    <Modal v-if="showSiteForm" :title="siteForm.name ? '✏️ Edit WordPress Site' : '➕ Add WordPress Site'" @close="showSiteForm = false">
      <div class="form-grid">
        <div class="field"><label>Site Name *</label><input class="input" v-model="siteForm.name" :disabled="!!siteForm.name" placeholder="My WordPress Site" /></div>
        <div class="field"><label>API URL (Posts) *</label><input class="input" v-model="siteForm.wp_url" placeholder="https://yoursite.com/wp-json/wp/v2/posts" /></div>
        <div class="field"><label>Media URL</label><input class="input" v-model="siteForm.wp_media_url" placeholder="https://yoursite.com/wp-json/wp/v2/media" /></div>
        <div class="field"><label>Username *</label><input class="input" v-model="siteForm.username" /></div>
        <div class="field"><label>App Password {{ siteForm.name ? '(kosong = tidak diubah)' : '*' }}</label>
          <input class="input" v-model="siteForm.app_password" type="password" placeholder="xxxx xxxx xxxx xxxx" />
        </div>
      </div>
      <div class="row" style="justify-content:flex-end;margin-top:12px;gap:8px;">
        <button class="btn" @click="showSiteForm = false">Batal</button>
        <button class="btn btn-primary" :disabled="busy || !siteForm.name || !siteForm.wp_url || !siteForm.username" @click="saveSite">💾 Simpan</button>
      </div>
    </Modal>

    <!-- Modal: Backlinks -->
    <Modal v-if="showBacklinks" title="🔗 Financial Authority Backlinks" @close="showBacklinks = false" style="max-width:800px;">
      <div style="margin-bottom:16px;">
        <h4 style="margin:0 0 8px;">Authority Sites ({{ Object.keys(authoritySites).length }})</h4>
        <div class="table-wrap" style="max-height:200px;overflow-y:auto;">
          <table class="tbl" style="font-size:12px;">
            <thead><tr><th>Nama</th><th>URL</th></tr></thead>
            <tbody>
              <tr v-for="(url, name) in authoritySites" :key="name">
                <td><b>{{ name }}</b></td>
                <td><a :href="url" target="_blank" rel="nofollow" style="font-size:11px;">{{ url }}</a></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <div>
        <h4 style="margin:0 0 8px;">Keyword Mapping ({{ Object.keys(keywordMapping).length }})</h4>
        <div class="table-wrap" style="max-height:200px;overflow-y:auto;">
          <table class="tbl" style="font-size:12px;">
            <thead><tr><th>Keyword</th><th>Target Site</th></tr></thead>
            <tbody>
              <tr v-for="(site, kw) in keywordMapping" :key="kw">
                <td>{{ kw }}</td>
                <td>{{ site }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="row" style="gap:8px;margin-top:12px;align-items:end;">
          <div class="field"><label>Keyword</label><input class="input" v-model="newKeyword" placeholder="emas" /></div>
          <div class="field"><label>Authority Site</label>
            <select class="select" v-model="newSiteName">
              <option value="">— Pilih —</option>
              <option v-for="(_, name) in authoritySites" :key="name" :value="name">{{ name }}</option>
            </select>
          </div>
          <button class="btn btn-primary" :disabled="busy || !newKeyword || !newSiteName" @click="saveKeywordMapping">➕ Add</button>
        </div>
      </div>
    </Modal>

    <!-- Modal: Upload History -->
    <Modal v-if="showHistory" title="📊 Upload History" @close="showHistory = false" style="max-width:800px;">
      <div class="row" style="gap:8px;margin-bottom:12px;flex-wrap:wrap;align-items:end;">
        <div class="field">
          <label style="font-size:11px;">Dari Tanggal</label>
          <input class="input" type="date" v-model="historyFilter.date_from" style="font-size:12px;" />
        </div>
        <div class="field">
          <label style="font-size:11px;">Sampai Tanggal</label>
          <input class="input" type="date" v-model="historyFilter.date_to" style="font-size:12px;" />
        </div>
        <div class="field">
          <label style="font-size:11px;">Aksi</label>
          <select class="select" v-model="historyFilter.action" style="font-size:12px;">
            <option value="">Semua</option>
            <option value="scrape">🔍 Scrape</option>
            <option value="upload">📤 Upload</option>
          </select>
        </div>
        <button class="btn btn-primary btn-sm" @click="loadHistory" :disabled="historyBusy">
          {{ historyBusy ? '⏳' : '🔍 Filter' }}
        </button>
      </div>
      <div v-if="!historyList.length" class="empty" style="padding:16px;">Tidak ada riwayat.</div>
      <div v-else class="table-wrap" style="max-height:400px;overflow-y:auto;">
        <table class="tbl" style="font-size:12px;">
          <thead><tr><th>Waktu</th><th>User</th><th>Aksi</th><th>Detail</th></tr></thead>
          <tbody>
            <tr v-for="(h, i) in historyList" :key="i">
              <td style="white-space:nowrap;">{{ h.date }} {{ h.time }}</td>
              <td>{{ h.user }}</td>
              <td>
                <span :class="h.action === 'upload' ? 'badge badge-blue' : 'badge badge-purple'">
                  {{ h.action === 'upload' ? '📤 Upload' : '🔍 Scrape' }}
                </span>
              </td>
              <td style="font-size:11px;">
                <template v-if="h.action === 'upload'">
                  {{ h.site }} — <span class="badge badge-green">{{ h.new_posts }} baru</span>
                  <span class="badge badge-blue">{{ h.updated_posts }} update</span>
                  <span v-if="h.errors" class="badge badge-red">{{ h.errors }} error</span>
                </template>
                <template v-else>
                  {{ h.pages }} halaman — <span class="badge badge-purple">{{ h.articles_found }} artikel</span>
                </template>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </Modal>

    <!-- Modal: Log -->
    <Modal v-if="showLog" title="📝 Activity Log" @close="showLog = false" style="max-width:700px;">
      <div v-if="!logs.length" class="empty" style="padding:16px;">Tidak ada log.</div>
      <div v-else class="table-wrap" style="max-height:400px;overflow-y:auto;">
        <table class="tbl" style="font-size:12px;">
          <thead><tr><th>Waktu</th><th>User</th><th>Pesan</th></tr></thead>
          <tbody>
            <tr v-for="(l, i) in logs" :key="i">
              <td style="white-space:nowrap;">{{ new Date(l.timestamp).toLocaleString('id-ID') }}</td>
              <td>{{ l.user }}</td>
              <td>{{ l.message }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div style="margin-top:8px;">
        <button class="btn btn-sm btn-danger" @click="clearLog">🗑 Clear Log</button>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
.row { display: flex; flex-wrap: wrap; }
.grow { flex: 1; min-width: 200px; }
</style>
