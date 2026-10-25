<script setup>
/**
 * Pengadaan / Purchase Order (v2.70.0) — dokumen pembelian yang terkontrol:
 * master Supplier → PO (rincian item) → penerimaan barang bertahap
 * (partial → closed). Kode mengikuti konvensi WaterView.
 */
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { useAuthStore } from '../stores/auth'
import { useStepupStore } from '../stores/stepup'
import Modal from '../components/Modal.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import PageHeader from '../components/PageHeader.vue'
import LoadingState from '../components/LoadingState.vue'
import ErrorState from '../components/ErrorState.vue'

const confirmRef = ref(null)
const ask = (message, opts) => confirmRef.value?.open(message, opts) ?? Promise.resolve(false)

const stepup = useStepupStore()
const auth = useAuthStore()
const isFinance = ['finance', 'admin'].includes(auth.role)

const loading = ref(true)
const err = ref('')
const msg = ref('')

const tab = ref('pos')            // 'pos' | 'suppliers'
const suppliers = ref([])
const orders = ref([])            // [{...po, total_amount}]
const summary = ref({})           // {open: {count, amount}, ...}
const detail = ref(null)          // PO detail saat modal terbuka
const selectedSupplierId = ref(null)

const STATUS_LABEL = { open: 'Menunggu Barang', partial: 'Diterima Sebagian', closed: 'Selesai', cancelled: 'Dibatalkan' }
const STATUS_BADGE = { open: 'badge-blue', partial: 'badge-orange', closed: 'badge-green', cancelled: 'badge-gray' }

const fmtRupiah = (n) => 'Rp ' + new Intl.NumberFormat('id-ID').format(Math.round(Number(n) || 0))
const fmtDate = (d) => {
  if (!d) return '-'
  const t = String(d).slice(0, 10).split('-')
  return t.length === 3 ? `${t[2]}/${t[1]}/${t[0]}` : d
}

// ---------------- Statistik kartu ----------------
const statOpen = computed(() => ({ ...(summary.value.open || { count: 0, amount: 0 }) }))
const statPartial = computed(() => ({ ...(summary.value.partial || { count: 0, amount: 0 }) }))
const statClosed = computed(() => ({ ...(summary.value.closed || { count: 0, amount: 0 }) }))

// ---------------- Modal PO baru ----------------
const showForm = ref(false)
const form = ref(null)
const suppliersActive = computed(() => suppliers.value.filter((s) => s.is_active))

function blankForm() {
  return { supplier_id: '', order_date: new Date().toISOString().slice(0, 10), notes: '', items: [{ description: '', qty: 1, satuan: 'unit', price: 0 }] }
}
const formTotal = computed(() => {
  if (!form.value) return 0
  const bad = form.value.items.some((it) => !String(it.description || '').trim() || Number(it.qty) < 1)
  const total = form.value.items.reduce((acc, it) => acc + Number(it.qty || 0) * Number(it.price || 0), 0)
  return bad ? null : total
})
function addItem() { form.value.items.push({ description: '', qty: 1, satuan: 'unit', price: 0 }) }
function removeItem(i) { form.value.items.splice(i, 1) }

function openForm() {
  form.value = blankForm()
  showForm.value = true
}
async function submitForm() {
  const f = form.value
  if (!f.supplier_id) { msg.value = '❌ Pilih supplier dulu'; return }
  if (formTotal.value === null) { msg.value = '❌ Lengkapi item (deskripsi & qty minimal 1)'; return }
  try {
    await api('/api/procurement/orders', {
      method: 'POST',
      body: JSON.stringify({
        supplier_id: Number(f.supplier_id), order_date: f.order_date,
        notes: f.notes, items: f.items.map((it) => ({
          description: it.description, qty: Number(it.qty), satuan: it.satuan, price: Number(it.price),
        })),
      }),
    })
    showForm.value = false
    showMsg('✅ PO dibuat — menunggu penerimaan barang')
    await load()
  } catch (e) {
    msg.value = `❌ ${e?.data?.error || e?.message || 'Gagal membuat PO'}`
  }
}

// ---------------- Detail & penerimaan ----------------
const showDetail = ref(false)
const receiveMode = ref(false)
const receiveForm = ref([])
const receiveValid = computed(() => {
  const tot = receiveForm.value.reduce((acc, r) => acc + Number(r.qty || 0), 0)
  const bad = receiveForm.value.some((r) => Number(r.qty || 0) < 0 || Number(r.qty || 0) > r.outstanding)
  return tot > 0 && !bad
})

async function openDetail(po) {
  try {
    detail.value = await api(`/api/procurement/orders/${po.id}`)
    showDetail.value = true
    receiveMode.value = false
  } catch (e) {
    msg.value = `❌ ${e?.data?.error || 'Gagal memuat detail PO'}`
  }
}
function startReceive() {
  receiveForm.value = (detail.value.items || []).map((it) => ({
    item_id: it.id, description: it.description, satuan: it.satuan,
    qty: 0, outstanding: it.outstanding, note: '',
  }))
  receiveMode.value = true
}
async function submitReceive() {
  const d = detail.value
  const entries = receiveForm.value
    .filter((r) => Number(r.qty) > 0)
    .map((r) => ({ item_id: r.item_id, qty: Number(r.qty), note: r.note }))
  if (!entries.length) return
  await stepup.require(async () => {
    await api(`/api/procurement/orders/${d.id}/receive`, {
      method: 'POST',
      body: JSON.stringify({ receipts: entries }),
    })
    showMsg(`✅ Penerimaan ${d.display_id} tercatat`)
    showDetail.value = false
    await load()
  }, `penerimaan barang ${d.display_id}`)
}

async function cancelPO() {
  const d = detail.value
  const reason = await ask(`Batalkan ${d.display_id}? Alasan wajib & tercatat di audit log.`, {
    title: 'Batalkan PO', danger: true, input: true, required: true,
    placeholder: 'Contoh: budget ditarik alokasinya',
  })
  if (reason === null || reason === false) return
  await stepup.require(async () => {
    await api(`/api/procurement/orders/${d.id}/cancel`, {
      method: 'POST', body: JSON.stringify({ reason }),
    })
    showMsg(`✅ ${d.display_id} dibatalkan`)
    showDetail.value = false
    await load()
  }, `pembatalan PO ${d.display_id}`)
}

// ---------------- Supplier ----------------
const supplierForm = ref(null)
const supplierEditId = ref(null)
const showSupplierModal = ref(false)

function openSupplier(s) {
  supplierEditId.value = s ? s.id : null
  supplierForm.value = s
    ? { name: s.name, category: s.category, contact_name: s.contact_name, phone: s.phone, address: s.address }
    : { name: '', category: '', contact_name: '', phone: '', address: '' }
  showSupplierModal.value = true
}
async function submitSupplier() {
  const s = supplierForm.value
  if (!String(s.name || '').trim()) { msg.value = '❌ Nama supplier wajib diisi'; return }
  const body = JSON.stringify(s)
  await stepup.require(async () => {
    if (supplierEditId.value === null) {
      await api('/api/procurement/suppliers', { method: 'POST', body })
      showMsg(`✅ Supplier "${s.name}" ditambahkan`)
    } else {
      await api(`/api/procurement/suppliers/${supplierEditId.value}`, { method: 'PUT', body })
      showMsg(`✅ Supplier "${s.name}" diperbarui`)
    }
    showSupplierModal.value = false
    selectedSupplierId.value = null
    await load()
  }, supplierEditId.value === null ? 'tambah supplier' : 'ubah supplier')
}
async function deactivateSupplier(s) {
  const ok = await ask(`Nonaktifkan supplier "${s.name}"? Data historis PO tetap utuh.`, {
    title: 'Nonaktifkan Supplier', confirmText: 'Nonaktifkan', danger: true,
  })
  if (!ok) return
  await stepup.require(async () => {
    await api(`/api/procurement/suppliers/${s.id}`, { method: 'DELETE' })
    showMsg(`✅ Supplier "${s.name}" dinonaktifkan`)
    selectedSupplierId.value = null
    await load()
  }, `nonaktifkan supplier ${s.name}`)
}

// ---------------- Data & utilitas ----------------
function showMsg(m) { msg.value = m; setTimeout(() => { msg.value = '' }, 5000) }

async function load() {
  const [s, o] = await Promise.all([
    api('/api/procurement/suppliers?all=1'),
    api('/api/procurement/orders'),
  ])
  suppliers.value = s.suppliers || []
  orders.value = o.orders || []
  summary.value = o.summary || {}
}

onMounted(async () => {
  try {
    await load()
  } catch (e) {
    err.value = e?.message || 'Gagal memuat data pengadaan'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div>
    <div v-if="msg" class="alert" :class="msg.startsWith('✅') ? 'alert-success' : 'alert-error'">{{ msg }}</div>

    <PageHeader icon="🛒" title="Pengadaan — Purchase Order"
                subtitle="Master supplier, PO barang, dan penerimaan bertahap dalam satu jejak dokumen">
      <button class="btn btn-primary" @click="openForm">➕ PO Baru</button>
      <button class="btn" :class="{ 'btn-primary': tab === 'suppliers' }" @click="tab = tab === 'pos' ? 'suppliers' : 'pos'">
        🏷️ Supplier
      </button>
    </PageHeader>

    <div v-if="loading"><LoadingState :rows="5" label="Memuat data pengadaan…" /></div>
    <div v-else-if="err"><ErrorState :message="err" @retry="load" /></div>
    <template v-else>
      <!-- Kartu statistik PO -->
      <div class="row" style="gap:12px;flex-wrap:wrap;margin-bottom:16px;">
        <div class="card card-pad grow" style="min-width:170px;">
          <div class="muted" style="font-size:12px;">⏳ Menunggu Barang</div>
          <div class="row" style="align-items:baseline;gap:8px;">
            <b style="font-size:24px;">{{ statOpen.count }}</b>
            <span class="muted" style="font-size:12px;">{{ fmtRupiah(statOpen.amount) }}</span>
          </div>
        </div>
        <div class="card card-pad grow" style="min-width:170px;">
          <div class="muted" style="font-size:12px;">📦 Diterima Sebagian</div>
          <div class="row" style="align-items:baseline;gap:8px;">
            <b style="font-size:24px;">{{ statPartial.count }}</b>
            <span class="muted" style="font-size:12px;">{{ fmtRupiah(statPartial.amount) }}</span>
          </div>
        </div>
        <div class="card card-pad grow" style="min-width:170px;">
          <div class="muted" style="font-size:12px;">✅ Selesai</div>
          <div class="row" style="align-items:baseline;gap:8px;">
            <b style="font-size:24px;">{{ statClosed.count }}</b>
            <span class="muted" style="font-size:12px;">{{ fmtRupiah(statClosed.amount) }}</span>
          </div>
        </div>
      </div>

      <!-- ========== TAB PURCHASE ORDER ========== -->
      <div v-if="tab === 'pos'" class="card">
        <div class="card-pad row" style="border-bottom:1px solid var(--border);">
          <b>🗂️ Daftar Purchase Order</b>
          <span class="badge badge-blue">{{ orders.length }}</span>
        </div>
        <div v-if="!orders.length" class="empty">Belum ada PO. Buat dokumen pertama dengan ➕ PO Baru.</div>
        <div v-for="p in orders" :key="p.id" class="cash-item">
          <div class="row" style="align-items:center;flex-wrap:wrap;gap:8px;">
            <div class="grow">
              <div class="row" style="gap:8px;align-items:center;">
                <b>{{ p.display_id }}</b>
                <span class="badge" :class="STATUS_BADGE[p.status] || 'badge-gray'">{{ STATUS_LABEL[p.status] || p.status }}</span>
              </div>
              <div class="muted" style="font-size:12px;margin-top:4px;">
                🗓️ {{ fmtDate(p.order_date) }} · 🏭 {{ p.supplier_name }} · ✍️ {{ p.created_by }}
              </div>
            </div>
            <div class="row" style="gap:8px;align-items:center;flex-wrap:wrap;">
              <b style="font-size:13px;">{{ fmtRupiah(p.total_amount) }}</b>
              <button class="btn btn-sm" @click="openDetail(p)">👁️ Detail</button>
            </div>
          </div>
        </div>
      </div>

      <!-- ========== TAB SUPPLIER ========== -->
      <div v-else class="card">
        <div class="card-pad row" style="border-bottom:1px solid var(--border);">
          <b>🏭 Master Supplier</b>
          <span class="badge badge-blue">{{ suppliers.filter((s) => s.is_active).length }} aktif</span>
          <button v-if="isFinance" class="btn btn-sm btn-primary" style="margin-left:auto;" @click="openSupplier(null)">➕ Supplier</button>
        </div>
        <div v-if="!suppliers.length" class="empty">Belum ada supplier. Tambahkan pemasok pertama.</div>
        <div v-for="s in suppliers" :key="s.id" class="cash-item"
             :style="!s.is_active ? 'opacity:.55;' : ''"
             @click="selectedSupplierId = s.id;">
          <div class="row" style="align-items:center;flex-wrap:wrap;gap:8px;">
            <div class="grow">
              <div class="row" style="gap:8px;align-items:center;">
                <b>{{ s.name }}</b>
                <span class="badge" :class="s.is_active ? 'badge-green' : 'badge-gray'">{{ s.is_active ? 'Aktif' : 'Nonaktif' }}</span>
              </div>
              <div class="muted" style="font-size:12px;margin-top:4px;">
                🗂️ {{ s.category || '-' }} · 👤 {{ s.contact_name || '-' }} · ☎️ {{ s.phone || '-' }}
              </div>
            </div>
            <div v-if="selectedSupplierId === s.id && isFinance" class="row" style="gap:6px;">
              <button class="btn btn-sm" @click.stop="openSupplier(s)">✏️ Edit</button>
              <button v-if="s.is_active" class="btn btn-sm btn-danger" @click.stop="deactivateSupplier(s)">🚫 Nonaktifkan</button>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- Modal PO Baru -->
    <Modal v-if="showForm" title="🛒 Purchase Order Baru" wide @close="showForm = false;">
      <div class="card-pad">
        <div class="row" style="gap:10px;flex-wrap:wrap;">
          <div class="field">
            <label>Supplier *</label>
            <select class="select" v-model="form.supplier_id">
              <option value="" disabled>— pilih supplier —</option>
              <option v-for="s in suppliersActive" :key="s.id" :value="s.id">{{ s.name }}</option>
            </select>
          </div>
          <div class="field">
            <label>Tanggal PO *</label>
            <input class="input" type="date" v-model="form.order_date" />
          </div>
          <div class="field grow" style="min-width:180px;">
            <label>Catatan</label>
            <input class="input" v-model="form.notes" placeholder="rekening/keterangan…" maxlength="500" />
          </div>
        </div>
        <b style="display:block;margin:14px 0 6px;">🧾 Rincian Item</b>
        <div v-for="(it, i) in form.items" :key="i" class="row" style="gap:6px;flex-wrap:nowrap;margin-bottom:6px;align-items:flex-end;">
          <div class="field grow" style="min-width:140px;">
            <label>Deskripsi</label>
            <input class="input" v-model="it.description" :placeholder="`Item #${i + 1}`" maxlength="200" />
          </div>
          <div class="field" style="width:80px;">
            <label>Qty</label>
            <input class="input" type="number" v-model.number="it.qty" min="1" />
          </div>
          <div class="field" style="width:110px;">
            <label>Satuan</label>
            <select class="select" v-model="it.satuan">
              <option v-for="s in ['unit', 'set', 'pcs', 'dus', 'box', 'kaleng', 'botol', 'galon', 'karung', 'liter', 'kg', 'paket']" :key="s" :value="s">{{ s }}</option>
            </select>
          </div>
          <div class="field" style="width:130px;">
            <label>Harga/unit</label>
            <input class="input" type="number" v-model.number="it.price" min="0" />
          </div>
          <button class="btn btn-sm btn-danger" title="Hapus item" @click="removeItem(i)">🗑️</button>
        </div>
        <button class="btn btn-sm" @click="addItem">➕ Item</button>
        <div class="row" style="justify-content:flex-end;gap:10px;margin-top:10px;">
          <b>Total:</b>
          <span v-if="formTotal !== null" class="total-amount">{{ fmtRupiah(formTotal) }}</span>
          <span v-else class="muted">— lengkapi item —</span>
        </div>
        <div class="row" style="justify-content:flex-end;gap:8px;margin-top:12px;">
          <button class="btn" @click="showForm = false;">Batal</button>
          <button class="btn btn-primary" @click="submitForm">💾 Simpan PO</button>
        </div>
      </div>
    </Modal>

    <!-- Modal Detail PO -->
    <Modal v-if="showDetail && detail" :title="`📄 ${detail.display_id} — ${detail.supplier_name}`" wide @close="showDetail = false;">
      <div class="card-pad">
        <div class="row" style="gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:10px;">
          <span class="badge" :class="STATUS_BADGE[detail.status] || 'badge-gray'">{{ STATUS_LABEL[detail.status] }}</span>
          <span class="muted" style="font-size:12px;">🗓️ {{ fmtDate(detail.order_date) }} · ✍️ {{ detail.created_by }}</span>
        </div>
        <div v-if="detail.notes" class="muted" style="font-size:12px;margin-bottom:10px;">📝 {{ detail.notes }}</div>
        <table class="table">
          <thead>
            <tr><th>Deskripsi</th><th style="text-align:center;">Qty</th><th>Satuan</th><th style="text-align:right;">Harga</th><th style="text-align:center;">Diterima</th><th style="text-align:center;">Sisa</th></tr>
          </thead>
          <tbody>
            <tr v-for="it in detail.items" :key="it.id">
              <td>{{ it.description }}</td>
              <td style="text-align:center;">{{ it.qty }}</td>
              <td>{{ it.satuan }}</td>
              <td style="text-align:right;">{{ fmtRupiah(it.price) }}</td>
              <td style="text-align:center;">{{ it.received }}</td>
              <td style="text-align:center;"><b>{{ it.outstanding }}</b></td>
            </tr>
          </tbody>
        </table>
        <div class="row" style="justify-content:flex-end;margin-top:10px;">
          <b>Total: {{ fmtRupiah(detail.total_amount) }}</b>
        </div>
        <template v-if="detail.receipts && detail.receipts.length">
          <b style="display:block;margin:16px 0 6px;">📥 Riwayat Penerimaan</b>
          <div v-for="r in detail.receipts" :key="r.id" class="muted" style="font-size:12px;margin-bottom:4px;">
            · {{ r.received_by }} menerima {{ r.qty }} ({{ fmtDate(r.received_at) }}){{ r.note ? ' — ' + r.note : '' }}
          </div>
        </template>
        <div v-if="detail.cancel_reason" class="alert alert-error" style="margin-top:10px;">
          Dibatalkan oleh {{ detail.cancelled_by }}: {{ detail.cancel_reason }}
        </div>
        <div class="row" style="justify-content:flex-end;gap:8px;margin-top:14px;">
          <button v-if="isFinance && ['open', 'partial'].includes(detail.status)" class="btn" @click="cancelPO">✖ Batalkan</button>
          <button v-if="['open', 'partial'].includes(detail.status)" class="btn btn-primary" @click="startReceive">📦 Catat Penerimaan</button>
          <button class="btn" @click="showDetail = false;">Tutup</button>
        </div>
      </div>
    </Modal>

    <!-- Modal Penerimaan -->
    <Modal v-if="showDetail && receiveMode" title="📦 Catat Penerimaan Barang" wide @close="receiveMode = false;">
      <div class="card-pad">
        <div class="muted" style="font-size:12px;margin-bottom:10px;">
          Masukkan qty yang benar-benar diterima per item (tidak boleh melebihi sisa).
          PO otomatis <b>partial</b> saat sebagian terima dan <b>closed</b> saat semua item penuh.
        </div>
        <div v-for="r in receiveForm" :key="r.item_id" class="row" style="gap:8px;margin-bottom:8px;align-items:flex-end;">
          <div class="field grow" style="min-width:150px;">
            <label>Item</label>
            <div>{{ r.description }}</div>
          </div>
          <div class="field" style="width:100px;">
            <label>Sisa</label>
            <div><b>{{ r.outstanding }}</b> {{ r.satuan }}</div>
          </div>
          <div class="field" style="width:110px;">
            <label>Qty terima</label>
            <input class="input" type="number" v-model.number="r.qty" :min="0" :max="r.outstanding" />
          </div>
          <div class="field grow" style="min-width:150px;">
            <label>Catatan</label>
            <input class="input" v-model="r.note" placeholder="waybill / kondisi barang…" maxlength="300" />
          </div>
        </div>
        <div class="row" style="justify-content:flex-end;gap:8px;margin-top:12px;">
          <button class="btn" @click="receiveMode = false;">Batal</button>
          <button class="btn btn-primary" :disabled="!receiveValid" @click="submitReceive">💾 Simpan Penerimaan</button>
        </div>
      </div>
    </Modal>

    <!-- Modal Supplier -->
    <Modal v-if="showSupplierModal" :title="supplierEditId === null ? '🏭 Supplier Baru' : '✏️ Edit Supplier'" @close="showSupplierModal = false;">
      <div class="card-pad">
        <div class="row" style="gap:10px;flex-wrap:wrap;">
          <div class="field grow" style="min-width:200px;">
            <label>Nama *</label>
            <input class="input" v-model="supplierForm.name" maxlength="150" />
          </div>
          <div class="field" style="width:180px;">
            <label>Kategori</label>
            <input class="input" v-model="supplierForm.category" placeholder="bahan bangunan / ATK…" maxlength="100" />
          </div>
        </div>
        <div class="row" style="gap:10px;flex-wrap:wrap;">
          <div class="field" style="width:180px;">
            <label>Nama PIC</label>
            <input class="input" v-model="supplierForm.contact_name" maxlength="100" />
          </div>
          <div class="field grow" style="min-width:150px;">
            <label>Telepon</label>
            <input class="input" v-model="supplierForm.phone" maxlength="50" />
          </div>
        </div>
        <div class="field" style="margin-top:8px;">
          <label>Alamat</label>
          <input class="input" v-model="supplierForm.address" maxlength="300" />
        </div>
        <div class="row" style="justify-content:flex-end;gap:8px;margin-top:12px;">
          <button class="btn" @click="showSupplierModal = false;">Batal</button>
          <button class="btn btn-primary" @click="submitSupplier">💾 Simpan</button>
        </div>
      </div>
    </Modal>

    <ConfirmDialog ref="confirmRef" />
  </div>
</template>

<style scoped>
.total-amount { font-size: 18px; font-weight: 700; }
.table { width: 100%; border-collapse: collapse; font-size: 13px; }
.table th, .table td { padding: 6px 8px; border-bottom: 1px solid var(--border, #e5e7eb); }
.table th { text-align: left; font-weight: 600; }
</style>
