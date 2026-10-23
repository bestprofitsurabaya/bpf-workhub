// ============================================================
// MyPertamina "Subsidi Tepat" — browser driver (akun pribadi)
// ------------------------------------------------------------
// Prinsip: akses akun sendiri via browser nyata (Chrome for Testing)
// reCAPTCHA v3 dihasilkan halaman itu sendiri; OTP email dimasukkan
// manual oleh pemilik akun SEKALI — token `__mpv-token` disimpan utk
// pull data berikutnya tanpa OTP.
//   npm i puppeteer-core
//   node login.mjs
// ============================================================
import puppeteer from 'puppeteer-core';
import fs from 'fs';
import path from 'path';
import readline from 'readline';

const DIR = path.dirname(new URL(import.meta.url).pathname);
const ENV = Object.fromEntries(fs.readFileSync(path.join(DIR, '.env'), 'utf8')
  .trim().split('\n').filter(l => l.includes('=')).map(l => {
    const i = l.indexOf('=');
    return [l.slice(0, i).trim(), l.slice(i + 1).trim()];
  }));

const CHROME = '/home/it-ef/.local/bin/chrome';  // symlink chrome/chromium sama
const PROFILE = path.join(DIR, 'profile');      // sesi persist (anti detect ulang)
const LOGIN_URL = process.env.MPV_URL || 'https://subsiditepat.mypertamina.id/login';

const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const shot = (page, name) => page.screenshot({ path: path.join(DIR, `${name}.png`) });
const dumpDOM = (page, name) => page.content().then(h =>
  fs.writeFileSync(path.join(DIR, `${name}.html`), h));

async function main() {
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: false,               // headful — dijalankan dalam Xvfb (anti cap 'Headless')
    userDataDir: PROFILE,
    args: [
      '--no-sandbox',
      '--disable-blink-features=AutomationControlled',
      '--window-size=1200,900',
      '--lang=id-ID',
    ],
    defaultViewport: { width: 1200, height: 900 },
    env: { ...process.env, DISPLAY: process.env.DISPLAY || ':99' },
  });
  const page = (await browser.pages())[0] || await browser.newPage();
  page.setDefaultNavigationTimeout(45000);
  // UA asli (headless=new memakai "HeadlessChrome") — reCAPTCHA v3 menilai UA.
  const ua = await browser.userAgent();
  console.log('UA bawaan:', ua);
  await page.setUserAgent(ua.replace('HeadlessChrome/', 'Chrome/').replace(/Chrome\/(\d+)/, 'Chrome/151'));

  await page.goto(LOGIN_URL, { waitUntil: 'networkidle2' }).catch(e => console.log('(!) nav:', e.message));
  await sleep(2500);
  await shot(page, '01_awal');
  await dumpDOM(page, '01_awal');

  // --- deteksi semua input — keputusan cerdas mana NIK/password ----------
  const inputs = await page.evaluate(() =>
    [...document.querySelectorAll('input')].map(i => ({
      type: i.type, name: i.name || '', id: i.id || '',
      placeholder: i.placeholder || '', ariaLabel: i.ariaLabel || i.getAttribute('aria-label') || '',
      autocomplete: i.autocomplete || '', visible: !!(i.offsetParent || i.getClientRects().length),
      cls: (i.className || '').slice(0, 80),
    })).filter(i => i.visible && !i.type.match(/hidden|checkbox|submit|button/i))
  );
  console.log('INPUTS:', JSON.stringify(inputs, null, 1));

  // --- petakan NIK & password -------------------------------------------
  const nikField = inputs.find(i => /nik|national|user|email|name/i.test((i.placeholder + i.name + i.id + i.ariaLabel + i.autocomplete)))
    || inputs[0];
  const passField = inputs.find(i => i.type === 'password');
  if (!nikField || !passField) {
    console.log('(!) field tidak terdeteksi — lihat 01_awal.png & 01_awal.html');
    console.log('STATUS: MANUAL_LNYUT');
    fs.writeFileSync(path.join(DIR, 'session.txt'), '');
    await browser.disconnect?.();
    process.exit(2);
  }
  const fillBy = i => page.waitForSelector(`input${i.id ? '#' + CSS.escape(i.id) : ''}`, { visible: true });
  // gunakan CSS.escape selalu (id bisa kosong → pakai nth-of-type fallback)
  const all = await page.$$('input');
  let nikEl = null, passEl = null;
  for (const el of all) {
    const info = await el.evaluate(i => ({ type: i.type, vis: !!(i.offsetParent || i.getClientRects().length), old: (i.name + i.id + i.placeholder + (i.getAttribute('aria-label') || '') + i.autocomplete).toLowerCase(), hidden: i.type }));
    if (!info.vis) continue;
    if (info.hidden === 'password') passEl = passEl || el;
    else if ((info.old.match(/nik|national|user|email|name/i) || info === inputs[0])) nikEl = nikEl || el;
  }
  nikEl = nikEl || all[0];
  // Perilaku manusia: gerak mouse + typing lambat — reCAPTCHA v3 menilai pola ini.
  for (let i = 0; i < 5; i++) {
    await page.mouse.move(200 + Math.random() * 600, 150 + Math.random() * 500);
    await sleep(180 + Math.random() * 250);
  }
  await nikEl.click({ delay: 40 });
  await nikEl.type(ENV.NICK, { delay: 40 + Math.random() * 90 });
  await sleep(400 + Math.random() * 900);
  if (passEl) {
    await passEl.click({ delay: 40 });
    await passEl.type(ENV.PASS, { delay: 40 + Math.random() * 90 });
  }
  await sleep(1200 + Math.random() * 1500);
  await shot(page, '02_terisi');

  // --- submit ------------------------------------------------------------
  const btn = (await page.$$('button[type=submit]'))[0]
    || (await page.$$('form button'))[0];
  if (!btn) { console.log('(!) tombol submit tidak ketemu'); }
  else {
    await btn.click();
    console.log('submit dikiriiim — tunggu respons...');
  }
  // intersep request + respons API login — untuk diagnosis 400
  page.on('request', r => {
    const u = r.url() || '';
    if (u.includes('gateway/auth') || u.includes('auth/login') || u.includes('otp')) {
      console.log(`>> REQ ${r.method()} ${u}`);
      console.log('   headers:', JSON.stringify(Object.fromEntries(Object.entries(r.headers()).filter(([k]) => /recaptcha|login-session|content-type|cookie/i.test(k))), null, 1));
      const pd = r.postData();
      if (pd) console.log('   body:', pd.slice(0, 500));
    }
  });
  page.on('response', async r => {
    const u = r.url() || '';
    if (u.includes('gateway/auth') || u.includes('auth/login') || u.includes('otp')) {
      console.log(`>> RESP ${r.status()} ${u}`);
      try { console.log('   body:', (await r.text()).slice(0, 600)); } catch {}
    }
  });

  // deteksi OTP/email-bypass: pola kosakata halaman
  const detect = async () => {
    const txt = ((await page.evaluate(() => document.body.innerText)) || '').toLowerCase();
    return {
      otp: /(masukkan.*otp|kode otp|verifikasi.*otp|otp method|kode verifikasi|pilih jenis otp)/.test(txt),
      method: /pilih jenis otp/.test(txt),       // halaman pemilih metode (email/sms)
      sent: /(kirim ulang|resend|kode otp.*dikirim|terkirim)/.test(txt),
      tnc: /syarat.*ketentuan|setujui.*ketentuan/.test(txt) && txt.length < 1200,
      bad: /(salah|tidak sesuai|tidak ditemukan|terlalu banyak)/.test(txt),
    };
  };
  // OTP tidak pernah terkirim sampai: (1) metode Email dipilih, lalu
  // (2) tombol "Kirim Kode Verifikasi" diklik. Keduanya klik Puppeteer
  // tepercaya (bukan .click() DOM yg diabaikan React/Mantine).
  const clickBtn = async (re) => {
    const handles = await page.$$('button');
    for (const h of handles) {
      const t = ((await h.evaluate((el) => el.innerText)) || '').trim();
      if (re.test(t)) { await h.click(); return true; }
    }
    return false;
  };
  const pickEmailOtp = async () => {
    try {
      // (1) pilih radio Email
      const picked = await clickBtn(/email/i);
      console.log(picked ? 'Radio Email dipilih (trusted)' : '(!) tombol Email tidak ketemu');
      if (!picked) return false;
      await sleep(1200);
      // (2) tekan Kirim Kode Verifikasi — inilah yg memicu dispatch OTP
      const sent = await clickBtn(/kirim kode verifikasi|kirim kode|kirim otp/i);
      console.log(sent ? '"Kirim Kode Verifikasi" ditekan — menunggu dispatch…' : '(!) tombol Kirim Kode tidak ketemu');
      return sent;
    } catch (e) {
      console.log('(!) pickEmailOtp:', e.message);
      return false;
    }
  };
  // OTP_SENT hanya bila halaman metode sudah hilang (pindah ke halaman
  // isi kode) atau ada konfirmasi "kirim ulang/terkirim" — jangan anggap
  // memilih metode = sudah terkirim.
  let flag = null, pickedMethod = false;
  for (let i = 0; i < 30 && flag !== 'OTP_SENT'; i++) {
    await sleep(2500);
    const d = await detect();
    await shot(page, `03_wait_${i}`);
    if (d.method && !pickedMethod) {
      pickedMethod = await pickEmailOtp();
      await sleep(3000);
    } else if (pickedMethod && !d.method) {
      // halaman metode hilang → sudah di halaman isi kode = OTP terkirim
      flag = 'OTP_SENT';
    } else if (pickedMethod && d.sent) {
      flag = 'OTP_SENT';
    } else if (i >= 8 && d.bad) {
      flag = 'CRED_ABNORMAL';
    }
  }
  const urlNow = page.url();
  console.log('URL sekarang:', urlNow);
  console.log('STATUS:', flag || 'INDUKSI_MANUAL');
  await shot(page, '04_post_submit');
  await dumpDOM(page, '04_post_submit');
  const ws = browser.wsEndpoint();
  fs.writeFileSync(path.join(DIR, 'session.txt'), ws);
  console.log('Browser TETAP hidup — bila OTP dikirim email, panggil verify.mjs');
  console.log('WS=' + ws);
  console.log('** KODE OTP dari email YANG TERSEBUT — jalankan: node verify.mjs <kode>');
  // tahan proses (browser & CDP tetap hidup) sampai di-kill manual
  setInterval(() => {}, 60000);
}

main().catch(e => { console.error('FATAL', e); process.exit(1); });
