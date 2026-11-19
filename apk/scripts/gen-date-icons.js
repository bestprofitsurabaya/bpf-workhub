'use strict';
/* Bangkitkan 31 ikon tanggal launcher (1..31) — gaya ikon kalender:
   piringan putih rounded, band merah "BPF", angka tanggal navy (logo BestProfit).
   Densitas: mdpi 48, hdpi 72, xxxhdpi 192. Butuh fontconfig (tools/iconfonts)
   + sharp di tools/icon-gen. Dijalankan dari repo root:
     FONTCONFIG_FILE=$PWD/tools/iconfonts/fonts.conf node scripts/gen-date-icons.js  */
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');
const sharp = require(path.join(ROOT, 'tools', 'icon-gen', 'node_modules', 'sharp'));
const OUTROOT = path.join(ROOT, 'mobile', 'res', 'date-icon');

const WMAP = { mdpi: 48, hdpi: 72, xxxhdpi: 192 };

const template = (W, day) => {
  const R = Math.round(W * 0.16);
  const bandY = Math.round(W * 0.27);
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${W}">
  <rect x="0" y="0" width="${W}" height="${W}" rx="${R}" ry="${R}" fill="#ffffff"/>
  <path d="M0,${bandY} L0,${R} Q0,0 ${R},0 L${W - R},0 Q${W},0 ${W},${R} L${W},${bandY} Z" fill="#ed1c24"/>
  <text x="${W / 2}" y="${Math.round(W * 0.2)}" font-size="${Math.round(W * 0.14)}" font-weight="bold"
        text-anchor="middle" dominant-baseline="middle" fill="#ffffff" font-family="DejaVu Sans">BPF</text>
  <text x="${W / 2}" y="${Math.round(W * 0.63)}" font-size="${Math.round(W * 0.42)}" font-weight="bold"
        text-anchor="middle" dominant-baseline="middle" fill="#22307a" font-family="DejaVu Sans">${day}</text>
</svg>`;
};

(async () => {
  for (const [den, W] of Object.entries(WMAP)) {
    const dir = path.join(OUTROOT, den);
    fs.mkdirSync(dir, { recursive: true });
    for (let d = 1; d <= 31; d++) {
      await sharp(Buffer.from(template(W, d))).png().toFile(path.join(dir, `bpfday${d}.png`));
    }
    console.log(den, W + 'px — 31 ikon OK');
  }
})().catch((e) => { console.error('GAGAL:', e.message); process.exit(1); });
