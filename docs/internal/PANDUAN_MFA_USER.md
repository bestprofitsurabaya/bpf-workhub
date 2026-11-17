# 📱 Panduan Verifikasi Dua Langkah (MFA) — BPF WorkHub

**Untuk semua pengguna** · Berlaku sejak v2.112.0 · 17 November 2026

Panduan ini bisa dicetak atau dibagikan apa adanya ke karyawan.

---

## Apa itu MFA?

Mulai v2.112.0, login BPF WorkHub memakai **dua langkah**:

1. **PIN 6 digit** (seperti biasa), lalu
2. **Kode 6 digit** dari aplikasi *authenticator* di ponsel.

Kode kedua berganti setiap **30 detik**, jadi mencuri PIN saja tidak cukup
untuk masuk.

**Siapa yang wajib?** Semua peran **kecuali marketing, ob, dan driver**.
Admin dapat mengubah daftar ini kapan saja.

---

## Bagian 1 — Sekali saja: pendaftaran (± 2 menit)

### Yang perlu disiapkan
- Ponsel Android atau iPhone.
- Aplikasi **Microsoft Authenticator** (gratis). Alternatif: Google
  Authenticator, Authy, 1Password, Bitwarden.

### Langkah

1. **Pasang aplikasi**
   - Android: buka **Play Store** → cari **Microsoft Authenticator** → Instal.
   - iPhone: buka **App Store** → cari **Microsoft Authenticator** → Unduh.

2. **Login ke BPF WorkHub**
   Buka aplikasi WorkHub → isi **Username** + **PIN** → klik **🔐 Masuk**.

3. **Layar Verifikasi Dua Langkah muncul**
   Bila peranmu wajib MFA dan belum pernah mendaftar, layar menampilkan
   **QR code** dan **kunci manual**.

4. **Buka Microsoft Authenticator**
   Ketuk tanda **+** di kanan atas → pilih **Akun lain**
   (*Other account*).

5. **Pindai QR**
   Arahkan kamera ponsel ke QR di layar WorkHub.
   - Kamera tidak bisa? Pilih **Masukkan kode secara manual**, lalu ketik
     **kunci manual** yang ada di bawah QR (huruf besar, tanpa spasi).
   - Jenis akun yang dipilih: **Akun lain (Google, Facebook, dll.)**.

6. **Masukkan kode pertama**
   Aplikasi menampilkan **kode 6 digit** untuk akun **BPF WorkHub**.
   Ketik kode itu di layar WorkHub → klik **Aktifkan MFA**.

7. **SIMPAN KODE PEMULIHAN** ⚠️
   Muncul **10 kode** berbentuk `XXXXX-XXXXX`. Kode ini **hanya ditampilkan
   sekali**.
   - Klik **📋 Salin semua** atau **⬇️ Unduh .txt**.
   - Simpan di tempat aman **yang bukan ponsel yang sama** (mis. komputer
     kantor, password manager, atau cetak dan simpan di dompet).
   - Setiap kode hanya bisa dipakai **satu kali**.

8. Klik **Masuk ke aplikasi**. Selesai — pendaftaran tidak perlu diulang.

---

## Bagian 2 — Login sehari-hari

1. Buka BPF WorkHub → isi **Username** + **PIN** → **🔐 Masuk**.
2. Buka **Microsoft Authenticator** → lihat kode 6 digit untuk **BPF WorkHub**.
3. Ketik kode → **Verifikasi & Masuk**.

> 💡 Bila muncul "kode salah", tunggu kode berganti (30 detik) lalu masukkan
> kode terbaru. Jangan memakai kode yang sudah dipakai sebelumnya.

---

## Bagian 3 — Kalau ada masalah

### Ponsel hilang, rusak, atau aplikasi ter-reset

**Punya kode pemulihan?**
1. Di layar verifikasi, klik **"Ponsel hilang? Gunakan kode pemulihan"**.
2. Ketik salah satu kode `XXXXX-XXXXX` → **Gunakan kode pemulihan**.
3. Setelah masuk, buka **Profil Saya** → **Kode pemulihan baru** untuk membuat
   10 kode pengganti.

**Tidak punya kode pemulihan?**
Hubungi **Admin**. Admin akan melakukan **Reset MFA** untuk akunmu.
- Reset memerlukan PIN ulang Admin (step-up) dan tercatat di Audit Log.
- Setelah direset, kamu mendaftar ulang (Bagian 1) saat login berikutnya.

### Kode selalu ditolak

1. **Setel jam ponsel otomatis** — Setelan → Tanggal & waktu → *Setel otomatis*.
   Selisih jam lebih dari 30 detik membuat kode dianggap salah.
2. Pastikan memilih akun **BPF WorkHub**, bukan akun lain di aplikasi.
3. Tunggu kode berganti, lalu coba kode terbaru.
4. Masih gagal? Gunakan kode pemulihan atau minta Admin reset.

### Ingin mematikan MFA

Buka **Profil Saya** → kartu **Verifikasi Dua Langkah (MFA)** →
**Matikan MFA** → masukkan kode 6 digit.

Tombol ini **nonaktif** bila peranmu diwajibkan MFA oleh Admin. Dalam kondisi
itu, MFA hanya bisa dimatikan lewat perubahan kebijakan Admin.

---

## Bagian 4 — Keamanan

- 🔒 **Jangan bagikan kode 6 digit atau kode pemulihan** kepada siapa pun —
  termasuk staf IT, Admin, atau atasan. Petugas resmi tidak pernah memintanya.
- 🔒 Jangan menyimpan kode pemulihan di aplikasi catatan yang sama dengan
  authenticator.
- 🔒 Laporkan segera ke Admin bila ponsel hilang atau ada login yang tidak
  kamu kenali.
- 🔒 PIN tetap rahasia. MFA menambah lapisan, bukan mengganti PIN.

---

## Pertanyaan yang sering ditanya

**Apakah harus online?**
Hanya saat login. Aplikasi authenticator menghitung kode secara offline, jadi
tetap bisa dipakai tanpa sinyal.

**Boleh pakai Google Authenticator?**
Boleh. Semua aplikasi TOTP standar (Google Authenticator, Authy, 1Password,
Bitwarden, FreeOTP) kompatibel.

**Kenapa Microsoft Authenticator tidak menampilkan "push notification"?**
Fitur push/number-matching hanya untuk akun Microsoft 365 (Entra ID). Untuk
BPF WorkHub, aplikasi dipakai sebagai **TOTP** — pilih menu **Akun lain**,
bukan "Akun Microsoft".

**Bisa dipakai di dua ponsel?**
Bisa, dengan memindai QR yang sama saat pendaftaran (atau menambah akun di
ponsel kedua). Namun kode pemulihan tetap wajib disimpan.

**Apakah kode pemulihan bisa dipakai berulang?**
Tidak. Setiap kode sekali pakai. Setelah habis, buat kode baru di Profil Saya.

**Apakah MFA berlaku di aplikasi Driver?**
Tidak. Peran **driver, ob, marketing** dikecualikan dari kebijakan default.

---

## Untuk Admin

Ringkasan pengaturan ada di **Pengaturan → 🔐 MFA**:

| Kebijakan | Perilaku |
|---|---|
| Nonaktif | Kill switch — tidak ada yang diminta kode. |
| Opsional | User yang sudah mendaftar wajib verifikasi; user lain boleh mendaftar sendiri. |
| Wajib untuk role terpilih | Role yang dicentang wajib MFA. Default: semua kecuali marketing, ob, driver. |

- **Masa tenggang** (default 7 hari) mencegah lockout massal. Isi `0` untuk
  menegakkan segera.
- **Reset MFA** per user memerlukan step-up PIN dan tercatat di Audit Log.
- Pantau kolom **Status per user** sampai semua user target mendaftar sebelum
  menurunkan tenggang.

---

*Dokumen ini bagian dari rilis v2.112.0. Panduan lengkap aplikasi ada di
`guides/USER_GUIDE.md`.*
