<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

const brandIcon = '/static/icon-192.png'
const PENDIDIKAN = ['SMA', 'SMK', 'MA', 'D3', 'D4', 'S1', 'S2', 'S3']
const DRAFT_KEY = 'bpf_fw_draft_v1'
const STEPS = ['Data Diri', 'Kontak & Referensi', 'Identitas']

// Cabang tujuan diambil dari link (?cabang=MLG). Server tetap memvalidasi
// terhadap master branches dan menolak nilai asing (jatuh ke SBY).
const linkParams = new URLSearchParams(window.location.search)
const linkBranch = (linkParams.get('cabang') || linkParams.get('branch') || '').trim().toUpperCase()
// v2.82.0: token form milik cabang. Tanpa token yang cocok, isian tidak bisa
// dikirim atas nama cabang tersebut (anti tukar/mix antar cabang).
const linkToken = (linkParams.get('t') || linkParams.get('token') || '').trim()
const branchLabel = ref('')
const resolvedBranch = ref(linkBranch)
// v2.86.0: status keabsahan tautan. 'loading' → 'ok' (tautan sah) atau
// 'invalid' (ditolak server) — tautan tidak sah dirender sebagai halaman
// penolakan penuh, TANPA form dan TANPA branding cabang mana pun.
const linkState = ref('loading')
const linkError = ref('')

// Kode provinsi pada 2 digit pertama NIK.
const PROVINSI = {
  11: 'Aceh', 12: 'Sumatera Utara', 13: 'Sumatera Barat', 14: 'Riau', 15: 'Jambi',
  16: 'Sumatera Selatan', 17: 'Bengkulu', 18: 'Lampung', 19: 'Bangka Belitung',
  21: 'Kepulauan Riau', 31: 'DKI Jakarta', 32: 'Jawa Barat', 33: 'Jawa Tengah',
  34: 'DI Yogyakarta', 35: 'Jawa Timur', 36: 'Banten', 51: 'Bali',
  52: 'Nusa Tenggara Barat', 53: 'Nusa Tenggara Timur', 61: 'Kalimantan Barat',
  62: 'Kalimantan Tengah', 63: 'Kalimantan Selatan', 64: 'Kalimantan Timur',
  65: 'Kalimantan Utara', 71: 'Sulawesi Utara', 72: 'Sulawesi Tengah',
  73: 'Sulawesi Selatan', 74: 'Sulawesi Tenggara', 75: 'Gorontalo',
  76: 'Sulawesi Barat', 81: 'Maluku', 82: 'Maluku Utara', 91: 'Papua',
  92: 'Papua Barat', 93: 'Papua Selatan', 94: 'Papua Tengah',
  95: 'Papua Pegunungan', 96: 'Papua Barat Daya',
}

const form = reactive({
  nik: '', nama: '', pendidikan: '',
  referrer_id: '', referensi_text: '', no_hp: '',
})
const referrers = ref([])
const metaLoading = ref(true)
const ktpFile = ref(null)
const ktpLabel = ref('')
const ktpPreview = ref('')
const error = ref('')
const submitting = ref(false)
// v2.85.0: persetujuan pemrosesan data pribadi (UU PDP) wajib sebelum kirim.
const consent = ref(false)
const done = ref(null)
const step = ref(0)
const restored = ref(false)
const nikCheck = reactive({ state: 'idle', exists: false })

const manualRef = computed(() => form.referrer_id === 'manual')
const pct = computed(() => Math.round(((step.value) / STEPS.length) * 100))

// --- NIK: baca jenis kelamin, tanggal lahir, dan provinsi ---
const nikInfo = computed(() => {
  if (form.nik.length !== 16) return null
  const province = PROVINSI[Number(form.nik.slice(0, 2))] || ''
  let dd = Number(form.nik.slice(6, 8))
  let mm = Number(form.nik.slice(8, 10))
  const yy = Number(form.nik.slice(10, 12))
  const female = mm > 40
  if (female) mm -= 40
  const year = yy > 26 ? 1900 + yy : 2000 + yy
  const date = new Date(year, mm - 1, dd)
  const validDate = dd >= 1 && dd <= 31 && mm >= 1 && mm <= 12
    && date.getDate() === dd && date.getMonth() === mm - 1
  if (!validDate) return { valid: false, province }
  const today = new Date()
  let age = today.getFullYear() - year
  if (today.getMonth() < mm - 1 || (today.getMonth() === mm - 1 && today.getDate() < dd)) age -= 1
  return {
    valid: true,
    female,
    gender: female ? 'Perempuan' : 'Laki-laki',
    birth: date.toLocaleDateString('id-ID', { day: '2-digit', month: 'long', year: 'numeric' }),
    province,
    age,
    warning: age < 15 || age > 70 ? `Usia terbaca ${age} tahun — pastikan NIK sesuai KTP.` : '',
  }
})

// --- HP: terima 08…, 8…, +62…, 62… dan tampilkan bentuk baku ---
function normalizeHp(value) {
  let digits = String(value || '').replace(/\D/g, '')
  if (digits.startsWith('62')) digits = '0' + digits.slice(2)
  else if (digits.startsWith('8')) digits = '0' + digits
  return digits
}
const hpInfo = computed(() => {
  const hp = normalizeHp(form.no_hp)
  return { hp, valid: /^08\d{8,12}$/.test(hp) }
})

function onNik(event) {
  form.nik = String(event.target.value || '').replace(/\D/g, '').slice(0, 16)
}
function onHpBlur() {
  if (form.no_hp) form.no_hp = normalizeHp(form.no_hp)
}
function onNamaBlur() {
  form.nama = String(form.nama || '').replace(/\s+/g, ' ').trim()
}

// --- Cek NIK duplikat langsung (debounce) ---
let checkTimer = null
function resetNikCheck() {
  nikCheck.state = 'idle'
  nikCheck.exists = false
}
watch(() => form.nik, (nik) => {
  clearTimeout(checkTimer)
  resetNikCheck()
  if (nik.length !== 16 || !nikInfo.value?.valid) return
  nikCheck.state = 'checking'
  checkTimer = setTimeout(async () => {
    try {
      const response = await fetch(`/api/first-work/check-nik?nik=${nik}`, {
        headers: { Accept: 'application/json' },
      })
      const data = await response.json()
      if (form.nik !== nik) return
      if (data?.status === 'error') { resetNikCheck(); return }
      nikCheck.exists = !!data.exists
      nikCheck.state = data.exists ? 'taken' : 'free'
    } catch {
      if (form.nik === nik) resetNikCheck()
    }
  }, 450)
})

// --- Draf otomatis supaya pengisian tidak hilang ---
function saveDraft() {
  try {
    localStorage.setItem(DRAFT_KEY, JSON.stringify({ ...form, step: step.value, saved_at: Date.now() }))
  } catch { /* localStorage penuh / private mode */ }
}
function clearDraft() {
  try { localStorage.removeItem(DRAFT_KEY) } catch { /* noop */ }
}
function restoreDraft() {
  try {
    const raw = localStorage.getItem(DRAFT_KEY)
    if (!raw) return
    const draft = JSON.parse(raw)
    const hasData = draft && (draft.nik || draft.nama || draft.no_hp || draft.pendidikan || draft.referensi_text)
    if (!hasData) return
    Object.assign(form, {
      nik: String(draft.nik || '').slice(0, 16),
      nama: draft.nama || '',
      pendidikan: draft.pendidikan || '',
      referrer_id: draft.referrer_id || '',
      referensi_text: draft.referensi_text || '',
      no_hp: draft.no_hp || '',
    })
    step.value = Math.min(Number(draft.step) || 0, STEPS.length - 1)
    restored.value = true
  } catch { /* draf rusak diabaikan */ }
}
watch(form, saveDraft, { deep: true })
watch(step, saveDraft)

async function loadReferrers() {
  try {
    const params = new URLSearchParams()
    if (linkBranch) params.set('cabang', linkBranch)
    if (linkToken) params.set('t', linkToken)
    const query = params.toString() ? `?${params.toString()}` : ''
    const response = await fetch('/api/first-work/referrers' + query, { headers: { Accept: 'application/json' } })
    const data = await response.json()
    if (!response.ok) {
      // v2.86.0: tautan ditolak server (token salah/kosong, cabang tak dikenal)
      // → halaman penolakan penuh, bukan form dengan branding default.
      linkState.value = 'invalid'
      linkError.value = data.error || 'Tautan form tidak valid untuk cabang ini.'
      referrers.value = []
      return
    }
    referrers.value = data.referrers || []
    branchLabel.value = data.branch_name || ''
    resolvedBranch.value = data.branch || linkBranch
    linkState.value = 'ok'
  } catch {
    // Koneksi gagal — tidak bisa memastikan tautan sah; jangan tampilkan form.
    linkState.value = 'invalid'
    linkError.value = 'Gagal memuat data cabang. Periksa koneksi internet lalu muat ulang halaman.'
    referrers.value = []
  } finally {
    metaLoading.value = false
  }
}

// ============================================================
// v2.87.0 — SCAN KTP DI PERANGKAT (P1/P2)
// Foto miring diluruskan lewat 4 titik sudut (perspective transform),
// kontras dinaikkan, lalu kualitas diperiksa (kabur / pantulan / gelap).
// Semua diproses di HP pengguna — tidak ada unggahan tambahan dan tidak
// memakai layanan pihak ketiga (data KTP tidak keluar dari perangkat
// sebelum dikirim ke server BPF).
// ============================================================
const ktpScanned = ref(false)
const ocrBusy = ref(false)
const ocrMsg = ref('')
const ocrNotice = ref('')
const scanCanvas = ref(null)
const scanBox = ref(null)
const scan = reactive({
  show: false, mode: 'edit', busy: false,
  url: '', bitmap: null, natural: { w: 0, h: 0 },
  points: [], warnings: [], resultUrl: '', resultBlob: null,
  fileName: 'ktp.jpg', dragging: -1,
})

function revokeUrl(url) {
  try { if (url) URL.revokeObjectURL(url) } catch { /* noop */ }
}

// Muat gambar dengan orientasi EXIF diterapkan (foto kamera sering miring 90°).
function loadBitmap(file) {
  return new Promise((resolve, reject) => {
    if (window.createImageBitmap) {
      createImageBitmap(file, { imageOrientation: 'from-image' })
        .then(resolve)
        .catch(() => createImageBitmap(file).then(resolve).catch(() => imageFallback(file, resolve, reject)))
      return
    }
    imageFallback(file, resolve, reject)
  })
}

function imageFallback(file, resolve, reject) {
  const url = URL.createObjectURL(file)
  const img = new Image()
  img.onload = () => { URL.revokeObjectURL(url); resolve(img) }
  img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('Gambar tidak bisa dibaca')) }
  img.src = url
}

// Kompres foto (dipakai untuk PDF/passthrough & tombol "Foto asli").
function compressImage(file) {
  return new Promise((resolve) => {
    if (!file.type.startsWith('image/')) { resolve(file); return }
    loadBitmap(file).then((image) => {
      const maxSide = 1600
      const scale = Math.min(1, maxSide / Math.max(image.width, image.height))
      const canvas = document.createElement('canvas')
      canvas.width = Math.max(1, Math.round(image.width * scale))
      canvas.height = Math.max(1, Math.round(image.height * scale))
      canvas.getContext('2d').drawImage(image, 0, 0, canvas.width, canvas.height)
      if (image.close) image.close()
      canvas.toBlob((blob) => {
        if (!blob) { resolve(file); return }
        const name = file.name.replace(/\.[^.]+$/, '') + '.jpg'
        resolve(new File([blob], name, { type: 'image/jpeg' }))
      }, 'image/jpeg', 0.85)
    }).catch(() => resolve(file))
  })
}

async function pickKtp(event) {
  error.value = ''
  const original = event.target.files?.[0]
  event.target.value = ''
  if (!original) return
  if (original.size > 12 * 1024 * 1024) {
    error.value = 'Ukuran file maksimal 12 MB.'
    return
  }
  if (!original.type.startsWith('image/') && original.type !== 'application/pdf') {
    error.value = 'File KTP harus berupa JPG, PNG, atau PDF.'
    return
  }
  // PDF tidak bisa di-warp di browser — kirim apa adanya (dinormalisasi server).
  if (original.type === 'application/pdf') {
    if (original.size > 5 * 1024 * 1024) {
      error.value = 'Ukuran PDF melebihi 5 MB.'
      return
    }
    setKtpFile(original, false)
    return
  }
  try {
    const bitmap = await loadBitmap(original)
    openScan(bitmap, original)
  } catch (e) {
    error.value = e.message || 'Foto tidak bisa dibaca. Coba file lain.'
  }
}

function setKtpFile(file, scanned) {
  revokeUrl(ktpPreview.value)
  ktpFile.value = file
  ktpPreview.value = file.type.startsWith('image/') ? URL.createObjectURL(file) : ''
  ktpLabel.value = `${file.name} · ${Math.max(1, Math.round(file.size / 1024))} KB`
  ktpScanned.value = scanned
}

function openScan(bitmap, file) {
  closeScan(true)
  scan.show = true
  scan.mode = 'edit'
  scan.busy = false
  scan.bitmap = bitmap
  scan.natural = { w: bitmap.width, h: bitmap.height }
  // Default: sedikit di dalam tepi foto.
  scan.points = [
    { x: 0.06, y: 0.09 }, { x: 0.94, y: 0.09 },
    { x: 0.94, y: 0.91 }, { x: 0.06, y: 0.91 },
  ]
  scan.warnings = []
  scan.resultBlob = null
  scan.resultUrl = ''
  scan.fileName = file?.name || 'ktp.jpg'
  scan.url = ''
  nextTick(drawScanEditor)
}

function drawScanEditor() {
  const canvas = scanCanvas.value
  if (!canvas || !scan.bitmap) return
  const maxW = Math.min(380, Math.max(220, window.innerWidth - 92))
  const ratio = scan.natural.h / Math.max(1, scan.natural.w)
  canvas.width = Math.round(maxW)
  canvas.height = Math.max(120, Math.round(maxW * ratio))
  const ctx = canvas.getContext('2d')
  ctx.drawImage(scan.bitmap, 0, 0, canvas.width, canvas.height)
}

function startDrag(index, event) {
  event.preventDefault()
  scan.dragging = index
  window.addEventListener('pointermove', onDragMove, { passive: false })
  window.addEventListener('pointerup', endDrag)
  window.addEventListener('pointercancel', endDrag)
}

function onDragMove(event) {
  if (scan.dragging < 0 || !scanBox.value) return
  event.preventDefault()
  const rect = scanBox.value.getBoundingClientRect()
  const x = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width))
  const y = Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height))
  scan.points[scan.dragging] = { x, y }
}

function endDrag() {
  scan.dragging = -1
  window.removeEventListener('pointermove', onDragMove)
  window.removeEventListener('pointerup', endDrag)
  window.removeEventListener('pointercancel', endDrag)
}

// Urutkan 4 titik: TL, TR, BR, BL (berdasarkan sudut dari pusat).
function orderCorners(points) {
  const cx = points.reduce((s, p) => s + p.x, 0) / 4
  const cy = points.reduce((s, p) => s + p.y, 0) / 4
  const sorted = points.map((p) => ({ ...p }))
    .sort((a, b) => Math.atan2(a.y - cy, a.x - cx) - Math.atan2(b.y - cy, b.x - cx))
  let start = 0
  let best = Infinity
  sorted.forEach((p, i) => {
    const sum = p.x + p.y
    if (sum < best) { best = sum; start = i }
  })
  return [...sorted.slice(start), ...sorted.slice(0, start)]
}

// Selesaikan homografi (dest → src) dengan eliminasi Gauss.
function solveHomography(src, dst) {
  const A = []
  const b = []
  for (let i = 0; i < 4; i += 1) {
    const { x, y } = dst[i]
    const { x: u, y: v } = src[i]
    A.push([x, y, 1, 0, 0, 0, -x * u, -y * u]); b.push(u)
    A.push([0, 0, 0, x, y, 1, -x * v, -y * v]); b.push(v)
  }
  const n = 8
  for (let col = 0; col < n; col += 1) {
    let piv = col
    for (let r = col + 1; r < n; r += 1) {
      if (Math.abs(A[r][col]) > Math.abs(A[piv][col])) piv = r
    }
    if (Math.abs(A[piv][col]) < 1e-9) return null
    if (piv !== col) {
      const tmp = A[col]; A[col] = A[piv]; A[piv] = tmp
      const tb = b[col]; b[col] = b[piv]; b[piv] = tb
    }
    const div = A[col][col]
    for (let c = col; c < n; c += 1) A[col][c] /= div
    b[col] /= div
    for (let r = 0; r < n; r += 1) {
      if (r === col) continue
      const f = A[r][col]
      if (!f) continue
      for (let c = col; c < n; c += 1) A[r][c] -= f * A[col][c]
      b[r] -= f * b[col]
    }
  }
  return b
}

// Warp perspektif + tingkatkan kontras. Sumber dibatasi 2000 px agar hemat memori HP.
function warpCanvas(bitmap, points) {
  const ordered = orderCorners(points)
  const orderedPx = ordered.map((p) => ({ x: p.x * bitmap.width, y: p.y * bitmap.height }))
  const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y)
  let outW = Math.round(Math.max(dist(orderedPx[0], orderedPx[1]), dist(orderedPx[3], orderedPx[2])))
  let outH = Math.round(Math.max(dist(orderedPx[0], orderedPx[3]), dist(orderedPx[1], orderedPx[2])))
  outW = Math.max(240, outW)
  outH = Math.max(150, outH)
  const scaleOut = Math.min(1, 1600 / Math.max(outW, outH))
  outW = Math.round(outW * scaleOut)
  outH = Math.round(outH * scaleOut)

  const scaleSrc = Math.min(1, 2000 / Math.max(bitmap.width, bitmap.height))
  const sw = Math.max(1, Math.round(bitmap.width * scaleSrc))
  const sh = Math.max(1, Math.round(bitmap.height * scaleSrc))
  const source = document.createElement('canvas')
  source.width = sw
  source.height = sh
  const sctx = source.getContext('2d', { willReadFrequently: true })
  sctx.drawImage(bitmap, 0, 0, sw, sh)
  const srcData = sctx.getImageData(0, 0, sw, sh).data
  const srcPx = orderedPx.map((p) => ({ x: p.x * scaleSrc, y: p.y * scaleSrc }))

  const dest = document.createElement('canvas')
  dest.width = outW
  dest.height = outH
  const dctx = dest.getContext('2d')
  const out = dctx.createImageData(outW, outH)
  const H = solveHomography(srcPx, [
    { x: 0, y: 0 }, { x: outW, y: 0 }, { x: outW, y: outH }, { x: 0, y: outH },
  ])
  if (!H) return { canvas: source, width: sw, height: sh }
  const [a, b, c, d, e, f, g, h] = H
  const outData = out.data
  for (let y = 0; y < outH; y += 1) {
    for (let x = 0; x < outW; x += 1) {
      const den = g * x + h * y + 1 || 1e-9
      const u = Math.min(sw - 1, Math.max(0, (a * x + b * y + c) / den))
      const v = Math.min(sh - 1, Math.max(0, (d * x + e * y + f) / den))
      const x0 = u | 0
      const y0 = v | 0
      const x1 = Math.min(sw - 1, x0 + 1)
      const y1 = Math.min(sh - 1, y0 + 1)
      const fx = u - x0
      const fy = v - y0
      const i00 = (y0 * sw + x0) * 4
      const i10 = (y0 * sw + x1) * 4
      const i01 = (y1 * sw + x0) * 4
      const i11 = (y1 * sw + x1) * 4
      const o = (y * outW + x) * 4
      for (let ch = 0; ch < 3; ch += 1) {
        const top = srcData[i00 + ch] * (1 - fx) + srcData[i10 + ch] * fx
        const bot = srcData[i01 + ch] * (1 - fx) + srcData[i11 + ch] * fx
        outData[o + ch] = top * (1 - fy) + bot * fy
      }
      outData[o + 3] = 255
    }
  }
  dctx.putImageData(out, 0, 0)
  enhanceCanvas(dest)
  return { canvas: dest, width: outW, height: outH }
}

// Peregangan kontras 2%–98% (tetap berwarna agar foto KTP tetap bisa diperiksa).
function enhanceCanvas(canvas) {
  const ctx = canvas.getContext('2d', { willReadFrequently: true })
  const img = ctx.getImageData(0, 0, canvas.width, canvas.height)
  const data = img.data
  const hist = new Uint32Array(256)
  const stride = Math.max(1, Math.floor((canvas.width * canvas.height) / 120000))
  let total = 0
  for (let i = 0; i < data.length; i += 4 * stride) {
    hist[(0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2]) | 0] += 1
    total += 1
  }
  const pick = (frac) => {
    let acc = 0
    const target = total * frac
    for (let i = 0; i < 256; i += 1) {
      acc += hist[i]
      if (acc >= target) return i
    }
    return 255
  }
  let low = pick(0.02)
  let high = pick(0.98)
  if (high - low < 40) { low = Math.max(0, low - 20); high = Math.min(255, high + 20) }
  const scale = 255 / Math.max(1, high - low)
  for (let i = 0; i < data.length; i += 4) {
    data[i] = Math.min(255, Math.max(0, (data[i] - low) * scale))
    data[i + 1] = Math.min(255, Math.max(0, (data[i + 1] - low) * scale))
    data[i + 2] = Math.min(255, Math.max(0, (data[i + 2] - low) * scale))
  }
  ctx.putImageData(img, 0, 0)
}

// Kualitas: ketajaman (varians Laplacian), pantulan, dan pencahayaan.
function assessCanvas(canvas) {
  const w = Math.min(360, canvas.width)
  const h = Math.max(1, Math.round(canvas.height * (w / canvas.width)))
  const small = document.createElement('canvas')
  small.width = w
  small.height = h
  small.getContext('2d').drawImage(canvas, 0, 0, w, h)
  const data = small.getContext('2d').getImageData(0, 0, w, h).data
  const gray = new Float32Array(w * h)
  let sum = 0
  let glare = 0
  for (let i = 0; i < w * h; i += 1) {
    const o = i * 4
    const g = 0.299 * data[o] + 0.587 * data[o + 1] + 0.114 * data[o + 2]
    gray[i] = g
    sum += g
    if (g > 248) glare += 1
  }
  const mean = sum / (w * h)
  let lapSum = 0
  let lapSq = 0
  let n = 0
  for (let y = 1; y < h - 1; y += 1) {
    for (let x = 1; x < w - 1; x += 1) {
      const i = y * w + x
      const lap = 4 * gray[i] - gray[i - 1] - gray[i + 1] - gray[i - w] - gray[i + w]
      lapSum += lap
      lapSq += lap * lap
      n += 1
    }
  }
  const variance = n ? lapSq / n - (lapSum / n) ** 2 : 0
  const glareRatio = glare / (w * h)
  const warnings = []
  if (variance < 60) warnings.push('Foto tampak kurang tajam/kabur — tahan HP lebih stabil lalu ulangi bila perlu.')
  if (glareRatio > 0.06) warnings.push('Ada pantulan cahaya di KTP — miringkan sedikit agar tidak menyilaukan.')
  if (mean < 55) warnings.push('Pencahayaan terlalu gelap — foto di tempat yang lebih terang.')
  if (Math.min(canvas.width, canvas.height) < 420) warnings.push('Resolusi hasil scan rendah — dekatkan kamera ke KTP.')
  return { warnings, metrics: { variance: Math.round(variance), mean: Math.round(mean), glare: Math.round(glareRatio * 100) } }
}

function confirmScan() {
  if (!scan.bitmap || scan.busy) return
  scan.busy = true
  try {
    const { canvas } = warpCanvas(scan.bitmap, scan.points)
    scan.warnings = assessCanvas(canvas).warnings
    canvas.toBlob((blob) => {
      scan.busy = false
      if (!blob) { error.value = 'Gagal memproses foto. Coba lagi.'; return }
      revokeUrl(scan.resultUrl)
      scan.resultUrl = URL.createObjectURL(blob)
      scan.resultBlob = blob
      scan.mode = 'result'
    }, 'image/jpeg', 0.9)
  } catch (e) {
    scan.busy = false
    error.value = 'Gagal merapikan foto: ' + (e.message || e)
  }
}

function acceptScan() {
  if (!scan.resultBlob) return
  if (scan.resultBlob.size > 5 * 1024 * 1024) {
    error.value = 'Ukuran hasil scan melebihi 5 MB. Coba lagi.'
    return
  }
  const name = String(scan.fileName || 'ktp').replace(/\.[^.]+$/, '') + '-scan.jpg'
  const file = new File([scan.resultBlob], name, { type: 'image/jpeg' })
  revokeUrl(ktpPreview.value)
  ktpFile.value = file
  ktpPreview.value = scan.resultUrl
  scan.resultUrl = ''
  ktpLabel.value = `${name} · ${Math.max(1, Math.round(file.size / 1024))} KB`
  ktpScanned.value = true
  closeScan(false)
}

// v2.89.0 (P5): OCR bantu isi NIK & nama dari hasil scan. Hasil OCR tetap
// harus diperiksa pengguna — tidak ada pengisian otomatis yang tak terlihat.
async function runOcr() {
  if (!scan.resultBlob || ocrBusy.value) return
  ocrBusy.value = true
  ocrMsg.value = ''
  try {
    const payload = new FormData()
    payload.append('ktp', scan.resultBlob, 'ktp-scan.jpg')
    payload.append('branch', resolvedBranch.value)
    if (linkToken) payload.append('t', linkToken)
    const response = await fetch('/api/first-work/ocr-ktp', {
      method: 'POST', body: payload,
    })
    const data = await response.json().catch(() => ({}))
    if (!response.ok || data.status !== 'success') {
      throw new Error(data.msg || 'OCR gagal. Isi manual saja.')
    }
    if (!data.found) {
      ocrMsg.value = data.msg || 'NIK/nama tidak terbaca — isi manual.'
      return
    }
    const filled = []
    if (/^\d{16}$/.test(String(data.nik || '')) && !form.nik) {
      form.nik = String(data.nik)
      filled.push('NIK')
    }
    if (String(data.nama || '').trim().length >= 3 && !form.nama.trim()) {
      form.nama = String(data.nama).trim()
      filled.push('nama')
    }
    if (!filled.length) {
      ocrMsg.value = 'NIK/nama sudah terisi — tidak ditimpa. Periksa kembali.'
      return
    }
    acceptScan()
    step.value = 0
    ocrNotice.value = `NIK & nama terisi dari KTP (keyakinan ${data.confidence || 0}%). `
      + 'Periksa kembali sebelum mengirim.'
    window.scrollTo({ top: 0, behavior: 'smooth' })
  } catch (e) {
    ocrMsg.value = e.message || 'OCR gagal. Isi manual saja.'
  } finally {
    ocrBusy.value = false
  }
}

function useOriginalScan() {
  if (!scan.bitmap || scan.busy) return
  scan.busy = true
  // Bangun file asli dari bitmap (orientasi EXIF sudah diterapkan).
  const maxSide = 1600
  const scale = Math.min(1, maxSide / Math.max(scan.bitmap.width, scan.bitmap.height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, Math.round(scan.bitmap.width * scale))
  canvas.height = Math.max(1, Math.round(scan.bitmap.height * scale))
  canvas.getContext('2d').drawImage(scan.bitmap, 0, 0, canvas.width, canvas.height)
  canvas.toBlob((blob) => {
    scan.busy = false
    if (!blob) { error.value = 'Gagal memakai foto asli.'; return }
    if (blob.size > 5 * 1024 * 1024) { error.value = 'Foto asli melebihi 5 MB.'; return }
    const name = String(scan.fileName || 'ktp').replace(/\.[^.]+$/, '') + '.jpg'
    const file = new File([blob], name, { type: 'image/jpeg' })
    revokeUrl(ktpPreview.value)
    ktpFile.value = file
    ktpPreview.value = URL.createObjectURL(blob)
    ktpLabel.value = `${name} · ${Math.max(1, Math.round(file.size / 1024))} KB`
    ktpScanned.value = false
    closeScan(true)
  }, 'image/jpeg', 0.85)
}

function closeScan(revokeOriginal = true) {
  endDrag()
  if (revokeOriginal) revokeUrl(scan.url)
  revokeUrl(scan.resultUrl)
  if (scan.bitmap && scan.bitmap.close) {
    try { scan.bitmap.close() } catch { /* noop */ }
  }
  scan.show = false
  scan.bitmap = null
  scan.url = ''
  scan.resultUrl = ''
  scan.resultBlob = null
  scan.points = []
  scan.warnings = []
  scan.mode = 'edit'
  scan.busy = false
  scan.dragging = -1
}

function stepError(target) {
  if (target === 0) {
    if (form.nik.length !== 16) return 'NIK sesuai KTP wajib 16 digit angka.'
    if (!nikInfo.value?.valid) return 'Tanggal lahir pada NIK tidak valid. Periksa kembali 16 digit NIK.'
    if (nikCheck.exists) return 'NIK ini sudah pernah mendaftar. Hubungi Traineer bila perlu koreksi data.'
    if (form.nama.trim().length < 3) return 'Nama Lengkap sesuai KTP wajib diisi (min. 3 karakter).'
    return ''
  }
  if (target === 1) {
    if (!form.pendidikan.trim()) return 'Pendidikan Terakhir wajib diisi.'
    if (manualRef.value ? form.referensi_text.trim().length < 2 : !form.referrer_id) {
      return 'Referensi wajib dipilih atau diisi.'
    }
    if (!hpInfo.value.valid) return 'Nomor Handphone tidak valid. Contoh: 081234567890.'
    return ''
  }
  if (!ktpFile.value) return 'Upload Identitas (KTP) wajib dilampirkan.'
  if (!consent.value) {
    return 'Centang persetujuan pemrosesan data pribadi terlebih dahulu.'
  }
  return ''
}

function goNext() {
  const message = stepError(step.value)
  if (message) { error.value = message; return }
  error.value = ''
  step.value = Math.min(step.value + 1, STEPS.length - 1)
  window.scrollTo({ top: 0, behavior: 'smooth' })
}
function goBack() {
  error.value = ''
  step.value = Math.max(0, step.value - 1)
  window.scrollTo({ top: 0, behavior: 'smooth' })
}
function goTo(index) {
  if (index > step.value) { goNext(); return }
  error.value = ''
  step.value = index
}

async function submit() {
  if (linkState.value !== 'ok') {
    error.value = 'Tautan form tidak valid. Minta tautan resmi dari Traineer/Admin.'
    return
  }
  for (let i = 0; i < STEPS.length; i += 1) {
    const message = stepError(i)
    if (message) { step.value = i; error.value = message; return }
  }
  error.value = ''
  const payload = new FormData()
  payload.append('nik', form.nik)
  payload.append('nama', form.nama.trim())
  payload.append('pendidikan', form.pendidikan.trim())
  payload.append('no_hp', hpInfo.value.hp)
  if (manualRef.value) payload.append('referensi_text', form.referensi_text.trim())
  else payload.append('referrer_id', form.referrer_id)
  payload.append('branch', resolvedBranch.value)
  if (linkToken) payload.append('t', linkToken)
  payload.append('consent', '1')
  payload.append('ktp', ktpFile.value)

  const csrf = localStorage.getItem('bpf_csrf') || sessionStorage.getItem('bpf_csrf')
  submitting.value = true
  try {
    const response = await fetch('/api/first-work/public', {
      method: 'POST',
      body: payload,
      headers: csrf ? { 'X-CSRF-Token': csrf } : {},
    })
    const data = await response.json().catch(() => ({}))
    if (!response.ok || data.status !== 'success') {
      throw new Error(data.msg || 'Gagal mengirim. Coba lagi.')
    }
    done.value = data
    clearDraft()
    window.scrollTo({ top: 0, behavior: 'smooth' })
  } catch (e) {
    error.value = e.message || 'Gagal mengirim. Coba lagi.'
  } finally {
    submitting.value = false
  }
}

function reset() {
  Object.assign(form, {
    nik: '', nama: '', pendidikan: '',
    referrer_id: '', referensi_text: '', no_hp: '',
  })
  ktpFile.value = null
  ktpLabel.value = ''
  ktpPreview.value = ''
  ocrBusy.value = false
  ocrMsg.value = ''
  ocrNotice.value = ''
  done.value = null
  error.value = ''
  step.value = 0
  consent.value = false
  restored.value = false
  resetNikCheck()
  clearDraft()
}

function copyRegNo() {
  if (!done.value?.registration_no) return
  navigator.clipboard?.writeText(done.value.registration_no).catch(() => {})
}

function maskNik(nik) {
  const text = String(nik || '')
  return text.length === 16 ? `${text.slice(0, 6)}••••${text.slice(-4)}` : text
}

onMounted(() => {
  restoreDraft()
  loadReferrers()
})
onBeforeUnmount(() => {
  clearTimeout(checkTimer)
  if (scan.show) closeScan(true)
})
</script>

<template>
  <div class="fw-page">
    <div class="fw-card">
      <div class="fw-brand">
        <img :src="brandIcon" alt="BPF" />
        <h1>Absensi FirstWork</h1>
        <!-- v2.86.0: tanpa fallback 'Surabaya' — nama cabang hanya tampil bila
             tautan terverifikasi server, dan disembunyikan saat tautan ditolak. -->
        <p v-if="linkState !== 'invalid'">PT Bestprofit Futures · {{ branchLabel || '…' }}</p>
      </div>

      <!-- v2.86.0: halaman penolakan penuh untuk tautan tidak sah —
           tanpa form, tanpa langkah, tanpa branding cabang. -->
      <div v-if="linkState === 'invalid'" class="fw-reject">
        <div class="fw-reject-ico">⛔</div>
        <h2>Tautan Form Tidak Valid</h2>
        <p class="fw-reject-msg">{{ linkError }}</p>
        <p class="fw-note">
          Gunakan tautan atau QR resmi dari Traineer/Admin cabang tujuan Anda.
          Setiap cabang memiliki tautan yang berbeda dan tidak dapat dipakai
          antar cabang.
        </p>
      </div>

      <template v-else>
      <div v-if="done" class="fw-success">
        <div class="fw-check">✅</div>
        <h2>Terima kasih, {{ done.nama }}!</h2>
        <div class="fw-info">
          <div><span>No. Registrasi</span><b>{{ done.registration_no }}</b></div>
          <div><span>Waktu Kirim</span><b>{{ done.submitted_at }}</b></div>
          <div><span>Status</span><b>Menunggu verifikasi Traineer</b></div>
        </div>
        <p class="fw-note">
          Simpan nomor registrasi di atas. Data Anda akan diverifikasi oleh Traineer
          sebelum diproses lebih lanjut.
        </p>
        <button class="btn fw-wide" @click="copyRegNo">📋 Salin No. Registrasi</button>
        <button class="btn btn-primary fw-wide" @click="reset">📝 Isi Data Lain</button>
      </div>

      <form v-else @submit.prevent="step === STEPS.length - 1 ? submit() : goNext()">
        <div v-if="restored" class="fw-restored">
          ↩️ Draf pengisian sebelumnya dipulihkan.
          <button type="button" class="fw-link" @click="reset(); restored = false">Mulai baru</button>
        </div>
        <div v-if="error" class="alert alert-error">{{ error }}</div>

        <div class="fw-steps">
          <button v-for="(label, i) in STEPS" :key="label" type="button" class="fw-step"
                  :class="{ active: step === i, done: step > i }" @click="goTo(i)">
            <span class="fw-step-no">{{ step > i ? '✓' : i + 1 }}</span>
            <span class="fw-step-label">{{ label }}</span>
          </button>
        </div>
        <div class="fw-progress"><div class="fw-progress-bar" :style="{ width: pct + '%' }" /></div>

        <!-- Langkah 1: data diri -->
        <template v-if="step === 0">
          <div v-if="ocrNotice" class="fw-callout fw-callout-ok">{{ ocrNotice }}</div>
          <div class="fw-field">
            <label>NIK sesuai KTP <span class="req">*</span></label>
            <input class="input" :value="form.nik" inputmode="numeric" autocomplete="off"
                   maxlength="16" placeholder="16 digit angka" @input="onNik" />
            <small class="fw-hint">
              {{ form.nik.length }}/16 digit
              <template v-if="nikCheck.state === 'checking'"> · memeriksa…</template>
              <template v-else-if="nikCheck.state === 'free'"> · ✅ belum terdaftar</template>
              <template v-else-if="nikCheck.state === 'taken'"> · ⚠️ sudah terdaftar</template>
            </small>
          </div>

          <div v-if="nikCheck.exists" class="fw-callout fw-callout-red">
            NIK ini sudah pernah mendaftar. Hubungi Traineer untuk koreksi atau cek status
            pendaftaran Anda — tidak perlu mengisi ulang.
          </div>
          <div v-else-if="nikInfo" class="fw-callout" :class="nikInfo.valid ? '' : 'fw-callout-red'">
            <template v-if="nikInfo.valid">
              <div class="fw-derived">
                <span>👤 {{ nikInfo.gender }}</span>
                <span>🎂 {{ nikInfo.birth }}</span>
                <span v-if="nikInfo.province">📍 {{ nikInfo.province }}</span>
              </div>
              <small v-if="nikInfo.warning" class="fw-hint">{{ nikInfo.warning }}</small>
              <small v-else class="fw-hint">Dibaca otomatis dari NIK — cocokkan dengan KTP Anda.</small>
            </template>
            <template v-else>
              Tanggal lahir pada NIK tidak valid. Periksa kembali 16 digit NIK Anda.
            </template>
          </div>

          <div class="fw-field">
            <label>Nama Lengkap sesuai KTP <span class="req">*</span></label>
            <input class="input" v-model="form.nama" maxlength="150" autocomplete="name"
                   placeholder="cth: Ahmad Fauzi" @blur="onNamaBlur" />
            <small class="fw-hint">Tulis persis seperti di KTP, tanpa gelar.</small>
          </div>
        </template>

        <!-- Langkah 2: pendidikan, referensi, kontak -->
        <template v-else-if="step === 1">
          <div class="fw-field">
            <label>Pendidikan Terakhir <span class="req">*</span></label>
            <input class="input" v-model="form.pendidikan" list="fw-pendidikan"
                   maxlength="100" autocomplete="off"
                   placeholder="cth: S1 / SMK / S1 pendidikan keagamaan katolik" />
            <datalist id="fw-pendidikan">
              <option v-for="p in PENDIDIKAN" :key="p" :value="p" />
            </datalist>
            <small class="fw-hint">Boleh diisi bebas sesuai ijazah.</small>
          </div>

          <div class="fw-field">
            <label>Referensi <span class="req">*</span></label>
            <select class="select" v-model="form.referrer_id" :disabled="metaLoading">
              <option value="">— Pilih Pengundang / Pemberi Info —</option>
              <option v-for="ref in referrers" :key="ref.id" :value="String(ref.id)">{{ ref.name }}</option>
              <option value="manual">Lainnya / tidak ada di daftar…</option>
            </select>
            <input v-if="manualRef" class="input fw-gap" v-model="form.referensi_text"
                   maxlength="150" placeholder="Nama pengundang / pemberi informasi lowongan" />
            <small class="fw-hint">Nama orang yang mengundang atau memberi info lowongan.</small>
          </div>

          <div class="fw-field">
            <label>No. Handphone <span class="req">*</span></label>
            <input class="input" v-model="form.no_hp" type="tel" inputmode="tel"
                   maxlength="20" autocomplete="tel" placeholder="cth: 081234567890"
                   @blur="onHpBlur" />
            <small class="fw-hint">
              <template v-if="!form.no_hp">Boleh 08…, 8…, atau +62… (otomatis dibakukan).</template>
              <template v-else-if="hpInfo.valid">✅ Tersimpan sebagai {{ hpInfo.hp }}</template>
              <template v-else>⚠️ Nomor belum valid — perlu 10–14 digit dan diawali 08.</template>
            </small>
          </div>
        </template>

        <!-- Langkah 3: KTP + ringkasan -->
        <template v-else>
          <div class="fw-field">
            <label>Upload Identitas (KTP) <span class="req">*</span></label>
            <label class="fw-upload" :class="{ 'has-file': ktpFile }">
              <input type="file" accept="image/jpeg,image/png,application/pdf" capture="environment"
                     hidden @change="pickKtp" />
              <template v-if="ktpFile">
                <img v-if="ktpPreview" :src="ktpPreview" alt="Pratinjau KTP" class="fw-thumb" />
                <span class="fw-file">✅ {{ ktpLabel }}</span>
                <span v-if="ktpScanned" class="fw-scan-badge">✨ Sudah diluruskan &amp; diperjelas</span>
                <span class="fw-hint">Tap untuk ganti file</span>
              </template>
              <template v-else>
                <span class="fw-upload-ico">🪪</span>
                <span class="fw-file">Foto / Scan KTP</span>
                <span class="fw-hint">JPG, PNG, atau PDF · maks. 5 MB · foto miring diluruskan otomatis</span>
              </template>
            </label>
          </div>

          <div class="fw-review">
            <h4>Ringkasan</h4>
            <div><span>Nama</span><b>{{ form.nama || '—' }}</b></div>
            <div><span>NIK</span><b>{{ maskNik(form.nik) }}</b></div>
            <div><span>Pendidikan</span><b>{{ form.pendidikan || '—' }}</b></div>
            <div><span>Referensi</span><b>{{ manualRef ? (form.referensi_text || '—') : (referrers.find(r => String(r.id) === form.referrer_id)?.name || '—') }}</b></div>
            <div><span>No. Handphone</span><b>{{ hpInfo.hp || '—' }}</b></div>
          </div>
        </template>

          <label class="fw-consent">
            <input type="checkbox" v-model="consent" />
            <span>Saya menyatakan data yang saya isi adalah benar dan saya
            <b>menyetujui penggunaan data pribadi saya</b> (NIK, nama, No. HP,
            foto KTP) oleh PT Bestprofit Futures untuk proses rekrutmen
            FirstWork ini.</span>
          </label>

          <div class="fw-nav">
            <button v-if="step > 0" type="button" class="btn" @click="goBack">← Kembali</button>
            <button v-if="step < STEPS.length - 1" type="submit" class="btn btn-primary fw-next">
              Lanjut →
            </button>
            <button v-else type="submit" class="btn btn-primary fw-next" :disabled="submitting || !consent">
              {{ submitting ? '⏳ Mengirim…' : '📤 Kirim Absensi' }}
            </button>
          </div>
          <p class="fw-note">
            Form ini terbuka untuk umum dan tidak memerlukan login. Data Anda hanya
            dipakai untuk proses rekrutmen PT Bestprofit Futures dan disesuai
            kebijakan retensi: foto KTP dihapus otomatis setelah proses selesai.
          </p>
      </form>
      </template>
    </div>

    <!-- v2.87.0: editor scan KTP — 4 sudut, warp perspektif, cek kualitas.
         Diproses sepenuhnya di perangkat; tidak ada unggahan tambahan. -->
    <div v-if="scan.show" class="fw-scan-overlay" role="dialog" aria-modal="true">
      <div class="fw-scan-box">
        <div class="fw-scan-head">
          <b>Rapikan Foto KTP</b>
          <button type="button" class="fw-scan-x" aria-label="Tutup" @click="closeScan()">✕</button>
        </div>

        <template v-if="scan.mode === 'edit'">
          <p class="fw-scan-hint">Geser 4 titik ke sudut KTP. Hasilnya akan diluruskan otomatis.</p>
          <div ref="scanBox" class="fw-scan-stage">
            <canvas ref="scanCanvas" class="fw-scan-canvas" />
            <svg class="fw-scan-lines" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
              <polygon :points="scan.points.map((p) => `${p.x * 100},${p.y * 100}`).join(' ')" />
            </svg>
            <button v-for="(p, i) in scan.points" :key="i" type="button"
                    class="fw-scan-handle" :style="{ left: `${p.x * 100}%`, top: `${p.y * 100}%` }"
                    :aria-label="`Sudut ${i + 1}`" @pointerdown="startDrag(i, $event)" />
          </div>
          <div class="fw-scan-actions">
            <button type="button" class="btn" @click="closeScan()">Batal</button>
            <button type="button" class="btn" :disabled="scan.busy" @click="useOriginalScan">Foto asli</button>
            <button type="button" class="btn btn-primary" :disabled="scan.busy" @click="confirmScan">
              {{ scan.busy ? '⏳ Memproses…' : '✓ Rapikan' }}
            </button>
          </div>
        </template>

        <template v-else>
          <img :src="scan.resultUrl" alt="Hasil scan KTP" class="fw-scan-result" />
          <div v-if="scan.warnings.length" class="fw-scan-warn">
            <b>Periksa dulu:</b>
            <ul><li v-for="w in scan.warnings" :key="w">{{ w }}</li></ul>
          </div>
          <p v-else class="fw-scan-ok">✅ Hasil scan cukup jelas.</p>
          <button type="button" class="btn fw-scan-ocr" :disabled="ocrBusy" @click="runOcr">
            {{ ocrBusy ? '⏳ Membaca KTP…' : '🔍 Isi NIK & Nama otomatis' }}
          </button>
          <p class="fw-scan-hint">Bantuan OCR — selalu periksa hasilnya sebelum kirim.</p>
          <p v-if="ocrMsg" class="fw-scan-ocrmsg">{{ ocrMsg }}</p>
          <div class="fw-scan-actions">
            <button type="button" class="btn" @click="scan.mode = 'edit'; nextTick(drawScanEditor)">↩ Atur sudut</button>
            <button type="button" class="btn btn-primary" @click="acceptScan">✓ Pakai hasil ini</button>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.fw-page {
  min-height: 100vh; display: flex; align-items: center; justify-content: center;
  padding: 20px 16px;
  background:
    radial-gradient(at 0% 0%, rgba(180, 83, 9, .10) 0px, transparent 50%),
    radial-gradient(at 100% 100%, rgba(37, 99, 235, .08) 0px, transparent 50%), var(--bg);
}
.fw-card {
  width: 100%; max-width: 460px; background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 26px 22px; box-shadow: var(--shadow-lg);
  animation: popIn .2s ease;
}
.fw-brand { text-align: center; margin-bottom: 18px; }
.fw-brand img { width: 54px; height: 54px; border-radius: 13px; box-shadow: 0 4px 14px rgba(180, 83, 9, .22); }
.fw-brand h1 { font-size: 18px; font-weight: 800; margin-top: 10px; }
.fw-brand p { font-size: 11px; color: var(--text-3); margin-top: 2px; }
.fw-field { margin-bottom: 14px; }
.fw-field > label { display: block; font-size: 12px; font-weight: 600; margin-bottom: 5px; }
.fw-hint { display: block; font-size: 10px; color: var(--text-3); margin-top: 4px; }
.fw-gap { margin-top: 8px; }
.req { color: var(--danger, #dc2626); }
.fw-wide { width: 100%; justify-content: center; padding: 11px; margin-top: 6px; }
.fw-note { margin-top: 14px; font-size: 11px; color: var(--text-3); text-align: center; line-height: 1.5; }
.fw-success { text-align: center; }
.fw-check { font-size: 44px; }
.fw-success h2 { font-size: 17px; margin-top: 6px; }
.fw-info {
  margin-top: 14px; background: var(--bg); border: 1px solid var(--border); border-radius: 12px;
  padding: 14px; text-align: left; display: grid; gap: 10px;
}
.fw-info span { display: block; font-size: 11px; color: var(--text-3); }
.fw-info b { font-size: 14px; }
.fw-upload {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  min-height: 118px; border: 2px dashed var(--border); border-radius: 12px;
  cursor: pointer; transition: all .2s; overflow: hidden; padding: 10px; text-align: center;
}
.fw-upload:hover { border-color: var(--primary, #7c3aed); background: rgba(124, 58, 237, .04); }
.fw-upload.has-file { border-style: solid; border-color: var(--success, #16a34a); }
.fw-upload-ico { font-size: 26px; margin-bottom: 4px; }
.fw-file { font-size: 12px; font-weight: 600; color: var(--text-2); word-break: break-word; }
.fw-thumb { width: 100%; max-height: 130px; object-fit: contain; border-radius: 8px; margin-bottom: 6px; }

.fw-steps { display: flex; gap: 6px; margin-bottom: 8px; }
.fw-step {
  flex: 1; display: flex; align-items: center; gap: 5px; padding: 6px 4px; border: 1px solid var(--border);
  background: var(--bg); border-radius: 9px; cursor: pointer; font-size: 10px; color: var(--text-3);
  min-width: 0;
}
.fw-step-no {
  width: 17px; height: 17px; border-radius: 50%; display: inline-flex; align-items: center;
  justify-content: center; font-weight: 700; background: var(--border); color: var(--text-2); flex: none;
}
.fw-step-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fw-step.active { border-color: var(--primary, #7c3aed); color: var(--text); font-weight: 600; }
.fw-step.active .fw-step-no { background: var(--primary, #7c3aed); color: #fff; }
.fw-step.done .fw-step-no { background: var(--success, #16a34a); color: #fff; }
.fw-progress { height: 4px; background: var(--border); border-radius: 99px; overflow: hidden; margin-bottom: 16px; }
.fw-progress-bar { height: 100%; background: var(--primary, #7c3aed); transition: width .25s ease; }
.fw-callout {
  background: var(--bg); border: 1px solid var(--border); border-radius: 10px;
  padding: 10px 12px; margin-bottom: 14px; font-size: 11px; line-height: 1.5;
}
.fw-callout-red { border-color: #dc2626; background: rgba(220, 38, 38, .06); color: #b91c1c; }
.fw-callout-ok { border-color: #16a34a; background: rgba(22, 163, 74, .07); color: #166534; }
.fw-derived { display: flex; flex-wrap: wrap; gap: 8px; font-size: 11px; font-weight: 600; }
.fw-restored {
  background: rgba(37, 99, 235, .08); border: 1px solid rgba(37, 99, 235, .3);
  border-radius: 9px; padding: 8px 10px; font-size: 11px; margin-bottom: 12px;
}
.fw-link { background: none; border: 0; padding: 0; color: #2563eb; font-size: 11px; cursor: pointer; text-decoration: underline; }
.fw-review { background: var(--bg); border: 1px solid var(--border); border-radius: 12px;
  padding: 12px 14px; display: grid; gap: 8px; margin-bottom: 12px;
}
.fw-review h4 { font-size: 11px; text-transform: uppercase; letter-spacing: .04em; color: var(--text-3); }
.fw-review span { display: block; font-size: 10px; color: var(--text-3); }
.fw-review b { font-size: 12px; }
/* v2.85.0: persetujuan pemrosesan data pribadi (UU PDP) */
.fw-consent { display: flex; gap: 10px; align-items: flex-start; cursor: pointer;
  background: var(--bg); border: 1px solid var(--border); border-radius: 10px;
  padding: 10px 12px; font-size: 11.5px; line-height: 1.5; margin-bottom: 4px; }
.fw-consent input { margin-top: 2px; flex: none; width: 16px; height: 16px; accent-color: var(--primary, #7c3aed); }
.fw-consent:has(input:checked) { border-color: var(--primary, #7c3aed); }
.fw-nav { display: flex; gap: 8px; margin-top: 6px; }
/* v2.86.0: halaman penolakan penuh tautan form tidak sah */
.fw-reject { text-align: center; padding: 28px 16px; display: grid; gap: 8px; justify-items: center; }
.fw-reject-ico { font-size: 34px; }
.fw-reject h2 { margin: 0; font-size: 16px; }
.fw-reject-msg { margin: 0; font-size: 12px; color: var(--text-3); line-height: 1.6; }
.fw-next { flex: 1; justify-content: center; }
/* v2.87.0: editor scan KTP (P1/P2) */
.fw-scan-overlay {
  position: fixed; inset: 0; z-index: 60; background: rgba(15, 23, 42, .72);
  display: flex; align-items: center; justify-content: center; padding: 14px;
}
.fw-scan-box {
  width: 100%; max-width: 420px; max-height: 94vh; overflow: auto;
  background: var(--surface); border-radius: 14px; padding: 14px;
  box-shadow: 0 18px 50px rgba(0, 0, 0, .3);
}
.fw-scan-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.fw-scan-x { border: 0; background: none; font-size: 18px; cursor: pointer; color: var(--text-3); }
.fw-scan-hint { font-size: 11px; color: var(--text-3); margin: 0 0 8px; }
.fw-scan-stage {
  position: relative; touch-action: none; user-select: none;
  border-radius: 10px; overflow: hidden; background: #0f172a;
}
.fw-scan-canvas { display: block; width: 100%; height: auto; }
.fw-scan-lines { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
.fw-scan-lines polygon {
  fill: rgba(124, 58, 237, .12); stroke: #a78bfa; stroke-width: 1.2;
  vector-effect: non-scaling-stroke;
}
.fw-scan-handle {
  position: absolute; width: 26px; height: 26px; margin: -13px 0 0 -13px;
  border-radius: 50%; border: 2px solid #fff; background: #7c3aed;
  box-shadow: 0 2px 8px rgba(0, 0, 0, .4); touch-action: none; cursor: grab; padding: 0;
}
.fw-scan-actions { display: flex; gap: 8px; margin-top: 12px; }
.fw-scan-actions .btn { flex: 1; justify-content: center; }
.fw-scan-result { width: 100%; border-radius: 10px; border: 1px solid var(--border); }
.fw-scan-warn {
  margin-top: 10px; background: rgba(245, 158, 11, .1);
  border: 1px solid rgba(245, 158, 11, .4); border-radius: 10px;
  padding: 8px 10px; font-size: 11px; line-height: 1.5;
}
.fw-scan-warn ul { margin: 4px 0 0; padding-left: 16px; }
.fw-scan-ok { margin-top: 8px; font-size: 11px; color: var(--success, #16a34a); }
.fw-scan-badge { font-size: 10px; font-weight: 700; color: #7c3aed; }
.fw-scan-ocr { width: 100%; justify-content: center; margin-top: 10px; }
.fw-scan-ocrmsg { margin: 6px 0 0; font-size: 11px; color: #b45309; }
</style>
