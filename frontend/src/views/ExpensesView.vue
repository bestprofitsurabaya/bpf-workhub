<script setup>
/**
 * Rekap Pengeluaran (v2.71.0) — laporan bulanan lintas modul:
 * Pembelian Barang (PO diterima) + Kasbon BBM (dana cair) per bulan/cabang.
 * Sumber tak terukur (air minum tanpa harga, overtime tanpa nominal) sengaja
 * di luar cakupan — lihat docstring routes_expense.py.
 */
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { useAuthStore } from '../stores/auth'
import PageHeader from '../components/PageHeader.vue'
import LoadingState from '../components/LoadingState.vue'
import ErrorState from '../components/ErrorState.vue'

const auth = useAuthStore()
const loading = ref(true)
const err = ref('')
const msg = ref('')

const year = ref(new Date().getFullYear())
const branch = ref(auth.role === 'admin' ? 'ALL' : 'SBY')
const years = computed(() => {
  const y = new Date().getFullYear()
  return [y, y - 1, y - 2, y - 3]
})
const branches = ref([])

const display = ref(null)      // {name, po[12], kasbon[12], total[12]}
const perBranch = ref([])      // untuk tabel ringkas cabang saat scope ALL
const totals = ref({ po: 0, kasbon: 0 })
const grandTotal = ref(0)
const errors = ref({})         // {CODE: pesan}

const CATEGORY_LABEL = { po: '🛒 Pembelian Barang (PO diterima)', kasbon: '💵 Kasbon BBM (dana cair)' }

const fmtRupiah = (n) => 'Rp ' + new Intl.NumberFormat('id-ID').format(Math.round(Number(n) || 0))
const NAMA_BULAN = ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des']

const rowsBulan = computed(() =>
  NAMA_BULAN.map((b, i) => ({
    label: b,
    po: display.value?.po?.[i] ?? 0,
    kasbon: display.value?.kasbon?.[i] ?? 0,
    total: display.value?.total?.[i] ?? 0,
  }))
)

const pesanErrCabang = computed(() =>
  Object.entries(errors.value).map(([c, e]) => `${c}: ${e}`).join(' · '))

async function load() {
  loading.value = true
  err.value = ''
  try {
    const d = await api(`/api/expenses/recap?year=${year.value}&branch=${branch.value}`)
    display.value = d.display || { name: '—', po: [], kasbon: [], total: [] }
    totals.value = d.totals || { po: 0, kasbon: 0 }
    grandTotal.value = d.grand_total || 0
    branches.value = d.branches || []
    perBranch.value = branch.value === 'ALL' ? Object.entries(d.per_branch || {})
      .map(([code, v]) => ({
        code, name: v.name,
        po: v.po.reduce((a, b) => a + b, 0),
        kasbon: v.kasbon.reduce((a, b) => a + b, 0),
        total: v.total.reduce((a, b) => a + b, 0),
      })) : []
    errors.value = d.errors || {}
  } catch (e) {
    err.value = e?.data?.error || e?.message || 'Gagal memuat rekap pengeluaran'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <div v-if="msg" class="alert" :class="msg.startsWith('✅') ? 'alert-success' : 'alert-error'">{{ msg }}</div>

    <PageHeader icon="📊" title="Rekap Pengeluaran"
                subtitle="Gabungan biaya terukur: pembelian barang (PO diterima) & kasbon BBM — air minum/overtime belum punya nominal di sistem">
      <div class="field" style="width:110px;">
        <select class="select" v-model.number="year" @change="load">
          <option v-for="y in years" :key="y" :value="y">{{ y }}</option>
        </select>
      </div>
      <div class="field" style="width:200px;">
        <select class="select" v-model="branch" @change="load">
          <option value="ALL">🏭 Semua Cabang</option>
          <option v-for="b in branches" :key="b.code" :value="b.code">{{ b.name }}</option>
        </select>
      </div>
    </PageHeader>

    <div v-if="loading"><LoadingState :rows="5" label="Memuat rekap pengeluaran…" /></div>
    <div v-else-if="err"><ErrorState :message="err" @retry="load" /></div>
    <template v-else>
      <!-- Kartu total tahun berjalan -->
      <div class="row" style="gap:12px;flex-wrap:wrap;margin-bottom:16px;">
        <div class="card card-pad grow" style="min-width:200px;">
          <div class="muted" style="font-size:12px;">{{ CATEGORY_LABEL.po }}</div>
          <b style="font-size:22px;">{{ fmtRupiah(totals.po) }}</b>
        </div>
        <div class="card card-pad grow" style="min-width:200px;">
          <div class="muted" style="font-size:12px;">{{ CATEGORY_LABEL.kasbon }}</div>
          <b style="font-size:22px;">{{ fmtRupiah(totals.kasbon) }}</b>
        </div>
        <div class="card card-pad grow" style="min-width:200px;background:var(--primary-soft, rgba(25,103,210,.08));">
          <div class="muted" style="font-size:12px;">Σ Total Pengeluaran {{ year }}</div>
          <b style="font-size:24px;">{{ fmtRupiah(grandTotal) }}</b>
        </div>
      </div>

      <div v-if="pesanErrCabang" class="alert alert-error" style="margin-bottom:12px;">
        ⚠️ Sebagian cabang gagal dihitung: {{ pesanErrCabang }}
      </div>

      <!-- Tabel bulanan -->
      <div class="card" style="margin-bottom:16px;">
        <div class="card-pad row" style="border-bottom:1px solid var(--border);">
          <b>📅 Per Bulan — {{ display?.name || '—' }} · {{ year }}</b>
        </div>
        <table class="table">
          <thead>
            <tr>
              <th>Bulan</th>
              <th style="text-align:right;">Pembelian Barang</th>
              <th style="text-align:right;">Kasbon BBM</th>
              <th style="text-align:right;">Total</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in rowsBulan" :key="r.label" :class="{ 'bulan-aktif': r.total > 0 }">
              <td>{{ r.label }}</td>
              <td style="text-align:right;">{{ r.po ? fmtRupiah(r.po) : '—' }}</td>
              <td style="text-align:right;">{{ r.kasbon ? fmtRupiah(r.kasbon) : '—' }}</td>
              <td style="text-align:right;"><b>{{ r.total ? fmtRupiah(r.total) : '—' }}</b></td>
            </tr>
            <tr style="font-weight:700;">
              <td>Total {{ year }}</td>
              <td style="text-align:right;">{{ fmtRupiah(totals.po) }}</td>
              <td style="text-align:right;">{{ fmtRupiah(totals.kasbon) }}</td>
              <td style="text-align:right;">{{ fmtRupiah(grandTotal) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Ringkas per cabang (hanya saat scope Semua Cabang) -->
      <div v-if="perBranch.length" class="card">
        <div class="card-pad row" style="border-bottom:1px solid var(--border);">
          <b>🏭 Per Cabang — {{ year }}</b>
        </div>
        <table class="table">
          <thead>
            <tr>
              <th>Cabang</th>
              <th style="text-align:right;">Pembelian Barang</th>
              <th style="text-align:right;">Kasbon BBM</th>
              <th style="text-align:right;">Total</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="b in perBranch" :key="b.code">
              <td><b>{{ b.code }}</b> — {{ b.name }}</td>
              <td style="text-align:right;">{{ fmtRupiah(b.po) }}</td>
              <td style="text-align:right;">{{ fmtRupiah(b.kasbon) }}</td>
              <td style="text-align:right;"><b>{{ fmtRupiah(b.total) }}</b></td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<style scoped>
.table { width: 100%; border-collapse: collapse; font-size: 13px; }
.table th, .table td { padding: 7px 10px; border-bottom: 1px solid var(--border, #e5e7eb); }
.table th { text-align: left; font-weight: 600; }
.bulan-aktif td { background: var(--primary-soft, rgba(25,103,210,.05)); }
</style>
