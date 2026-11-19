# Ikon & logo aplikasi

Logo resmi BestProfit sudah diunduh dari situs resmi (180x180, transparan).
Satu sumber logo dipakai di semua titik:
- Ikon aplikasi Android & iOS dibuat dari file ini (res/icon/android/*.png, ios/logo-180.png)
- Tampilan header aplikasi & admin diambil dari server /assets/logo.png (file sama)
- deploy-server.sh menyalin assets/logo.png + favicon.ico ke ~/bpf-workhub/data/assets/ di NAS

Untuk finalisasi rilis (ubah agar lebih berkilau bila perlu):
- Android: set telah lengkap 48/72/96/144/192 (dibuat dari logo)
- iOS: 1024 App Store tanpa alpha + set iOS lengkap; daftarkan di <platform name="ios">

Sumber logo: https://www.bestprofit-futures.co.id/
