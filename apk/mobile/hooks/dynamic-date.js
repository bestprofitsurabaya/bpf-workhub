'use strict';
/**
 * Hook after_prepare (Android): bikin LAUNCHER ICON tanggal-hidup + WIDGET 1×1.
 * - 31 activity-alias (.bpfDay1..31) masing-masing ikon angka tanggal; receiver
 *   to Serahkan alias tiap ganti hari (BOOT/DATE_CHANGED/TIME_SET/alarms) + saat app dibuka.
 * - AppWidget 1×1 menampilkan bulan + tanggal (merah/navy BestProfit), tap buka app.
 * - Widget & ikon juga difresh saat app dibuka (MainActivity.onResume).
 * Idempotent dengan penanda BPF-DATELIVE.
 */
const fs = require('fs');
const path = require('path');

const MONTHS = ['JAN', 'FEB', 'MAR', 'APR', 'MEI', 'JUN', 'JUL', 'AGU', 'SEP', 'OKT', 'NOV', 'DES'];

module.exports = function (ctx) {
  if (!ctx.opts.platforms || !ctx.opts.platforms.includes('android')) return;
  const root = ctx.opts.projectRoot;
  const android = path.join(root, 'platforms', 'android', 'app', 'src', 'main');
  if (!fs.existsSync(path.join(android, 'AndroidManifest.xml'))) {
    console.log('[datelive] AndroidManifest.xml tidak ada (bukan target android) — lewati');
    return;
  }
  const manifestPath = path.join(android, 'AndroidManifest.xml');
  let manifest = fs.readFileSync(manifestPath, 'utf8');
  // package namespace dari cdv-gradle-config.json (root manifest tidak memuat attribute copy di tempatnya)
  let pkg = '';
  try {
    const cfg = JSON.parse(fs.readFileSync(
      path.join(root, 'platforms', 'android', 'cdv-gradle-config.json'), 'utf8'));
    pkg = cfg.PACKAGE_NAMESPACE || '';
  } catch { /* fallback di bawah */ }
  if (!pkg) pkg = (manifest.match(/package="([^"]+)"/) || [])[1] || '';
  if (!pkg) { console.log('[datelive] package tidak ketemu'); return; }

  /* ---------- 1) copy 31 ikon x 3 densitas ---------- */
  const DENS = { mdpi: 48, hdpi: 72, xxxhdpi: 192 };
  for (const [den] of Object.entries(DENS)) {
    const srcDir = path.join(root, 'res', 'date-icon', den);
    if (!fs.existsSync(srcDir)) { console.log(`[datelive] ikon ${den} tidak ada — jalankan scripts/gen-date-icons.js`); continue; }
    const dstDir = path.join(android, 'res', `mipmap-${den}`);
    fs.mkdirSync(dstDir, { recursive: true });
    for (let d = 1; d <= 31; d++) {
      fs.copyFileSync(path.join(srcDir, `bpfday${d}.png`), path.join(dstDir, `bpfday${d}.png`));
    }
  }
  console.log('[datelive] ikon tanggal (31 x 3) tersalin ke res/mipmap-*');

  /* ---------- 2) java: DateLive, DateReceiver, DateWidgetProvider ---------- */
  const javaPkgs = path.join(android, 'java', ...pkg.split('.'));
  const javaLive = path.join(android, 'java', 'bpf', 'datelive');
  fs.mkdirSync(javaLive, { recursive: true });
  const R_IMPORT = `import ${pkg}.R;`;

  fs.writeFileSync(path.join(javaLive, 'DateLive.java'), `
package bpf.datelive;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.widget.RemoteViews;

import java.util.Calendar;

${R_IMPORT}

/** Sinkron ikon launcher (alias harian) + widget tanggal + alarm tengahmalam. */
public final class DateLive {

    public static void refresh(Context ctx) {
        try {
            Calendar c = Calendar.getInstance();
            setLauncherIcon(ctx, c.get(java.util.Calendar.DAY_OF_MONTH));
            updateWidget(ctx);
            scheduleMidnight(ctx);
        } catch (Exception e) {
            android.util.Log.e("BPFDateLive", "refresh gagal", e);
        }
    }

    // aktifkan alias .bpfDayN sesuai tanggal hari ini
    static void setLauncherIcon(Context ctx, int day) {
        try {
            PackageManager pm = ctx.getPackageManager();
            String p = ctx.getPackageName();
            for (int i = 1; i <= 31; i++) {
                ComponentName cn = new ComponentName(p, p + ".bpfDay" + i);
                boolean want = (i == day);
                int curState = pm.getComponentEnabledSetting(cn);
                if ((want && curState == PackageManager.COMPONENT_ENABLED_STATE_ENABLED)
                    || (!want && curState == PackageManager.COMPONENT_ENABLED_STATE_DISABLED)) {
                    continue;
                }
                pm.setComponentEnabledSetting(cn, want
                    ? PackageManager.COMPONENT_ENABLED_STATE_ENABLED
                    : PackageManager.COMPONENT_ENABLED_STATE_DISABLED,
                    PackageManager.DONT_KILL_APP);
            }
        } catch (Exception e) {
            android.util.Log.e("BPFDateLive", "setLauncherIcon gagal", e);
        }
    }

    static void updateWidget(Context ctx) {
        try {
            AppWidgetManager awm = AppWidgetManager.getInstance(ctx);
            if (awm == null) return;
            int[] ids = awm.getAppWidgetIds(new ComponentName(ctx, DateWidgetProvider.class));
            if (ids == null || ids.length == 0) return;

            Calendar c = Calendar.getInstance();
            java.util.Locale loc = java.util.Locale.getDefault();
            String month = MONTHS[c.get(java.util.Calendar.MONTH)];

            RemoteViews rv = new RemoteViews(ctx.getPackageName(), R.layout.bpf_date_widget);
            rv.setTextViewText(R.id.wiMonth, month);
            rv.setTextViewText(R.id.wiDay, String.valueOf(c.get(java.util.Calendar.DAY_OF_MONTH)));
            rv.setTextViewText(R.id.wiAgenda, agendaText(ctx));

            Intent open = ctx.getPackageManager().getLaunchIntentForPackage(ctx.getPackageName());
            if (open != null) {
                open.addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK);
                PendingIntent pi = PendingIntent.getActivity(ctx, 1, open,
                    PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
                rv.setOnClickPendingIntent(R.id.widRoot, pi);
            }
            awm.updateAppWidget(ids, rv);
        } catch (Exception e) {
            android.util.Log.w("BPFDateLive", "updateWidget: " + e);
        }
    }

    // teks agenda hari ini (ditulis aplikasi lewat aksi widgetAgenda).
    // Kalau tanggal tersimpan bukan hari ini, widget tidak menampilkan agenda lama.
    static String agendaText(Context ctx) {
        try {
            android.content.SharedPreferences sp = ctx.getSharedPreferences("bpf_widget", Context.MODE_PRIVATE);
            String today = new java.text.SimpleDateFormat("yyyy-MM-dd", java.util.Locale.US)
                .format(new java.util.Date());
            if (!today.equals(sp.getString("date", ""))) return "Belum ada agenda hari ini";
            String t = sp.getString("agenda", "");
            if (t == null || t.trim().isEmpty()) return "Belum ada agenda hari ini";
            return t;
        } catch (Exception e) {
            return "Belum ada agenda hari ini";
        }
    }

    /** Simpan agenda hari ini lalu perbarui widget (dipanggil dari plugin bpfBridge). */
    public static void setAgenda(Context ctx, String date, String text) {
        try {
            android.content.SharedPreferences sp = ctx.getSharedPreferences("bpf_widget", Context.MODE_PRIVATE);
            sp.edit()
                .putString("date", date == null ? "" : date)
                .putString("agenda", text == null ? "" : text)
                .apply();
            updateWidget(ctx);
        } catch (Exception e) {
            android.util.Log.w("BPFDateLive", "setAgenda: " + e);
        }
    }

    static void scheduleMidnight(Context ctx) {
        try {
            AlarmManager am = (AlarmManager) ctx.getSystemService(Context.ALARM_SERVICE);
            if (am == null) return;
            Intent i = new Intent(ctx, DateReceiver.class).setAction(DateReceiver.MIDNIGHT);
            PendingIntent pi = PendingIntent.getBroadcast(ctx, 42, i,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
            if (pi == null) return;
            Calendar next = Calendar.getInstance();
            next.add(java.util.Calendar.DAY_OF_MONTH, 1);
            next.set(java.util.Calendar.HOUR_OF_DAY, 0);
            next.set(java.util.Calendar.MINUTE, 0);
            next.set(java.util.Calendar.SECOND, 0);
            next.set(java.util.Calendar.MILLISECOND, 0);
            // window 1 menit supaya ganti hari pas; tanpa izin exact alarm
            am.setWindow(AlarmManager.RTC, next.getTimeInMillis(), 60000, pi);
        } catch (Exception e) {
            android.util.Log.w("BPFDateLive", "scheduleMidnight: " + e);
        }
    }

    // BPF-WIDGET: pin widget 1x1 ke home screen via launcher (requestPinAppWidget)
    public static boolean addWidget(Context ctx) {
        try {
            android.appwidget.AppWidgetManager awm = android.appwidget.AppWidgetManager.getInstance(ctx);
            if (awm == null) return false;
            if (!awm.isRequestPinAppWidgetSupported()) return false;
            android.content.ComponentName cn = new android.content.ComponentName(ctx, bpf.datelive.DateWidgetProvider.class);
            android.app.PendingIntent ppi = android.app.PendingIntent.getActivity(ctx, 77,
                new android.content.Intent(ctx, id.co.bpf.calendar.MainActivity.class),
                android.app.PendingIntent.FLAG_UPDATE_CURRENT | android.app.PendingIntent.FLAG_IMMUTABLE);
            boolean ok = awm.requestPinAppWidget(cn, new android.os.Bundle(), ppi);
            android.util.Log.d("BPFDateLive", "addWidget: request ok=" + ok);
            return ok;
        } catch (Exception e) {
            android.util.Log.e("BPFDateLive", "addWidget gagal", e);
            return false;
        }
    }

    // BPF-NOTIF: kirim notifikasi lokal (dipicu saat ada agenda baru dari admin)
    public static void notifyNew(Context ctx, String title, String msg) {
        try {
            android.app.NotificationManager nm = (android.app.NotificationManager) ctx.getSystemService(android.content.Context.NOTIFICATION_SERVICE);
            if (nm == null) return;
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
                String chId = "bpf.calendar.channel";
                android.app.NotificationChannel ch = nm.getNotificationChannel(chId);
                if (ch == null) {
                    ch = new android.app.NotificationChannel(chId, "BPF Agenda", android.app.NotificationManager.IMPORTANCE_DEFAULT);
                    nm.createNotificationChannel(ch);
                }
            }
            android.app.Notification n = new android.app.Notification.Builder(ctx, "bpf.calendar.channel")
                .setSmallIcon(android.R.drawable.ic_dialog_info)
                .setContentTitle(title)
                .setContentText(msg)
                .setAutoCancel(true)
                .build();
            nm.notify(4242, n);
        } catch (Exception e) {
            android.util.Log.e("BPFDateLive", "notifyNew gagal", e);
        }
    }

    private static final String[] MONTHS = MONTHS_LIST;

    private DateLive() {}
}
`.replace('MONTHS_LIST', `{"${MONTHS.join('","')}"}`));

  fs.writeFileSync(path.join(javaLive, 'DateReceiver.java'), `
package bpf.datelive;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** Dipicu saat tanggal/zona berubah, boot, atau alarm tengahmalam. */
public class DateReceiver extends BroadcastReceiver {
    public static final String MIDNIGHT = "bpf.datelive.MIDNIGHT";

    @Override
    public void onReceive(Context ctx, Intent i) {
        DateLive.refresh(ctx);
    }
}
`);

  fs.writeFileSync(path.join(javaLive, 'DateWidgetProvider.java'), `
package bpf.datelive;

import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.Context;

/** Widget 1x1: bulan + tanggal, tap untuk membuka aplikasi. */
public class DateWidgetProvider extends AppWidgetProvider {
    @Override
    public void onUpdate(Context ctx, AppWidgetManager awm, int[] ids) {
        DateLive.refresh(ctx);
    }

    @Override
    public void onEnabled(Context ctx) {
        DateLive.refresh(ctx);
    }
}
`);
  console.log('[datelive] kelas java bpf.datelive ditulis');

  /* ---------- 3) widget xml, layout, drawable ---------- */
  fs.mkdirSync(path.join(android, 'res', 'xml'), { recursive: true });
  fs.writeFileSync(path.join(android, 'res', 'xml', 'bpf_widget_info.xml'), `
<appwidget-provider xmlns:android="http://schemas.android.com/apk/res/android"
    android:minWidth="250dp"
    android:minHeight="110dp"
    android:targetCellWidth="4"
    android:targetCellHeight="2"
    android:updatePeriodMillis="0"
    android:initialLayout="@layout/bpf_date_widget"
    android:resizeMode="horizontal|vertical"
    android:widgetCategory="home_screen" />
`);
  fs.mkdirSync(path.join(android, 'res', 'layout'), { recursive: true });
  fs.writeFileSync(path.join(android, 'res', 'layout', 'bpf_date_widget.xml'), `
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:id="@+id/widRoot"
    android:layout_width="match_parent"
    android:layout_height="match_parent"
    android:orientation="vertical"
    android:gravity="center"
    android:padding="10dp"
    android:background="@drawable/bpf_widget_bg">

    <LinearLayout
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:orientation="horizontal"
        android:gravity="center_vertical">

        <TextView
            android:id="@+id/wiDay"
            android:layout_width="wrap_content"
            android:layout_height="wrap_content"
            android:minWidth="34dp"
            android:gravity="center"
            android:textStyle="bold"
            android:textSize="26sp"
            android:textColor="#22307a" />

        <LinearLayout
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:layout_marginStart="8dp"
            android:orientation="vertical">

            <TextView
                android:id="@+id/wiMonth"
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:textStyle="bold"
                android:textSize="12sp"
                android:textColor="#ed1c24" />

            <TextView
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:text="Agenda hari ini"
                android:textSize="9sp"
                android:textColor="#6b7280" />
        </LinearLayout>
    </LinearLayout>

    <TextView
        android:id="@+id/wiAgenda"
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:layout_marginTop="6dp"
        android:maxLines="3"
        android:ellipsize="end"
        android:lineSpacingExtra="2dp"
        android:textSize="12sp"
        android:textColor="#101014" />
</LinearLayout>
`);
  fs.mkdirSync(path.join(android, 'res', 'drawable'), { recursive: true });
  fs.writeFileSync(path.join(android, 'res', 'drawable', 'bpf_widget_bg.xml'), `
<shape xmlns:android="http://schemas.android.com/apk/res/android" android:shape="rectangle">
    <solid android:color="#ffffff" />
    <corners android:radius="10dp" />
    <stroke android:width="1dp" android:color="#ed1c24" />
</shape>
`);
  console.log('[datelive] res widget ditulis');

  /* ---------- 4) MainActivity: sinkron saat dibuka/di-resume ---------- */
  let mainJava = null;
  (function walk(dir) {
    for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, ent.name);
      if (ent.isDirectory()) walk(p);
      else if (ent.name === 'MainActivity.java') mainJava = p;
    }
  })(javaPkgs);
  if (mainJava) {
    let src = fs.readFileSync(mainJava, 'utf8');
    if (!src.includes('// BPF-DATELIVE')) {
      // sisipkan onResume refresh sebelum kurung penutup akhir class
      src = src.replace(/\}\s*$/, `
    // BPF-DATELIVE: sinkron ikon & widget tanggal tiap app dibuka / kembali aktif
    @Override
    protected void onResume() {
        super.onResume();
        try {
            bpf.datelive.DateLive.refresh(this);
        } catch (Exception e) {
            android.util.Log.e("BPFDateLive", "onResume refresh gagal", e);
        }
    }
}
`);
      fs.writeFileSync(mainJava, src);
      console.log('[datelive] onResume sinkron ditambahkan ke MainActivity');
    }
  }

  /* ---------- 5) manifest: izin + receiver + 31 alias + lepas LAUNCHER dari MainActivity ----------
     Strategi: baseline bersih dispanshot sekali (AndroidManifest.bpf-orig.xml);
     setiap prepare: baca baseline → sanitasi generik sekali lagi → sunting → tulis.
     Ini kebal terhadap manifest yang ditulis ulang gradle/attribute ordening. */

  // 5-0) siapkan baseline: dari kondisi sekarang, hapus PAPA umum (terlepas urutan atribut)
  const genericClean = (txt) => {
    // alias bpfDay (apa pun urutan atributnya)
    let out = txt;
    out = out.replace(/<activity-alias\b[\s\S]*?<\/activity-alias>\s*/g, (blk) =>
      (blk.includes('.bpfDay') ? '' : blk));
    // receiver bpf.datelive.* (apa pun urutan atributnya)
    out = out.replace(/<receiver\b[\s\S]*?<\/receiver>\s*/g, (blk) =>
      (blk.includes('bpf.datelive.') ? '' : blk));
    // komentar & permission duplikat
    out = out.replace(/<!-- BPF-DATELIVE[^>]*-->\s*/g, '');
    out = out.replace(/\s*<uses-permission android:name="android\.permission\.RECEIVE_BOOT_COMPLETED" \/>/g, '');
    // LAUNCHER filter di MainActivity bersihkan juga (kalau ada)
    out = out.replace(/(<activity[^>]*android:name="MainActivity"[^>]*>\s*[\s\S]*?<\/activity>)/, (blk) =>
      blk.replace(/<intent-filter[\s\S]*?<\/intent-filter>\s*/g, '')
         .replace(/\n\s*\n/g, '\n'));
    return out;
  };

  const origPath = path.join(android, 'AndroidManifest.bpf-orig.xml');
  if (!fs.existsSync(origPath)) {
    fs.writeFileSync(origPath, genericClean(manifest));
    console.log('[datelive] baseline manifest disimpan: ' + path.basename(origPath));
  }
  let clean = fs.readFileSync(origPath, 'utf8');
  // Baseline dibuat sekali; versi di dalamnya HARUS ikut config.xml terbaru,
  // kalau tidak APK hasil build tetap memakai versi lama (mis. 1.7.0).
  const curCode = (manifest.match(/android:versionCode="(\d+)"/) || [])[1];
  const curName = (manifest.match(/android:versionName="([^"]+)"/) || [])[1];
  if (curCode) clean = clean.replace(/android:versionCode="\d+"/, `android:versionCode="${curCode}"`);
  if (curName) clean = clean.replace(/android:versionName="[^"]*"/, `android:versionName="${curName}"`);
  clean = genericClean(clean); // ballast ketahanan

  // 5a) permission — baseline TIDAK ikut munge plugin, jadi izin plugin dipak ulang di sini
  const ensurePerm = (txt, perm) => (txt.includes(perm)
    ? txt
    : txt.replace(/(\s*)<\/manifest>/, `$1    <uses-permission android:name="${perm}" />
</manifest>`));
  clean = ensurePerm(clean, 'android.permission.RECEIVE_BOOT_COMPLETED');
  clean = ensurePerm(clean, 'android.permission.POST_NOTIFICATIONS'); // bpfBridge
  clean = ensurePerm(clean, 'android.permission.REQUEST_INSTALL_PACKAGES'); // updater APK

  // 5b) pasangan tunggal: alias harian + receiver
  let aliases = '';
  for (let d = 1; d <= 31; d++) {
    aliases += `
    <activity-alias android:enabled="${d === 1}" android:exported="true"
        android:icon="@mipmap/bpfday${d}" android:label="@string/app_name"
        android:name=".bpfDay${d}" android:targetActivity="MainActivity">
        <intent-filter android:label="@string/launcher_name">
            <action android:name="android.intent.action.MAIN" />
            <category android:name="android.intent.category.LAUNCHER" />
        </intent-filter>
    </activity-alias>`;
  }
  const block = `
    <!-- BPF-DATELIVE-ALIASES -->
${aliases}
    <!-- BPF-DATELIVE-RECEIVERS -->
    <receiver android:name="bpf.datelive.DateReceiver" android:exported="false">
        <intent-filter>
            <action android:name="bpf.datelive.MIDNIGHT" />
            <action android:name="android.intent.action.DATE_CHANGED" />
            <action android:name="android.intent.action.TIME_SET" />
            <action android:name="android.intent.action.TIMEZONE_CHANGED" />
        </intent-filter>
    </receiver>
    <receiver android:name="bpf.datelive.DateWidgetProvider" android:exported="false">
        <intent-filter>
            <action android:name="android.appwidget.action.APPWIDGET_UPDATE" />
        </intent-filter>
        <meta-data android:name="android.appwidget.provider" android:resource="@xml/bpf_widget_info" />
    </receiver>
`;
  const actNew = clean.match(/<activity[^>]*android:name="MainActivity"[\s\S]*?<\/activity>/);
  let idx = clean.indexOf('</activity>');
  if (actNew) idx = actNew.index + actNew[0].length;
  clean = clean.slice(0, idx) + block + clean.slice(idx);

  fs.writeFileSync(manifestPath, clean);
  console.log('[datelive] manifest di-patch (alias harian + receiver)');
};
