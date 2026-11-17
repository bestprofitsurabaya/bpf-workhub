# Audit — MFA OTP & Pengaturan Fleksibel Admin

**Tanggal:** 17 November 2026
**Versi repo:** v2.111.0 (HEAD `2f9c748`)
**Pemicu:** "periksa pembaharuan terkini di NAS — apakah fitur MFA OTP sudah
lengkap, dan apakah admin bisa mengatur aktif/non-aktif MFA OTP secara fleksibel."

---

## Kesimpulan

**Fitur MFA OTP belum ada sama sekali** — bukan "belum lengkap", melainkan
tidak pernah dibuat. Tidak ada kode, kolom database, kunci konfigurasi,
endpoint, halaman pengaturan, maupun riwayat commit yang menyebut MFA/TOTP/2FA.

Karena fiturnya tidak ada, pertanyaan kedua (admin bisa mengaktifkan /
menonaktifkan) juga **belum bisa dijawab "ya"**: belum ada saklar apa pun
untuk diatur.

Satu-satunya "OTP" yang ada di sistem adalah **OTP login portal MyPertamina**
untuk agen SubsidiTepat (`agent/subsiditepat/`). Itu OTP milik portal pihak
ketiga, diketik Finance di dashboard BBM, dan **bukan** autentikasi pengguna
BPF WorkHub.

---

## Bukti pemeriksaan

| Pemeriksaan | Hasil |
|---|---|
| `grep -riE "\bmfa\b\|totp\|2fa\|two.factor"` pada `*.py`, `*.vue`, `*.js`, `*.sql`, `*.md` | 0 hasil nyata (hanya false positive hash di file backup) |
| `information_schema.COLUMNS` untuk `%mfa%`, `%otp%`, `%totp%`, `%2fa%` | 0 kolom |
| `system_config` untuk key MFA/OTP | 0 key |
| `git log --all --grep="MFA\|TOTP\|2FA"` | 0 commit |
| `git log --all -S "mfa_enabled"` | 0 commit |
| Branch `feat/it-agent-rollout`, `feat/it-inventory` | tidak ada MFA |
| `docs/`, `guides/` | hanya OTP SubsidiTepat |
| Endpoint login `POST /api/auth/login` | hanya `username` + `pin` |
| Frontend `frontend/src` | tidak ada halaman/komponen MFA |

---

## Yang SUDAH ada (faktor tunggal + pengerasan)

| Kontrol | Implementasi | Catatan |
|---|---|---|
| PIN pengguna | 6 digit, disimpan **scrypt** (57/57 user aktif) | Migrasi dari plaintext sudah tuntas (`modules/pin_security.py`) |
| Rate limit login | 5 gagal / 5 menit → lockout 15 menit, per IP+username | `helpers.py` (`_LOGIN_MAX_FAILS`) |
| Step-up PIN | Aksi berisiko (uang, verifikasi pengajuan) minta PIN ulang | `modules/stepup.py`, grant 600 dtk (env `STEPUP_TTL_SECONDS`), rate limit 8/5 menit |
| Sesi | Cookie `bpf_session`, `SameSite=Lax`, `Secure` (env), umur 12 jam (env `SESSION_HOURS`) | `session.clear()` saat login (anti session fixation) |
| CSRF | Token per sesi + header `X-CSRF-Token`, perbandingan constant-time | `app.py` |
| Audit | `activity_logs` (login, step-up, aksi sensitif) | PII disamarkan pada modul tertentu |

Artinya: keamanan saat ini bertumpu pada **satu faktor** (PIN 6 digit) yang
diperkuat rate-limit, lockout, dan step-up untuk aksi berisiko. Belum ada
faktor kedua.

---

## Kesiapan prasyarat bila MFA ingin dibangun

| Prasyarat | Status | Dampak |
|---|---|---|
| Kolom kontak user (`email` / `no_hp`) | **Tidak ada** — tabel `users` hanya punya `username, full_name, role, pin, ...` | Email/SMS OTP mustahil tanpa migrasi + pengumpulan data |
| Pengirim email (SMTP/SendGrid/Mailgun) | **Tidak ada** di backend | Email OTP butuh integrasi baru |
| WhatsApp/SMS gateway | Tidak ada (Telegram hanya di modul `news_scraper`) | SMS OTP butuh vendor baru |
| Library TOTP | Tidak ada `pyotp`; **`segno`** sudah ada untuk QR | TOTP tetap bisa tanpa dependensi baru (stdlib `hmac`/`hashlib`) |
| Enkripsi secret | Tidak ada `cryptography` | Perlu ditambahkan untuk menyimpan secret MFA dengan aman |
| Session store sisi server | Tidak ada (Flask signed cookie) | "Logout semua perangkat" / cabut sesi belum mungkin |

**Kesimpulan prasyarat:** **TOTP (authenticator app) adalah jalur paling murah**
karena tidak butuh email/SMS, tidak butuh data kontak, dan QR sudah bisa dibuat
dengan `segno` yang sudah terpasang.

---

## Rekomendasi desain (bila dilanjutkan)

### Skema data
```sql
ALTER TABLE users
  ADD COLUMN mfa_enabled TINYINT(1) NOT NULL DEFAULT 0,
  ADD COLUMN mfa_secret VARBINARY(255) NULL,        -- terenkripsi (Fernet)
  ADD COLUMN mfa_enrolled_at DATETIME NULL,
  ADD COLUMN mfa_last_step BIGINT NULL;             -- anti replay

CREATE TABLE mfa_recovery_codes (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  code_hash CHAR(64) NOT NULL,                      -- sha256
  used_at DATETIME NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX (user_id)
);
```

### Konfigurasi global (fleksibel untuk admin)
Di `system_config`:
- `mfa_policy` = `off` | `optional` | `required_roles`
- `mfa_required_roles` = mis. `admin,finance`
- `mfa_grace_days` = masa tenggang sebelum penegakan (default 7)

Dengan ini admin pusat bisa:
1. **Mematikan total** (`off`) — perilaku hari ini.
2. **Opsional** (`optional`) — user boleh mendaftarkan sendiri.
3. **Wajib untuk role tertentu** (`required_roles`) — mis. semua `admin` dan
   `finance` wajib; role lain opsional.

### Alur login dua langkah
1. `POST /api/auth/login` (PIN) → bila MFA aktif/required: sesi **belum** diberi
   `user_role`, hanya `mfa_pending_user` + `mfa_pending_until` (5 menit).
2. `POST /api/auth/mfa/verify` (6 digit, window ±1 langkah, `mfa_last_step`
   mencegah replay) → baru set sesi penuh + `session.clear()` sebelum set.
3. Gagal verifikasi: rate limit 5/5 menit → lockout 15 menit, audit.
4. Bila `required` dan user belum enroll → paksa halaman enrollment
   (kecuali akun darurat yang diizinkan env `MFA_BYPASS_USERS`).

### Halaman Pengaturan → Keamanan (admin)
- Saklar kebijakan MFA (off/optional/required_roles) + pilih role.
- Daftar user: status enrollment (Aktif / Belum / Reset).
- Tombol **Reset MFA** per user (wajib step-up PIN + audit).
- Tombol **Nonaktifkan MFA** per user (wajib step-up + audit).
- Info masa tenggang dan tanggal penegakan.

### Pengaman wajib
- Secret **jangan** plaintext — enkripsi dengan kunci env `MFA_ENC_KEY`.
- Recovery code sekali pakai (hash), ditampilkan sekali saat enrollment.
- Jangan aktifkan `required_roles` sebelum semua admin target enroll
  (cegah lockout massal).
- Audit setiap perubahan kebijakan, enrollment, reset, dan verifikasi gagal.
- Jangan mencampur OTP SubsidiTepat dengan MFA login WorkHub.

### Perkiraan usaha
| Bagian | Perkiraan |
|---|---|
| Backend (skema, TOTP, endpoint login 2 langkah, kebijakan, audit) | 1,5–2 hari |
| Frontend (enrollment QR + verifikasi + halaman Keamanan admin) | 1 hari |
| Tes (unit + regresi login) & migrasi data | 0,5 hari |

---

## Temuan tambahan (di luar MFA)

| # | Temuan | Dampak |
|---|---|---|
| B-01 | `docs/internal/PROGRESS.md` masih menyebut v2.108.2 padahal repo sudah v2.111.0 | Handoff antar-sesi bisa menyesatkan |
| B-02 | Tidak ada server-side session store → sesi tidak bisa dicabut paksa | Bila cookie dicuri, berlaku sampai 12 jam |
| B-03 | Tidak ada kolom email/HP di `users` | Semua notifikasi keamanan (mis. "login baru") belum mungkin |
| B-04 | PIN 6 digit = satu-satunya faktor login | Risiko brute-force bergantung penuh pada rate limit |

---

## Status

**Belum diimplementasikan.** Dokumen ini murni audit — tidak ada perubahan
kode pada v2.111.0. Bila disetujui, implementasi disarankan memakai TOTP
dengan kebijakan `off / optional / required_roles` seperti di atas.
