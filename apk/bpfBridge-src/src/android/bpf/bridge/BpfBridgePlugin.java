package bpf.bridge;

import android.app.Activity;
import android.app.DownloadManager;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;

import androidx.core.content.FileProvider;

import org.apache.cordova.CallbackContext;
import org.apache.cordova.CordovaArgs;
import org.apache.cordova.CordovaInterface;
import org.apache.cordova.CordovaPlugin;
import org.apache.cordova.CordovaWebView;
import org.apache.cordova.PluginResult;
import org.json.JSONException;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.lang.reflect.Method;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.MessageDigest;

/**
 * Bridge native BPF Agenda (plugin cordova).
 * Aksi via cordova.exec(service = "bpfBridge"):
 *  - notify            -> bpf.datelive.DateLive.notifyNew(ctx, title, msg)
 *  - notify-permission -> minta izin POST_NOTIFICATIONS (Android 13+)
 *  - addWidget         -> bpf.datelive.DateLive.addWidget(ctx)  (pin widget)
 *  - refreshWidget     -> bpf.datelive.DateLive.refresh(ctx) / updateWidget(ctx)
 *  - widgetAgenda      -> simpan teks agenda hari ini untuk widget
 *  - download          -> unduh media ke folder Download (DownloadManager)
 *  - share             -> unduh media ke cache lalu bagikan via share sheet
 *  - appInfo           -> versi aplikasi terpasang (versionName/versionCode)
 *  - canInstall        -> apakah izin "pasang aplikasi tak dikenal" sudah aktif
 *  - openInstallSettings -> buka layar izin pemasangan aplikasi
 *  - installApk        -> unduh APK, verifikasi SHA-256, buka installer
 */
public class BpfBridgePlugin extends CordovaPlugin {

    private static final String PERM_POST_NOTIFICATIONS = "android.permission.POST_NOTIFICATIONS";
    private static final int REQ_NOTIFY_PERM = 4242;
    private static final String PROVIDER_SUFFIX = ".bpfmedia";

    private Context appCtx;
    private CallbackContext notifyPermCb;

    @Override
    public void initialize(CordovaInterface cordova, CordovaWebView webView) {
        super.initialize(cordova, webView);
        Activity act = cordova.getActivity();
        this.appCtx = act != null ? act.getApplicationContext() : null;
    }

    @Override
    public boolean execute(String action, CordovaArgs args, final CallbackContext cb) throws JSONException {
        final Context c = this.appCtx;
        if (c == null) {
            cb.error("BpfBridge: context belum siap");
            return true;
        }

        if ("notify".equals(action)) {
            String title = args.getString(0);
            String msg = args.getString(1);
            invokeDateLive(c, "notifyNew", c, title, msg);
            cb.success();
            return true;
        }

        if ("notify-permission".equals(action)) {
            notifyPermCb = cb;
            boolean atLeast13 = Build.VERSION.SDK_INT >= 33;
            if (atLeast13 && !this.cordova.hasPermission(PERM_POST_NOTIFICATIONS)) {
                PluginResult keep = new PluginResult(PluginResult.Status.NO_RESULT, true);
                keep.setKeepCallback(true);
                cb.sendPluginResult(keep);
                this.cordova.requestPermission(this, REQ_NOTIFY_PERM, PERM_POST_NOTIFICATIONS);
                return true;
            }
            cb.success("granted");
            return true;
        }

        if ("addWidget".equals(action)) {
            boolean ok = invokeDateLive(c, "addWidget", c);
            toast(ok ? "Widget BPF Agenda dikirim ke home screen"
                     : "Launcher ini tidak mendukung pin widget otomatis");
            cb.success(ok ? "ok" : "tidak didukung launcher");
            return true;
        }

        if ("refreshWidget".equals(action)) {
            boolean ok = invokeDateLive(c, "refresh", c);
            if (!ok) ok = invokeDateLive(c, "updateWidget", c);
            cb.success(String.valueOf(ok));
            return true;
        }

        if ("widgetAgenda".equals(action)) {
            String date = args.getString(0);
            String text = args.getString(1);
            boolean ok = invokeDateLive(c, "setAgenda", c, date, text);
            cb.success(String.valueOf(ok));
            return true;
        }

        if ("download".equals(action)) {
            String url = args.getString(0);
            String name = safeName(args.optString(1));
            boolean ok = enqueueDownload(c, url, name);
            toast(ok ? "Mengunduh " + name + " ke folder Download" : "Unduhan gagal dimulai");
            cb.success(ok ? "ok" : "gagal");
            return true;
        }

        if ("share".equals(action)) {
            String url = args.getString(0);
            String name = safeName(args.optString(1));
            String mimeArg = args.optString(2);
            String mime = (mimeArg == null || mimeArg.trim().isEmpty()) ? mimeOf(name) : mimeArg.trim();
            shareMedia(c, url, name, mime);
            cb.success("ok");
            return true;
        }

        if ("appInfo".equals(action)) {
            try {
                android.content.pm.PackageInfo pi =
                    c.getPackageManager().getPackageInfo(c.getPackageName(), 0);
                org.json.JSONObject out = new org.json.JSONObject();
                out.put("packageName", c.getPackageName());
                out.put("versionName", pi.versionName == null ? "" : pi.versionName);
                out.put("versionCode",
                    Build.VERSION.SDK_INT >= 28 ? pi.getLongVersionCode() : pi.versionCode);
                cb.success(out);
            } catch (Exception e) {
                cb.error("appInfo: " + e.getMessage());
            }
            return true;
        }

        if ("canInstall".equals(action)) {
            cb.success(String.valueOf(canInstall(c)));
            return true;
        }

        if ("openInstallSettings".equals(action)) {
            openInstallSettings(c);
            cb.success("ok");
            return true;
        }

        if ("installApk".equals(action)) {
            String url = args.getString(0);
            String sha = args.optString(1);
            String name = args.optString(2);
            installApk(c, url, sha, name, cb);
            return true;
        }

        cb.error("aksi tidak dikenal: " + action);
        return true;
    }

    @Override
    public void onRequestPermissionResult(int requestCode, String[] permissions, int[] grantResults) throws JSONException {
        if (requestCode == REQ_NOTIFY_PERM && notifyPermCb != null) {
            boolean granted = grantResults != null && grantResults.length > 0
                && grantResults[0] == PackageManager.PERMISSION_GRANTED;
            notifyPermCb.success(granted ? "granted" : "denied");
            notifyPermCb = null;
        }
    }

    /* ---------------- unduh ke folder Download ---------------- */

    private boolean enqueueDownload(Context c, String url, String name) {
        try {
            DownloadManager.Request req = new DownloadManager.Request(Uri.parse(url));
            req.setTitle(name);
            req.setDescription("BPF Agenda");
            req.setMimeType(mimeOf(name));
            req.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
            req.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, name);
            DownloadManager dm = (DownloadManager) c.getSystemService(Context.DOWNLOAD_SERVICE);
            if (dm == null) return false;
            dm.enqueue(req);
            return true;
        } catch (Exception e) {
            android.util.Log.w("BpfBridge", "download: " + e);
            return false;
        }
    }

    /* ---------------- bagikan media (unduh ke cache lalu share sheet) ---------------- */

    private void shareMedia(final Context c, final String url, final String name, final String mime) {
        toast("Menyiapkan media untuk dibagikan…");
        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    File dir = new File(c.getCacheDir(), "share");
                    if (!dir.exists() && !dir.mkdirs()) throw new java.io.IOException("cache");
                    File out = new File(dir, name);
                    fetchToFile(url, out);

                    Uri uri = FileProvider.getUriForFile(c, c.getPackageName() + PROVIDER_SUFFIX, out);
                    Intent send = new Intent(Intent.ACTION_SEND);
                    send.setType(mime);
                    send.putExtra(Intent.EXTRA_STREAM, uri);
                    send.putExtra(Intent.EXTRA_SUBJECT, name);
                    send.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                    Intent chooser = Intent.createChooser(send, "Bagikan media");
                    chooser.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                    chooser.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                    c.startActivity(chooser);
                } catch (Exception e) {
                    android.util.Log.w("BpfBridge", "share: " + e);
                    toast("Gagal menyiapkan media untuk dibagikan");
                }
            }
        }, "bpf-share").start();
    }

    private void fetchToFile(String spec, File out) throws Exception {
        HttpURLConnection conn = null;
        InputStream in = null;
        FileOutputStream fos = null;
        try {
            URL u = new URL(spec);
            conn = (HttpURLConnection) u.openConnection();
            conn.setConnectTimeout(20000);
            conn.setReadTimeout(30000);
            conn.setInstanceFollowRedirects(true);
            conn.connect();
            int code = conn.getResponseCode();
            if (code < 200 || code >= 300) throw new java.io.IOException("http " + code);
            in = conn.getInputStream();
            fos = new FileOutputStream(out);
            byte[] buf = new byte[8192];
            int n;
            while ((n = in.read(buf)) > 0) fos.write(buf, 0, n);
        } finally {
            try { if (fos != null) fos.close(); } catch (Exception ignored) { }
            try { if (in != null) in.close(); } catch (Exception ignored) { }
            if (conn != null) conn.disconnect();
        }
    }

    /* ---------------- updater APK (v2.125.0) ---------------- */

    private boolean canInstall(Context c) {
        if (Build.VERSION.SDK_INT < 26) return true;
        try {
            return c.getPackageManager().canRequestPackageInstalls();
        } catch (Exception e) {
            return false;
        }
    }

    private void openInstallSettings(Context c) {
        try {
            Intent it = new Intent(android.provider.Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                Uri.parse("package:" + c.getPackageName()));
            it.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            c.startActivity(it);
            toast("Izinkan pemasangan aplikasi dari BPF Agenda, lalu tekan Perbarui lagi");
        } catch (Exception e) {
            toast("Buka Pengaturan → Aplikasi → BPF Agenda → Pasang aplikasi tak dikenal");
        }
    }

    private void sendProgress(CallbackContext cb, int percent) {
        try {
            org.json.JSONObject o = new org.json.JSONObject();
            o.put("stage", "download");
            o.put("percent", percent);
            PluginResult pr = new PluginResult(PluginResult.Status.OK, o);
            pr.setKeepCallback(true);
            cb.sendPluginResult(pr);
        } catch (Exception ignored) { }
    }

    private static String hex(byte[] data) {
        StringBuilder sb = new StringBuilder(data.length * 2);
        for (byte b : data) sb.append(String.format("%02x", b));
        return sb.toString();
    }

    /**
     * Unduh APK ke cache, verifikasi SHA-256, lalu buka installer sistem.
     * Callback pertama (keepCallback) berisi {"stage":"download","percent":N};
     * callback terakhir sukses "installer dibuka" atau error.
     */
    private void installApk(final Context c, final String url, final String expectedSha,
                            final String rawName, final CallbackContext cb) {
        String safe = safeName(rawName);
        if (!safe.toLowerCase(java.util.Locale.US).endsWith(".apk")) {
            safe = safe.replaceAll("\\.[A-Za-z0-9]+$", "") + ".apk";
        }
        final String name = safe;

        new Thread(new Runnable() {
            @Override
            public void run() {
                HttpURLConnection conn = null;
                InputStream in = null;
                FileOutputStream fos = null;
                File out = null;
                try {
                    File dir = new File(c.getCacheDir(), "apk");
                    if (!dir.exists() && !dir.mkdirs()) throw new java.io.IOException("cache");
                    out = new File(dir, name);

                    conn = (HttpURLConnection) new URL(url).openConnection();
                    conn.setConnectTimeout(20000);
                    conn.setReadTimeout(60000);
                    conn.setInstanceFollowRedirects(true);
                    conn.connect();
                    int code = conn.getResponseCode();
                    if (code < 200 || code >= 300) throw new java.io.IOException("http " + code);

                    long total = conn.getContentLength();
                    MessageDigest md = MessageDigest.getInstance("SHA-256");
                    in = conn.getInputStream();
                    fos = new FileOutputStream(out);
                    byte[] buf = new byte[16384];
                    long read = 0;
                    int last = -1;
                    int n;
                    while ((n = in.read(buf)) > 0) {
                        fos.write(buf, 0, n);
                        md.update(buf, 0, n);
                        read += n;
                        if (total > 0) {
                            int pct = (int) (read * 100 / total);
                            if (pct != last) {
                                last = pct;
                                sendProgress(cb, pct);
                            }
                        }
                    }
                    fos.close();
                    fos = null;
                    in.close();
                    in = null;

                    String got = hex(md.digest());
                    if (expectedSha != null && !expectedSha.trim().isEmpty()
                        && !got.equalsIgnoreCase(expectedSha.trim())) {
                        if (out.exists()) out.delete();
                        cb.error("unduhan rusak (SHA-256 tidak cocok)");
                        return;
                    }

                    final File apk = out;
                    BpfBridgePlugin.this.cordova.getActivity().runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            if (!canInstall(c)) {
                                openInstallSettings(c);
                                cb.error("izin");
                                return;
                            }
                            try {
                                Uri uri = FileProvider.getUriForFile(
                                    c, c.getPackageName() + PROVIDER_SUFFIX, apk);
                                Intent it = new Intent(Intent.ACTION_VIEW);
                                it.setDataAndType(uri, "application/vnd.android.package-archive");
                                it.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                                it.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                                c.startActivity(it);
                                cb.success("installer dibuka");
                            } catch (Exception e) {
                                cb.error("gagal membuka installer: " + e.getMessage());
                            }
                        }
                    });
                } catch (Exception e) {
                    android.util.Log.w("BpfBridge", "installApk: " + e);
                    cb.error("gagal unduh APK: " + e.getMessage());
                } finally {
                    try { if (fos != null) fos.close(); } catch (Exception ignored) { }
                    try { if (in != null) in.close(); } catch (Exception ignored) { }
                    if (conn != null) conn.disconnect();
                }
            }
        }, "bpf-apk").start();
    }

    /* ---------------- util ---------------- */

    private static String safeName(String raw) {
        String s = raw == null ? "" : raw.trim();
        s = s.replaceAll("[?#].*$", "");
        int slash = s.lastIndexOf('/');
        if (slash >= 0) s = s.substring(slash + 1);
        s = s.replaceAll("[^A-Za-z0-9._-]", "-");
        while (s.startsWith("-") || s.startsWith(".")) s = s.substring(1);
        if (s.isEmpty()) s = "bpf-media-" + System.currentTimeMillis();
        if (s.length() > 80) s = s.substring(s.length() - 80);
        if (!s.contains(".")) s = s + ".bin";
        return s;
    }

    private static String mimeOf(String name) {
        String n = name.toLowerCase(java.util.Locale.US);
        if (n.endsWith(".jpg") || n.endsWith(".jpeg")) return "image/jpeg";
        if (n.endsWith(".png")) return "image/png";
        if (n.endsWith(".webp")) return "image/webp";
        if (n.endsWith(".gif")) return "image/gif";
        if (n.endsWith(".mp4")) return "video/mp4";
        if (n.endsWith(".webm")) return "video/webm";
        if (n.endsWith(".pdf")) return "application/pdf";
        return "application/octet-stream";
    }

    private void toast(final String msg) {
        final Activity act = this.cordova.getActivity();
        if (act == null) return;
        act.runOnUiThread(new Runnable() {
            @Override
            public void run() {
                try {
                    android.widget.Toast.makeText(act, msg, android.widget.Toast.LENGTH_SHORT).show();
                } catch (Exception ignored) { }
            }
        });
    }

    /** Panggil statik method di bpf.datelive.DateLive via reflection. */
    private boolean invokeDateLive(Context ctx, String method, Object... params) {
        try {
            Class<?> cl = Class.forName("bpf.datelive.DateLive");
            Class<?>[] sig = new Class<?>[params.length];
            Object[] real = new Object[params.length];
            for (int i = 0; i < params.length; i++) {
                if (params[i] instanceof Context) {
                    sig[i] = Context.class;
                    real[i] = ctx;
                } else {
                    sig[i] = String.class;
                    real[i] = params[i];
                }
            }
            Method m = cl.getMethod(method, sig);
            Object out = m.invoke(null, real);
            if (out instanceof Boolean) return (Boolean) out;
            return true;
        } catch (Exception e) {
            android.util.Log.w("BpfBridge", method + ": " + e);
            return false;
        }
    }
}
