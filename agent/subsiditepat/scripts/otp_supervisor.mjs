// ============================================================
// otp_supervisor.mjs — v2.69.0 (bagian bpf-workhub)
// ------------------------------------------------------------
// Jembatan Dashboard Finance ↔ agen Subsidi Tepat di HOST.
// Container web menulis perintah ke gate/ (bind-mount /app/subsidy_gate):
//   otp_request.json → login.mjs (headful, Xvfb :99) → OTP email
//   otp_submit.json  → verify.mjs <kode> → token.json baru
//                     → pull.mjs → push.mjs (import) → auto-match
// Status setiap langkah ditulis ke gate/agent_state.json:
//   idle → starting → waiting_otp → verifying → syncing → done|error
// Jalankan: node otp_supervisor.mjs  (cron @reboot + nohup sekarang)
// ============================================================
import { spawn, spawnSync } from 'child_process';
import fs from 'fs';
import path from 'path';

const DIR = path.dirname(new URL(import.meta.url).pathname);   // …/scripts
const ROOT = path.resolve(DIR, '..');                          // …/agent/subsiditepat
const GATE = process.env.SUBSIDY_GATE_DIR || path.join(ROOT, 'gate');
const TICK_MS = 4000;

const ENV = Object.fromEntries(fs.existsSync(path.join(ROOT, '.env'))
  ? fs.readFileSync(path.join(ROOT, '.env'), 'utf8').trim().split('\n')
      .filter(l => l.includes('=')).map(l => {
        const i = l.indexOf('=');
        return [l.slice(0, i).trim(), l.slice(i + 1).trim()];
      })
  : []);
const API = process.env.WORKHUB_API || ENV.WORKHUB_API || 'http://127.0.0.1:5001';

const gpath = (n) => path.join(GATE, n);
let lastReqAt = '', lastSubAt = '';   // cegah pemrosesan ulang

function readJson(name, fallback = null) {
  try { return JSON.parse(fs.readFileSync(gpath(name), 'utf8')); }
  catch { return fallback; }
}
function writeState(patch) {
  const cur = readJson('agent_state.json', {}) || {};
  const next = { ...cur, ...patch, updated_at: new Date().toISOString() };
  const tmp = gpath('agent_state.json.tmp');
  try {
    fs.writeFileSync(tmp, JSON.stringify(next, null, 1) + '\n', { mode: 0o644 });
    fs.renameSync(tmp, gpath('agent_state.json'));
  } catch (e) { console.error('writeState:', e.message); }
}

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

function run(cmd, args, { timeoutMs = 150000 } = {}) {
  const r = spawnSync(cmd, args, { cwd: ROOT, timeout: timeoutMs, encoding: 'utf8' });
  return { ok: r.status === 0, out: (r.stdout || '') + (r.stderr || ''), status: r.status };
}

function aliveLogin() {
  const r = spawnSync('pgrep', ['-f', 'node login.mjs'], { encoding: 'utf8' });
  return r.status === 0;
}
function sessionWs() {
  try { return fs.readFileSync(path.join(ROOT, 'session.txt'), 'utf8').trim(); }
  catch { return ''; }
}

let jobRunning = false;

// ---------- job 1: minta login baru (OTP email dikirim portal) ----------
async function startLogin(req) {
  jobRunning = true;
  try {
    writeState({ state: 'starting', msg: 'Menyiapkan browser login…', requested_by: req?.by || '?' });
    // Xvfb khusus agen (:98, TANPA -auth) — :99 kadang milik xvfb-run
    // lama dengan Xauthority, koneksi tanpa XAUTHORITY ditolak
    // ("Missing X server" dari puppeteer). Display ini dijamin bebas.
    const xv = spawnSync('pgrep', ['-f', '^Xvfb :98'], { encoding: 'utf8' });
    if (xv.status !== 0) {
      spawn('Xvfb', [':98', '-screen', '0', '1200x900x24', '-nolisten', 'tcp'],
            { detached: true, stdio: ['ignore', 'ignore', 'ignore'] }).unref();
      await sleep(1500);
    }
    // hentikan login lama & sesi lama
    spawnSync('pkill', ['-f', 'node login.mjs']);
    try { fs.unlinkSync(path.join(ROOT, 'session.txt')); } catch {}
    const log = fs.openSync(path.join(ROOT, 'artifacts/otp_login.log'), 'a');
    spawn('node', ['login.mjs'], {
      cwd: ROOT, detached: true, env: { ...process.env, DISPLAY: ':98' },
      stdio: ['ignore', log, log],
    }).unref();
    try { fs.unlinkSync(gpath('otp_request.json')); } catch {}
    writeState({ state: 'starting', msg: 'login.mjs berjalan — menunggu halaman OTP portal…' });
    // deteksi halaman OTP: session.txt tertulis (setelah submit berhasil)
    for (let i = 0; i < 45; i++) {          // ≤ ~3 menit
      await sleep(TICK_MS);
      if (sessionWs()) {
        writeState({
          state: 'waiting_otp',
          msg: 'OTP dikirim ke email akun Subsidi Tepat — masukkan 6 digitnya di dashboard.',
        });
        jobRunning = false;
        return;
      }
      if (!aliveLogin()) {
        const out = fs.existsSync(path.join(ROOT, 'artifacts/otp_login.log'))
          ? fs.readFileSync(path.join(ROOT, 'artifacts/otp_login.log'), 'utf8').slice(-500) : '';
        writeState({ state: 'error', msg: 'Login gagal — halaman OTP tidak muncul. ' + out.slice(-260) });
        jobRunning = false;
        return;
      }
    }
    writeState({ state: 'error', msg: 'Timeout menunggu halaman OTP (login lambat?) — coba Minta OTP lagi.' });
  } finally {
    jobRunning = false;
  }
}

// ---------- job 2: verifikasi OTP + sinkron penuh ----------
async function verifyAndSync(sub) {
  jobRunning = true;
  try {
    const code = String(sub?.code || '');
    const ws = sessionWs();
    if (!ws || !aliveLogin()) {
      writeState({ state: 'error', msg: 'Sesi login sudah mati — klik Minta OTP Email lagi.' });
      try { fs.unlinkSync(gpath('otp_submit.json')); } catch {}
      return;
    }
    writeState({ state: 'verifying', msg: `Memverifikasi OTP ${code} ke portal…` });
    const verifyRes = run('node', ['verify.mjs', code], { timeoutMs: 120000 });
    try { fs.unlinkSync(gpath('otp_submit.json')); } catch {}
    const tok = path.join(ROOT, 'token.json');
    const tokOk = verifyRes.out.includes('✅ token disimpan')
      || (fs.existsSync(tok) && Date.now() - fs.statSync(tok).mtimeMs < 120000);
    if (!tokOk) {
      const tail = verifyRes.out.split('\n').filter(Boolean).slice(-3).join(' | ').slice(-300);
      writeState({ state: 'error', msg: 'Verifikasi OTP gagal — cek ulang kode email: ' + tail });
      return;
    }
    writeState({ state: 'syncing', msg: 'Token baru OK — menarik riwayat SPBU…' });
    const pull = run('node', ['pull.mjs', '32'], { timeoutMs: 240000 });
    const total = (pull.out.match(/Total: (\d+) transaksi/) || [])[1];
    if (!pull.ok) {
      writeState({ state: 'error', msg: 'Tarik data gagal: ' + pull.out.split('\n').filter(Boolean).slice(-2).join(' | ').slice(-260) });
      return;
    }
    const push = run('node', ['push.mjs'], { timeoutMs: 120000 });
    if (!push.ok) {
      writeState({ state: 'error', msg: `Impor ke bpf-workhub gagal: ${push.out.slice(-200)}` });
      return;
    }
    // pencocokan advisory 1 klik (analisis perlengkapan berbasis .env token)
    const TOKEN = process.env.SUBSIDY_IMPORT_TOKEN || ENV.SUBSIDY_IMPORT_TOKEN || '';
    let matchMsg = '';
    if (TOKEN) {
      const r = spawnSync('curl', ['-s', '-X', 'POST', `${API}/api/subsidy/auto-match`,
        '-H', `X-SUBSIDY-TOKEN: ${TOKEN}`], { timeout: 60000, encoding: 'utf8' });
      try { matchMsg = ' · ' + (JSON.parse(r.stdout || '{}').msg || ''); } catch {}
    }
    writeState({
      state: 'done',
      msg: `✅ Selesai: ${total || '?'} transaksi ditarik & diimpor${matchMsg}`.slice(0, 400),
    });
  } finally {
    jobRunning = false;
  }
}

// ---------- watchdog: sesi mati tanpa selesai ----------
function watchdog(st) {
  if (st?.state === 'waiting_otp' && !aliveLogin()) {
    const ws = sessionWs();
    if (!ws) {
      writeState({ state: 'error', msg: 'Browser login tertutup tiba-tiba — klik Minta OTP Email lagi.' });
      lastReqAt = '';
    }
  }
}

// ---------- loop utama ----------
(async function main() {
  fs.mkdirSync(GATE, { recursive: true });
  fs.mkdirSync(path.join(ROOT, 'artifacts'), { recursive: true });
  console.log(`otp_supervisor: gate=${GATE} api=${API} tick=${TICK_MS}ms`);
  writeState({ state: readJson('agent_state.json', {})?.state || 'idle' });
  for (;;) {
    try {
      const st = readJson('agent_state.json', {}) || {};
      const req = readJson('otp_request.json');
      const sub = readJson('otp_submit.json');
      if (req && req.requested_at && req.requested_at !== lastReqAt && !jobRunning) {
        lastReqAt = req.requested_at;
        startLogin(req);                       // async — jangan await loop
      } else if (sub && sub.submitted_at && sub.submitted_at !== lastSubAt && !jobRunning) {
        lastSubAt = sub.submitted_at;
        verifyAndSync(sub);
      } else if (!jobRunning) {
        watchdog(st);
      }
    } catch (e) {
      console.error('tick error:', e.message);
    }
    await sleep(TICK_MS);
  }
})();
