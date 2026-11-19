# Plugin Cordova

Plugin dipasang otomatis oleh `npm install` di `apk/mobile`:

| Plugin | Asal | Fungsi |
|---|---|---|
| `bpfBridge` | `../bpfBridge-src` (lokal) | notifikasi lokal, widget home screen, unduh/bagikan media |
| `cordova-plugin-screen-orientation` | npm | kunci orientasi landscape |

Widget Android (tanggal + agenda) dan ikon launcher tanggal-hidup dibuat oleh
hook `mobile/hooks/dynamic-date.js` saat `cordova prepare`, lalu dibangun oleh
`scripts/build-android.sh`. Folder `plugins/*` hasil instalasi tidak di-commit
(hanya file JSON status + README ini).

Logo aplikasi diambil dari bridge WorkHub: `/assets/logo.png`.
