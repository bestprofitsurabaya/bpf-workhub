# 🗄️ Arsip Resolusi Lamara (Sep–Okt 2026)

Empat dokumen insiden-pojok yang solusinya sudah terpasang di produksi
dan tidak lagi dipakai — diarsipkan utk memangkas overhead pencarian.

| Dokumen | Isi | Status |
|---|---|---|
| `WORKER_MIGRATION_PLAN.md` | Migrasi worker gunicorn eventlet→gevent | ✅ SELESAI v2.38.0/v2.39.3 — referensi arsitektur |
| `OT_WEBAPP_REDEPLOY.md` | Redeploy Apps Script Overtime (ISO UTC vs wall-clock) | ✅ TERVERIFIKASI (feed v3 marker OK) |
| `SHEET_DATE_TYPO_FIX.md` | Paket koreksi 18 typo tanggal di Google Sheets overtime | ✅ DB beres; koreksi sheet Driver menunggu akses owner |
| `OXALPHA_COMMUNICATION.md` | Cara mengakses LLM Ox Alpha via OpenRouter API | Referensi — dipakai kalau perlu asisten IT |

Jangan edit; hanya dibaca kalau ada insiden serupa. Lihat juga CHANGELOG
v2.45.0–v2.40.3 utk konteks.
