// Stage B — verifikasi OTP (dipanggil SETELAH email OTP tiba)
//   node verify.mjs <kode_otp>
// Menghubung ke browser yang masih hidup (session.txt), mengisi kode,
// menekan verifikasi, lalu menarik cookie __mpv-token → token.json (mode 600).
import puppeteer from 'puppeteer-core';
import fs from 'fs';
import path from 'path';

const DIR = path.dirname(new URL(import.meta.url).pathname);
const otp = process.argv[2];
const sessionFile = path.join(DIR, 'session.txt');
const tokenFile = path.join(DIR, 'token.json');

if (!otp) { console.error('pakai: node verify.mjs <kode_otp>'); process.exit(1); }
if (!fs.existsSync(sessionFile)) { console.error('session.txt tidak ada — jalankan login.mjs dulu'); process.exit(1); }
const ws = fs.readFileSync(sessionFile, 'utf8').trim();
if (!ws) { console.error('session.txt kosong'); process.exit(1); }

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

async function main() {
  const browser = await puppeteer.connect({ browserWSEndpoint: ws, defaultViewport: null });
  const pages = await browser.pages();
  const page = pages[0];
  console.log('URL sekarang:', page.url());

  // --- isi field OTP (bisa 6 digit utuh atau 6 kotak terpisah) -----------
  const boxes = await page.$$('input[inputmode=numeric], input[type=tel]');
  console.log('input OTP ditemukan:', boxes.length);
  if (boxes.length >= 6) {
    for (let i = 0; i < 6; i++) { await boxes[i].type(otp[i]); await sleep(150 + Math.random() * 150); }
  } else {
    const one = boxes[0] || await page.$('input[name*=otp i], input[placeholder*=otp i], input[type=tel]');
    if (!one) { console.error('(!) field OTP tidak ketemu'); process.exit(2); }
    await one.type(otp, { delay: 60 });
  }
  await page.screenshot({ path: path.join(DIR, 'artifacts/05_otp_filled.png') });

  // --- submit ------------------------------------------------------------
  const btn = await page.$('button[type=submit]') || await page.$('form button');
  if (btn) { await btn.click(); console.log('verifikasi dikirim...'); }

  // --- intersep response verifikasi --------------------------------------
  let resp = null;
  page.on('response', async r => {
    const u = r.url() || '';
    if (u.includes('otp-verification') || u.includes('otp')) resp = r;
    if (r.url().includes('otp-verification')) {
      console.log(`>> ${r.status()} ${u}`);
      try { console.log('   body:', (await r.text()).slice(0, 300)); } catch {}
    }
  });

  // deteksi sukses: URL keluar dari otp atau toast "berhasil"
  for (let i = 0; i < 20; i++) {
    await sleep(2000);
    const { url, cookies, txt } = await page.evaluate(() => ({
      url: location.href,
      txt: document.body?.innerText?.slice(0, 500) || '',
    }));
    console.log(`[t${i}] ${url}`);
    if (/.*\/(app|dashboard|profile|professional|home)/.test(url) || /berhasil/i.test(txt)) {
      break;
    }
  }
  await page.screenshot({ path: path.join(DIR, 'artifacts/06_post_otp.png') });

  // --- tarik cookie & localStorage token ---------------------------------
  const cookies = await browser.cookies();
  const interesting = cookies.filter(c =>
    c.name.includes('token') || c.name.includes('session') || c.name.includes('myptm') || c.name.includes('mpv'));
  console.log('cookies:', JSON.stringify(interesting, null, 1).slice(0, 1500));
  const storage = await page.evaluate(() => {
    const out = {};
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (/token|session|profile|myptm|mpv/i.test(k)) out[k] = localStorage.getItem(k);
    }
    return out;
  });
  console.log('storage keys:', Object.keys(storage));

  const bearer = (interesting.find(c => c.name === '__mpv-token') || {}).value
    || storage['__mpv-token']
    || storage['myptm-corporate-subsidy'];
  if (bearer) {
    fs.writeFileSync(tokenFile, JSON.stringify({
      token: bearer,
      at: new Date().toISOString(),
      cookies: interesting,
      storage,
    }, null, 1), { mode: 0o600 });
    console.log('✅ token disimpan →', tokenFile, `(len ${bearer.length})`);
  } else {
    console.log('⚠ token belum ketemu — lihat 06_post_otp.png / cookies di atas');
    fs.writeFileSync(path.join(DIR, 'cookies.json'), JSON.stringify(cookies, null, 1), { mode: 0o600 });
  }
  await browser.disconnect();
}

main().catch(e => { console.error('FATAL', e); process.exit(1); });
