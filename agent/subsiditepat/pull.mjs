// Stage C — ambil riwayat transaksi BBM menggunakan Bearer dari token.json
//   node pull.mjs [jumlah_hari=30]
// Endpoint resmi (hasil intersep web): GET /mpv-personal/v1/transaction/bbm
//   query: startDate, endDate, product, licenseNumber, size, page
import fs from 'fs';
import path from 'path';

const DIR = path.dirname(new URL(import.meta.url).pathname);
if (!fs.existsSync(path.join(DIR, 'token.json'))) {
  console.error('token.json tidak ada — jalankan login+verify dulu');
  process.exit(1);
}
const { token } = JSON.parse(fs.readFileSync(path.join(DIR, 'token.json'), 'utf8'));

const BASE = 'https://apimpv.my-pertamina.id';
const EP = '/mpv-personal/v1/transaction/bbm';
const DAYS = Number(process.argv[2] || 30);
const SIZE = 50; // server menolak 250; UI memakai 10
const UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36';

const end = new Date();
const start = new Date(Date.now() - DAYS * 86400e3);
const fmt = d => d.toISOString().slice(0, 10);

const call = async (qs) => {
  const r = await fetch(`${BASE}${EP}?${qs}`, {
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      'User-Agent': UA,
      Referer: 'https://subsiditepat.mypertamina.id/',
      Origin: 'https://subsiditepat.mypertamina.id',
    },
  });
  const txt = await r.text();
  let json = null;
  try { json = JSON.parse(txt); } catch {}
  return { status: r.status, json, txt };
};

const all = [];
let page = 1;
for (;;) {
  const qs = new URLSearchParams({
    startDate: fmt(start),
    endDate: fmt(end),
    product: '',
    licenseNumber: '',
    size: String(SIZE),
    page: String(page),
  }).toString();
  const { status, json, txt } = await call(qs);
  if (status !== 200) {
    console.log(`page ${page}: HTTP ${status}:`, (json && json.message) || txt.slice(0, 120));
    if (page === 1) process.exit(1);
    break;
  }
  const rows = json?.data || [];
  console.log(`page ${page}: ${rows.length} transaksi`);
  all.push(...rows);
  if (rows.length < SIZE || page >= 40) break;
  page++;
  await new Promise(r => setTimeout(r, 400));
}

// ringkasan
const fmtRp = n => 'Rp ' + (n || 0).toLocaleString('id-ID');
const totalLiter = all.reduce((s, t) => s + (t.volumeTransaction || 0), 0);
const totalRp = all.reduce((s, t) => s + (t.totalAmount || 0), 0);
const cars = [...new Set(all.map(t => t.vehicleLicenseNumber))];
const products = {};
for (const t of all) products[t.product || '?'] = (products[t.product || '?'] || 0) + (t.volumeTransaction || 0);
console.log('────────────────────────────────────────────');
console.log(`Total: ${all.length} transaksi | ${totalLiter.toFixed(2)} liter | ${fmtRp(totalRp)}`);
console.log(`Unit: ${cars.length} kendaraan →`, cars.join(', '));
console.log('Produk (liter):', JSON.stringify(products));
if (all.length) {
  const ds = all.map(t => t.transactionDate).sort();
  console.log(`Periode data: ${ds[0]} s/d ${ds.at(-1)}`);
}

// simpan artifact (data pribadi — di gitignore)
fs.mkdirSync(path.join(DIR, 'data'), { recursive: true });
const stem = `${fmt(start)}_${fmt(end)}`;
const jsonFile = path.join(DIR, `data/bbm_${stem}.json`);
fs.writeFileSync(jsonFile, JSON.stringify({
  pulledAt: new Date().toISOString(), count: all.length, totalLiter, totalRp, rows: all,
}, null, 1), { mode: 0o600 });
const csv = ['tanggal,jam,nopol,produk,liter,total_rp,spbu,kota,verifikasi,transactionId']
  .concat(all.slice().reverse().map(t => [
    (t.transactionDate || '').slice(0, 10),
    (t.transactionDate || '').slice(11, 16),
    t.vehicleLicenseNumber, t.product, t.volumeTransaction, t.totalAmount,
    t.spbuId, `${t.city || ''}/${t.witel || ''}`, t.verificationType, t.transactionId,
  ].join(','))).join('\n');
const csvFile = path.join(DIR, `data/bbm_${stem}.csv`);
fs.writeFileSync(csvFile, csv, { mode: 0o600 });
console.log('JSON →', jsonFile);
console.log('CSV  →', csvFile);
