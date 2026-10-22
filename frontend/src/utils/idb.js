/**
 * IndexedDB wrapper — antrean offline driver + trip drafts (auto-save).
 * 4 stores: fuel_queue, trip_queue, lpj_queue, trip_drafts
 *
 * v2.50.1: self-heal — bila bundel baru menagih store yang belum ada di DB
 * browser (dibuat versi lama), store otomatis dibuat via version-bump tanpa
 * error 'object store not found' berulang. Bump DB_VER juga paksa upgrade.
 */
const DB_NAME = 'BPF_Driver_DB'
const DB_VER = 5
const STORES = ['fuel_queue', 'trip_queue', 'lpj_queue', 'trip_drafts']

let _dbPromise = null

function _openVersion(ver) {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, ver)
    req.onupgradeneeded = (e) => {
      const d = e.target.result
      for (const s of STORES) {
        if (!d.objectStoreNames.contains(s)) d.createObjectStore(s, { keyPath: 'id', autoIncrement: true })
      }
    }
    req.onsuccess = (e) => resolve(e.target.result)
    req.onerror = (e) => reject(e)
    req.onblocked = () => reject(new Error('IndexedDB blocked — tutup tab lain lalu muat ulang'))
  })
}

async function openDB() {
  if (_dbPromise) return _dbPromise
  _dbPromise = (async () => {
    if (typeof indexedDB === 'undefined') throw new Error('IndexedDB tidak didukung browser ini')
    let db
    try {
      db = await _openVersion(DB_VER)
    } catch (err) {
      // E11: versi tersimpan lebih tinggi → buka tanpa versi (aktual).
      if (err && err.name === 'VersionError') db = await _openVersion()
      else throw err
    }
    // v2.50.1: DB lama bisa punya versi >= DB_VER tapi store tak lengkap
    // (di-*open* versi lama kode). Upgrade tidak jalan lagi di versi sama →
    // cek isi, bila ada store hilang buka ulang dengan versi lebih tinggi.
    const missing = () => STORES.filter((s) => !db.objectStoreNames.contains(s))
    let attempt = 0
    while (missing().length && attempt < 3) {
      try {
        db.close()
      } catch { /* ignore */ }
      attempt++
      db = await _openVersion(db.version + 1)
    }
    if (missing().length) throw new Error('Store IndexedDB tidak dapat dibuat: ' + missing().join(','))
    return db
  })()
  try {
    return await _dbPromise
  } catch (e) {
    _dbPromise = null
    throw e
  }
}

async function tx(store, mode) {
  const db = await openDB()
  return db.transaction(store, mode)
}

export async function addToQueue(store, data) {
  const t = await tx(store, 'readwrite')
  return new Promise((resolve, reject) => {
    const req = t.objectStore(store).add(data)
    req.onsuccess = () => resolve(req.result)
    req.onerror = (e) => reject(e)
  })
}

export async function getAllFromQueue(store) {
  const t = await tx(store, 'readonly')
  return new Promise((resolve, reject) => {
    const req = t.objectStore(store).getAll()
    req.onsuccess = () => resolve(req.result)
    req.onerror = (e) => reject(e)
  })
}

export async function deleteFromQueue(store, id) {
  const t = await tx(store, 'readwrite')
  return new Promise((resolve, reject) => {
    t.objectStore(store).delete(id)
    t.oncomplete = () => resolve()
    t.onerror = (e) => reject(e)
  })
}

export async function countQueue(store) {
  const t = await tx(store, 'readonly')
  return new Promise((resolve, reject) => {
    const req = t.objectStore(store).count()
    req.onsuccess = () => resolve(req.result)
    req.onerror = (e) => reject(e)
  })
}

/** Hitung semua antrean sekaligus → { fuel, trip, lpj }. */
export async function countAllQueues() {
  try {
    const [fuel, trip, lpj] = await Promise.all([
      countQueue('fuel_queue'), countQueue('trip_queue'), countQueue('lpj_queue'),
    ])
    return { fuel, trip, lpj }
  } catch {
    return { fuel: 0, trip: 0, lpj: 0 }
  }
}

// --- Trip Draft (auto-save) ---

/** Simpan draft trip (upsert by key = driver+date). */
export async function saveTripDraft(driver, tripDate, data) {
  try {
    const db = await openDB()
    const t = db.transaction('trip_drafts', 'readwrite')
    const store = t.objectStore('trip_drafts')
    const key = `${driver}_${tripDate}`
    // Hapus draft lama jika ada
    const existing = await new Promise((res) => {
      const req = store.get(key)
      req.onsuccess = () => res(req.result)
      req.onerror = () => res(null)
    })
    if (existing) store.delete(key)
    store.put({ id: key, driver, tripDate, data, savedAt: new Date().toISOString() })
    return true
  } catch { return false }
}

/** Load draft trip berdasarkan driver + date. */
export async function loadTripDraft(driver, tripDate) {
  try {
    const db = await openDB()
    const t = db.transaction('trip_drafts', 'readonly')
    const store = t.objectStore('trip_drafts')
    const key = `${driver}_${tripDate}`
    return await new Promise((res) => {
      const req = store.get(key)
      req.onsuccess = () => res(req.result?.data || null)
      req.onerror = () => res(null)
    })
  } catch { return null }
}

/** Hapus draft trip (setelah submit berhasil). */
export async function deleteTripDraft(driver, tripDate) {
  try {
    const db = await openDB()
    const t = db.transaction('trip_drafts', 'readwrite')
    const store = t.objectStore('trip_drafts')
    const key = `${driver}_${tripDate}`
    store.delete(key)
    return true
  } catch { return false }
}
