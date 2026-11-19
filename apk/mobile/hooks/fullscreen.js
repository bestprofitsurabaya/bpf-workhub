'use strict';
/**
 * Hook after_prepare (Android): patch MainActivity dengan immersive sticky —
 * status bar & navigation bar disembunyikan (edge-to-edge penuh), geser dari
 * tepi layar untuk memunculkannya sementara. Ini yang menghilangkan bar hitam.
 *
 * Idempotent: dipasang hanya sekali (berdasar penanda // BPF-IMMERSIVE).
 */
const fs = require('fs');
const path = require('path');

module.exports = function (ctx) {
  if (!ctx.opts.platforms || !ctx.opts.platforms.includes('android')) return;

  const javaRoot = path.join(ctx.opts.projectRoot, 'platforms', 'android',
    'app', 'src', 'main', 'java');
  if (!fs.existsSync(javaRoot)) {
    console.log('[fullscreen] src/main/java tidak ada (bukan target android)');
    return;
  }

  let mainActivity = null;
  const walk = (dir) => {
    for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, ent.name);
      if (ent.isDirectory()) walk(p);
      else if (ent.name === 'MainActivity.java') mainActivity = p;
    }
  };
  walk(javaRoot);

  if (!mainActivity) {
    console.log('[fullscreen] MainActivity.java tidak ditemukan — lewati');
    return;
  }

  const MARK = '// BPF-FULLSCREEN-ENABLE';
  let src = fs.readFileSync(mainActivity, 'utf8');
  if (src.includes(MARK)) {
    console.log('[fullscreen] patch sudah ada — dilewati');
    return;
  }

  const inject = [
    '',
    '        ' + MARK,
    '        // (opsional) sembunyikan status bar & nav bar penuh (full screen tanpa bar hitam)',
    '        androidx.core.view.WindowCompat.setDecorFitsSystemWindows(getWindow(), false);',
    '        androidx.core.view.WindowInsetsControllerCompat insetCtrl =',
    '            new androidx.core.view.WindowInsetsControllerCompat(getWindow(), getWindow().getDecorView());',
    '        insetCtrl.hide(androidx.core.view.WindowInsetsCompat.Type.systemBars());',
    '        insetCtrl.setSystemBarsBehavior(',
    '            androidx.core.view.WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);',
    '',
    '',
  ].join('\n');

  const anchor = 'super.onCreate(savedInstanceState);';
  if (!src.includes(anchor)) {
    console.log('[fullscreen] anchor onCreate tidak ditemukan — lewati');
    return;
  }
  src = src.replace(anchor, anchor + inject);
  fs.writeFileSync(mainActivity, src);
  console.log('[fullscreen] immersive ditambahkan ke ' + mainActivity);
};
