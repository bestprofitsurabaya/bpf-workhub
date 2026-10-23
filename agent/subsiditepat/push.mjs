// Stage D — push riwayat BBM ke bpf-workhub (/api/subsidy/import)
//   node push.mjs [file_data] [jumlah_hari_default=32]
// Tanpa argumen: jalankan pull.mjs dulu untuk hari terakhir 'days', atau pakai
// file JSON terbaru di data/. Auth: header X-SUBSIDY-TOKEN (env).
import fs from 'fs';
import path from 'path';

const DIR = path.dirname(new URL(import.meta.url).pathname);
const ENV = Object.fromEntries(fs.existsSync(path.join(DIR, '.env'))
  ? fs.readFileSync(path.join(DIR, '.env'), 'utf8').trim().split('\n')
      .filter(l => l.includes('=')).map(l => {
        const i = l.indexOf('=');
        return [l.slice(0, i).trim(), l.slice(i + 1).trim()];
      })
  : []);

const API = process.env.WORKHUB_API || ENV.WORKHUB_API || 'http://127.0.0.1:5001';
const TOKEN = process.env.SUBSIDY_IMPORT_TOKEN || ENV.SUBSIDY_IMPORT_TOKEN;
if (!TOKEN) { console.error('SUBSIDY_IMPORT_TOKEN tidak ada di .env'); process.exit(1); }

// tentukan sumber data
let file = process.argv[2];
if (!file || !fs.existsSync(file)) {
  const files = fs.readdirSync(path.join(DIR, 'data'))
    .filter(f => f.match(/^bbm_.*\.json$/)).sort().reverse();
  if (!files.length) {
    console.log('Tidak ada data — jalankan pull.mjs dulu.');
    process.exit(1);
  }
  file = path.join(DIR, 'data', files[0]);
}
const payload = JSON.parse(fs.readFileSync(file, 'utf8'));
const rows = payload.rows || [];
const daysBack = Math.round((Date.now() - new Date(file.match(/bbm_(\d{4}-\d{2}-\d{2})_\d{4}-\d{2}-\d{2}/)?.[1] || Date.now()).getTime()) / 86400e3);
const days = Math.max(1, Math.min(365, daysBack));
console.log(`Sumber: ${path.basename(file)} — ${rows.length} transaksi → ${API}`);

const r = await fetch(`${API}/api/subsidy/import`, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-SUBSIDY-TOKEN': TOKEN,
    'User-Agent': 'subsiditepat-agent/1.0',
  },
  body: JSON.stringify({ rows, pulled_at: payload.pulledAt, days }),
});
const txt = await r.text();
console.log(`${r.status}:`, txt.slice(0, 300));
process.exit(r.ok ? 0 : 1);
