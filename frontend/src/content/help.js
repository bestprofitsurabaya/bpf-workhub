export const GLOSSARY = [
  {
    term: 'GA', full: 'General Affairs', category: 'Peran',
    desc: 'Tim yang memverifikasi klaim BBM, penugasan driver, aset, dan kebutuhan operasional cabang.',
  },
  {
    term: 'Finance', full: 'Keuangan', category: 'Peran',
    desc: 'Tim yang mencairkan klaim yang sudah terverifikasi GA, mengelola kasbon/LPJ, dan menyusun rekap.',
  },
  {
    term: 'HO', full: 'Head Office', category: 'Peran',
    desc: 'Kantor pusat. Admin HO dapat melihat dan mengelola semua cabang; admin cabang hanya cabangnya sendiri.',
  },
  {
    term: 'Klaim BBM', full: 'Klaim bahan bakar', category: 'Alur klaim',
    desc: 'Pengajuan penggantian biaya BBM oleh driver. Alurnya: driver mengajukan → GA verifikasi → Finance cairkan → arsip.',
  },
  {
    term: 'Kasbon', full: 'Pinjaman operasional', category: 'Alur klaim',
    desc: 'Dana yang diajukan lebih dulu untuk kebutuhan perjalanan. Setelah dipakai, driver wajib menyerahkan LPJ.',
  },
  {
    term: 'LPJ', full: 'Laporan Pertanggungjawaban', category: 'Alur klaim',
    desc: 'Bukti pemakaian kasbon (nota, foto, nominal). Kasbon tidak dianggap selesai sebelum LPJ disetujui.',
  },
  {
    term: 'ODO', full: 'Odometer', category: 'Data & istilah',
    desc: 'Angka jarak tempuh kendaraan. Dipakai untuk mengecek wajar-tidaknya konsumsi BBM.',
  },
  {
    term: 'MyPertamina', full: 'Aplikasi Pertamina', category: 'Data & istilah',
    desc: 'Bukti transaksi BBM subsidi. Fotonya bisa diminta saat verifikasi klaim tertentu.',
  },
  {
    term: 'Anomali ML', full: 'Deteksi anomali', category: 'Data & istilah',
    desc: 'Klaim yang ditandai sistem karena polanya tidak wajar. Wajib diverifikasi manual lewat tombol 🛡 Verifikasi.',
  },
  {
    term: 'Terverifikasi GA', full: 'verified_ga', category: 'Status',
    desc: 'Klaim sudah lolos verifikasi GA dan menunggu pencairan oleh Finance.',
  },
  {
    term: 'Menunggu Finance', full: 'os_finance', category: 'Status',
    desc: 'Status setelah dana dicairkan; transaksi menunggu konfirmasi driver lalu diarsipkan.',
  },
  {
    term: 'Terarsip', full: 'archived', category: 'Status',
    desc: 'Transaksi sudah selesai dan disimpan sebagai arsip. Tidak bisa diubah lagi.',
  },
  {
    term: 'ACC Atasan', full: 'Persetujuan berjenjang', category: 'Alur klaim',
    desc: 'Persetujuan tambahan sebelum GA/Finance memproses, misalnya Chief Driver untuk kasbon/BBM.',
  },
  {
    term: 'Step-up PIN', full: 'Verifikasi PIN ulang', category: 'Keamanan',
    desc: 'Permintaan memasukkan PIN lagi sebelum aksi sensitif (menyetujui/mencairkan uang). Ini lapisan keamanan, bukan error.',
  },
  {
    term: 'Penugasan Driver', full: 'Assignments', category: 'Operasional',
    desc: 'Pembagian driver ke appointment/nasabah. Driver mengonfirmasi kendaraan sebelum berangkat.',
  },
  {
    term: 'Air Minum', full: 'Pengajuan OB', category: 'Operasional',
    desc: 'Pengajuan pembelian air minum oleh OB. Finance memverifikasi, lalu mencetak tanda terima.',
  },
  {
    term: 'Overtime', full: 'Lembur', category: 'SDM',
    desc: 'Pengajuan jam lembur OB/Security/Driver dengan persetujuan berjenjang sesuai peran.',
  },
  {
    term: 'Rekap', full: 'Laporan transaksi', category: 'Laporan',
    desc: 'Daftar transaksi terarsip pada rentang tanggal tertentu, bisa diunduh sebagai PDF.',
  },
  {
    term: 'Audit Log', full: 'Jejak aktivitas', category: 'Keamanan',
    desc: 'Catatan siapa melakukan apa dan kapan. Dipakai untuk investigasi dan kepatuhan ISO 27001.',
  },
  {
    term: 'Cabang', full: 'Branch', category: 'Data & istilah',
    desc: 'Unit kerja (Surabaya, Bandung, dst.). Admin cabang terkunci ke cabangnya dan tidak melihat data cabang lain.',
  },
]

const PAGE_HELP = [
  {
    paths: ['/dashboard', '/ga', '/finance'],
    title: 'Dashboard',
    summary: 'Mulai dari kartu “Perlu Tindakan Hari Ini”, lalu buka antrean yang angkanya paling besar.',
    steps: [
      'Klik kartu tindakan untuk langsung pindah ke antrean terkait.',
      'Gunakan tab antrean (GA/Finance/Konfirmasi Driver) sesuai pekerjaan Anda.',
      'Klik 👁 Detail untuk melihat foto bukti, ODO, liter, dan cross-check sebelum memutuskan.',
      'Angka badge di sidebar ikut berubah setelah aksi berhasil.',
    ],
    terms: ['GA', 'Finance', 'Anomali ML', 'Step-up PIN'],
  },
  {
    paths: ['/trips'],
    title: 'Log Perjalanan',
    summary: 'Pantau perjalanan driver: mulai, selesai, dan hasil kunjungan ke nasabah.',
    steps: [
      'Filter status untuk melihat perjalanan yang masih berjalan atau perlu tindakan.',
      'Buka detail untuk melihat waktu mulai/selesai dan catatan driver.',
      'Perjalanan yang bermasalah bisa ditindaklanjuti lewat penugasan atau ACC atasan.',
    ],
    terms: ['Penugasan Driver', 'ODO'],
  },
  {
    paths: ['/assignments'],
    title: 'Penugasan Driver',
    summary: 'Atur driver untuk setiap appointment dan pastikan kendaraannya dikonfirmasi.',
    steps: [
      'Pilih driver pada baris appointment, lalu simpan penugasan.',
      'Driver akan menerima notifikasi dan mengonfirmasi kendaraan.',
      'Gunakan badge di sidebar untuk melihat berapa penugasan belum dikonfirmasi.',
    ],
    terms: ['Penugasan Driver'],
  },
  {
    paths: ['/cash'],
    title: 'BBM, Kasbon & SPBU',
    summary: 'Klaim BBM, kasbon/LPJ driver, lampiran MyPertamina, dan Data SPBU dalam satu halaman.',
    steps: [
      'Klaim BBM: tinjau klaim masuk, cairkan yang sudah ACC GA, lalu unduh PDF per transaksi.',
      'Kasbon: setujui/tolak pengajuan dana dan periksa bukti LPJ driver (termasuk kode harian).',
      'Data SPBU: cocokkan klaim ke riwayat SPBU Subsidi Tepat dan pantau Berita Acara.',
    ],
    terms: ['Kasbon', 'LPJ', 'Klaim BBM', 'Subsidi Tepat', 'Step-up PIN'],
  },
  {
    paths: ['/water'],
    title: 'Air Minum',
    summary: 'Verifikasi pengajuan air minum dari OB dan cetak tanda terima.',
    steps: [
      'Buka pengajuan berstatus menunggu, lalu periksa item dan foto bukti.',
      'Isi remark verifikasi atau alasan penolakan — wajib untuk audit.',
      'Pengajuan terverifikasi bisa dicetak sebagai tanda terima.',
    ],
    terms: ['Air Minum'],
  },
  {
    paths: ['/approvals'],
    title: 'ACC Atasan',
    summary: 'Antrean persetujuan berjenjang sebelum pengajuan diproses back-office.',
    steps: [
      'Buka Keputusan pada pengajuan yang menunggu Anda.',
      'Tulis catatan — wajib diisi bila menolak.',
      'Rantai ACC menunjukkan siapa saja yang harus menyetujui.',
    ],
    terms: ['ACC Atasan', 'Kasbon', 'Klaim BBM', 'Overtime'],
  },
  {
    paths: ['/rekap'],
    title: 'Rekap',
    summary: 'Lihat dan unduh transaksi terarsip pada rentang tanggal tertentu.',
    steps: [
      'Pilih tanggal Dari/Sampai, lalu klik Tampilkan.',
      'Gunakan Preview PDF untuk melihat sebelum mengunduh.',
      'Status memakai label manusiawi, bukan kode database.',
    ],
    terms: ['Rekap', 'Terarsip'],
  },
  {
    paths: ['/analytics'],
    title: 'Analytics',
    summary: 'Lihat pola pemakaian BBM, biaya, dan efisiensi per driver/kendaraan.',
    steps: [
      'Pilih periode yang ingin dianalisis.',
      'Bandingkan nominal, liter, dan km/L antar driver atau kendaraan.',
      'Gunakan temuan untuk menindaklanjuti klaim ber-flag anomali.',
    ],
    terms: ['ODO', 'Anomali ML', 'Klaim BBM'],
  },
  {
    paths: ['/assets'],
    title: 'Aset & Pemeliharaan',
    summary: 'Catat AC, kendaraan, dan jadwal servisnya agar biaya operasional terkendali.',
    steps: [
      'Tambahkan aset/kendaraan lewat tombol Tambah.',
      'Catat log servis beserta odometer dan biaya.',
      'Hapus hanya data yang salah input — tindakan ini masuk audit.',
    ],
    terms: ['ODO', 'Audit Log'],
  },
  {
    paths: ['/settings'],
    title: 'Pengaturan',
    summary: 'Atur cabang, driver, kendaraan, harga BBM, dan kebijakan operasional.',
    steps: [
      'Admin cabang hanya melihat cabangnya (read-only untuk data lintas cabang).',
      'Aksi berisiko (hapus, reset PIN, bersihkan demo) memakai modal konfirmasi.',
      'Perubahan penting tercatat di Audit Log.',
    ],
    terms: ['Cabang', 'HO', 'Audit Log', 'Step-up PIN'],
  },
  {
    paths: ['/users'],
    title: 'Manajemen User',
    summary: 'Kelola akun, peran, dan status aktif pengguna.',
    steps: [
      'Periksa peran sebelum mengaktifkan akun — gunakan hak akses minimal.',
      'Akun tanpa login lama bisa ditinjau lewat Access Review.',
      'Reset PIN pengguna hanya bila diminta pemilik akun.',
    ],
    terms: ['HO', 'Audit Log'],
  },
  {
    paths: ['/logs'],
    title: 'Audit Log',
    summary: 'Telusuri jejak aktivitas untuk investigasi dan kepatuhan.',
    steps: [
      'Filter berdasarkan tanggal, pengguna, atau aksi.',
      'Buka detail untuk melihat IP, referensi transaksi, dan data lama.',
      'Gunakan arsip audit di Pengaturan untuk data yang sangat lama.',
    ],
    terms: ['Audit Log'],
  },
  {
    paths: ['/it', '/transcoder', '/pdfkit'],
    title: 'Perkakas IT',
    summary: 'Alat bantu operasional IT: scraper berita, transcoder media, dan kompres PDF.',
    steps: [
      'Periksa status job sebelum menutup halaman.',
      'Batalkan job yang salah daripada menunggu selesai.',
      'Hapus hasil hanya bila sudah tidak diperlukan.',
    ],
    terms: ['Audit Log'],
  },
  {
    paths: ['/receptionist'],
    title: 'Rekrutmen',
    summary: 'Data pelamar kerja cabang Anda: interview, 4 hari training, sampai lulus.',
    steps: [
      'Receptionist mengelola penuh: verifikasi, koreksi data, kehadiran, status, dan laporan PDF.',
      'Traineer melihat halaman yang sama dalam mode lihat saja — tanpa tombol pengelolaan.',
      'Isi filter tanggal/upline/user/status lalu tekan Cari untuk mempersempit daftar.',
    ],
    terms: ['Audit Log'],
  },
  {
    paths: ['/first-work'],
    title: 'Absensi FirstWork',
    summary: 'Pendaftar first work mengisi form publik; Traineer memverifikasi datanya.',
    steps: [
      'Chip Menunggu membuka antrean yang belum diverifikasi.',
      'Buka Detail untuk memeriksa NIK, referensi, dan unduh KTP sebelum memutuskan.',
      'Penolakan wajib diberi alasan; semua keputusan tercatat di riwayat.',
      'Data hanya berisi cabang Anda — cabang lain tidak terlihat.',
    ],
    terms: ['HO'],
  },
  {
    paths: ['/inout'],
    title: 'In-Out Karyawan',
    summary: 'Catatan keluar-masuk karyawan; sumber sheet atau input receptionist.',
    steps: [
      'Sinkronkan data dari Google Sheet bila perlu — baris yang dikelola aplikasi tidak tertimpa.',
      'Gunakan filter tanggal untuk melihat aktivitas harian.',
      'Hapus data hanya dengan alasan yang jelas; tindakan masuk audit.',
    ],
    terms: ['Audit Log'],
  },
  {
    paths: ['/ga-hr'],
    title: 'Overtime',
    summary: 'Atur pengajuan lembur dan batas waktu persetujuannya.',
    steps: [
      'Periksa pengajuan yang menunggu ACC.',
      'Atur batas waktu agar pengajuan tidak menggantung.',
      'Pengajuan yang terlambat diberi penanda khusus.',
    ],
    terms: ['Overtime', 'ACC Atasan'],
  },
  {
    paths: ['/driver'],
    title: 'Aplikasi Driver',
    summary: 'Semua pekerjaan lapangan ada di lima tab bawah: BBM, Kasbon, Trip, OT, dan Rapor.',
    steps: [
      'BBM: isi klaim setelah mengisi bahan bakar; foto struk membantu verifikasi.',
      'Kasbon: ajukan dana sebelum perjalanan, lalu unggah LPJ setelahnya.',
      'Trip: mulai dan selesaikan perjalanan; data aman tersimpan saat offline.',
      'OT: ajukan lembur; Rapor: lihat ringkasan performa Anda.',
    ],
    terms: ['Klaim BBM', 'Kasbon', 'LPJ', 'Overtime', 'ODO'],
  },
  {
    paths: ['/marketing', '/chief-driver'],
    title: 'Operasional Marketing & Driver',
    summary: 'Kelola appointment, penugasan, dan hasil kunjungan nasabah.',
    steps: [
      'Periksa appointment hari ini terlebih dahulu.',
      'Batalkan atau ubah area dengan alasan yang jelas.',
      'Gunakan penugasan untuk membagi kendaraan secara adil.',
    ],
    terms: ['Penugasan Driver'],
  },
]

export function helpForPath(path) {
  const p = String(path || '').replace(/\/+$/, '') || '/'
  return PAGE_HELP.find((h) => h.paths.some((x) => p === x || p.startsWith(`${x}/`))) || null
}

const ROLE_FOCUS = {
  admin: 'Dashboard menampilkan ringkasan cabang Anda. Data cabang lain tetap terpisah dan tidak terlihat dari akun ini.',
  ga: 'Pekerjaan utama Anda ada di Dashboard GA: verifikasi klaim BBM dan pantau penugasan driver.',
  finance: 'Pekerjaan utama Anda ada di Dashboard Finance: cairkan klaim terverifikasi dan cek rekap air minum.',
  marketing: 'Marketing Hub membantu Anda memantau appointment dan hasil kunjungan nasabah.',
  chief_driver: 'Chief Driver mengatur penugasan, mengganti driver, dan memantau perjalanan yang berjalan.',
  ga_hr: 'Halaman Overtime membantu Anda mengelola pengajuan lembur dan batas waktunya.',
  receptionist: 'Menu Rekrutmen berisi data pelamar kerja cabang Anda; in-out karyawan ada di menu SDM.',
  ob: 'Pengajuan air minum dan overtime bisa Anda pantau dari menu operasional.',
  security: 'Pengajuan overtime bisa Anda pantau dari menu Overtime Saya.',
  traineer: 'Verifikasi pendaftar first work ada di menu Absensi FirstWork; data pelamar cabang Anda bisa dilihat (hanya lihat) di menu Rekrutmen.',
  driver: 'Gunakan tab bawah untuk BBM, Kasbon, Trip, Overtime, dan Rapor. Data tetap tersimpan saat sinyal lemah.',
}

export function onboardingSteps(role, user, isHoAdmin = false) {
  const name = user?.full_name || user?.user_name || 'rekan'
  if (role === 'driver') {
    return [
      {
        icon: '👋',
        title: `Selamat datang, ${name}`,
        body: 'Aplikasi driver punya lima tab di bawah: BBM, Kasbon, Trip, OT, dan Rapor.',
        points: [
          'Mulai dari tab BBM setelah mengisi bahan bakar.',
          'Tombol ❓ di kanan atas membuka bantuan dan arti istilah.',
        ],
      },
      {
        icon: '📴',
        title: 'Tetap bisa dipakai saat sinyal lemah',
        body: 'Data yang Anda isi disimpan di perangkat. Saat online kembali, tekan Sinkron atau biarkan aplikasi mengirim otomatis.',
        points: [
          'Status 🟡 Offline berarti data menunggu dikirim.',
          'Jangan hapus aplikasi sebelum data tersinkron.',
        ],
      },
      {
        icon: '💵',
        title: 'Kasbon harus punya LPJ',
        body: 'Kasbon adalah dana muka untuk perjalanan. Setelah selesai, unggah LPJ berisi bukti pemakaian.',
        points: [
          'Nominal kasbon sudah termasuk kode unik hari ini.',
          'LPJ yang belum disetujui membuat kasbon belum selesai.',
        ],
      },
      {
        icon: '🔒',
        title: 'PIN adalah kunci Anda',
        body: 'Jangan bagikan PIN kepada siapa pun. Semua pengajuan tercatat atas nama akun Anda.',
        points: [
          'Periksa nominal dan nopol sebelum mengirim.',
          'Hubungi Admin bila PIN lupa atau akun bermasalah.',
        ],
      },
    ]
  }
  const roleLabel = role === 'admin' && !isHoAdmin ? 'Admin Cabang' : (role || 'pengguna')
  const focus = ROLE_FOCUS[role] || 'Gunakan menu di kiri untuk memulai. Semua halaman punya panduan singkat lewat tombol ?.'
  return [
    {
      icon: '👋',
      title: `Selamat datang, ${name}`,
      body: `Anda masuk sebagai ${roleLabel}. ${focus}`,
      points: [
        'Menu dikelompokkan agar mudah dicari.',
        'Tombol ❓ di kanan atas membuka bantuan dan glosarium kapan saja.',
      ],
    },
    {
      icon: '⚡',
      title: 'Mulai dari yang mendesak',
      body: 'Di dashboard, blok “Perlu Tindakan Hari Ini” menunjukkan pekerjaan yang menunggu. Klik kartunya untuk langsung menuju antrean.',
      points: [
        'Angka badge di sidebar = jumlah yang menunggu tindakan.',
        'Kartu bernilai 0 disembunyikan agar layar tidak penuh.',
      ],
    },
    {
      icon: '🔎',
      title: 'Cari menu & pahami istilah',
      body: 'Tekan Ctrl+K (atau ⌘K) untuk mencari menu. Istilah seperti GA, LPJ, ODO, atau step-up PIN dijelaskan di glosarium.',
      points: [
        'Ctrl+K → ketik nama menu → Enter.',
        'Tekan ? untuk membuka bantuan halaman ini.',
      ],
    },
    {
      icon: '🔒',
      title: 'Aman & tercatat',
      body: 'Aksi yang menyentuh uang akan meminta PIN ulang (step-up). Setiap keputusan penting tercatat di Audit Log.',
      points: [
        'Jangan bagikan PIN kepada siapa pun.',
        'Gunakan tombol Batal pada modal konfirmasi bila ragu.',
      ],
    },
  ]
}
