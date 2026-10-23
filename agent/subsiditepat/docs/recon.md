# 🔬 Recon — Subsidi Tepat MyPertamina (22 Okt 2026)

Hasil bedah bundle Next.js dua portal. Semua endpoint di bawah = yang dipakai
web resmi oleh browser user (bukan API tidak resmi).

## Dasar

| Item | Nilai |
|---|---|
| Base API (personal + korporat) | `https://apimpv.my-pertamina.id` |
| Portal personal (NIK) | `https://subsiditepat.mypertamina.id` |
| Portal perusahaan | `https://perusahaan.subsiditepat.my-pertamina.id` |
| Sitekey reCAPTCHA v3 (publik) | `6LdZZUorAAAAAO5HSdGXI9rc_Sa_tnyuiV_RSfYZ` |

## Header penting

- `Authorization: Bearer <token>` — token bearer dari cookie **`__mpv-token`**
  (korporat: `__myptm-corporate-token`)
- `X-LOGIN-SESSION` — dari cookie **`__mpv-login-session`** / body login
- `X-RECAPTCHA-TOKEN` — token reCAPTCHA v3 (dibuat kode halaman di browser asli)

## Peta endpoint PERSONAL (NIK + password)

- `POST mpv-personal/v4/users/auth/login` — login (kirim NIK/email + password
  + X-RECAPTCHA-TOKEN). Respons menyusun Login-Session baru.
- `POST mpv-personal/v4/users/auth/login/send-otp` — kirim OTP (metode pegangan
  di halaman `otp/method`)
- `POST mpv-personal/v4/users/auth/otp-verification` — verifikasi OTP → Bearer
- `POST mpv-personal/v2/users/auth/otp-resend` — kirim ulang (cooldown 3 menit)
- `GET mpv-personal/v1/transaction/bbm` — **riwayat transaksi BBM** (target)
- `GET mpv-personal/v2/users/verified-detail/identification` — QR kendaraan riwayat verifikasi
- v3/v2 profil dsb di bundle (`mpv-personal/*`)

## Peta endpoint KORPORAT (perusahaan)

- `POST mpv-corporate/v2/corporates/auth/login` (+v1)
- `POST mpv-corporate/v2/corporates/auth/login/send-otp`
- `POST mpv-corporate/v2/corporates/auth/otp-verification`
- `GET mpv-corporate/v1/transaction/bbm` — riwayat transaksi BBM korporat
- `GET mpv-corporate/v1/vehicle-registration/history` — riwayat registrasi unit
- `GET mpv-corporate/v1/vehicles`, `.../qr-code`, `.../profile`

## Catatan flow (serendipity atau penting)

1. Halaman login `subsiditepat.../login`; ketik NIK (16 digit) + password →
   form `POST /api/gateway/auth/login` (proxy Next.js di sisi domain web).
2. Bila OTP email diperlukan → redirect `/otp/method`.
3. Setelah verifikasi OTP, cookie `__mpv-token` (Bearer) terpasang dan semua
   panggilan selanjutnya via `apimpv` memakai Bearer itu.

## Encode kredbasic (dari bundle korporat, informasi saja)

`bXlwZXJ0YW1pbmEtbXB2OkFFQjk2MjgyLTE3NTMtNEVCRi05OEJFLUFFMzEyQzVGM0FCMw==`
→ `mypertamina-mpv:AEB96282-1753-4EBF-98BE-AE312C5F3AB3` (app key embedding di
JS publik — bukan rahasia, hanya basic-auth internal web).
