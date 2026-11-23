#!/usr/bin/env python3
"""Buat 4 dokumen PDF resmi BPF WorkHub v2.131.1.

1. Panduan Resmi Driver (lengkap)
2. Panduan Resmi GA (lengkap)
3. Panduan Khusus Service - Driver
4. Panduan Khusus Service - GA

Jalankan dari root repo:
    python3 scripts/generate_user_guide_driver_ga.py [output_dir]

Menggunakan BPFBasePDF agar kop, footer, dan identitas perusahaan mengikuti
system_config (sama seperti dokumen resmi lain di WorkHub).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from modules.pdf_generator import BPFBasePDF, INK, GRAY_LABEL, RULE

VERSION = 'v2.131.1'
TANGGAL = '23 November 2026'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOT_GA = os.path.join(ROOT, 'docs', 'public', 'screenshots', 'ga-service-audit.png')
SHOT_DRIVER = os.path.join(ROOT, 'docs', 'public', 'screenshots', 'driver-service-audit.png')
SHOTS = os.path.join(ROOT, 'docs', 'public', 'screenshots', 'all')
def shot(name):
    return os.path.join(SHOTS, name + '.png')


class GuidePDF(BPFBasePDF):
    def __init__(self, doc_title, audience):
        super().__init__(orientation='P', unit='mm', format='A4')
        self.set_auto_page_break(auto=True, margin=16)
        self.doc_title = doc_title
        self.audience = audience
        self.set_title(f'{doc_title} {VERSION}')

    # ---------- helper ----------
    def h1(self, text):
        if self.get_y() > 235:
            self.add_page()
        self.ln(2)
        self.set_font(self._font(), 'B', 13)
        self.set_text_color(*INK)
        self.cell(0, 7, self.clean_text(text), new_x='LMARGIN', new_y='NEXT')
        self.set_draw_color(*RULE)
        self.set_line_width(0.5)
        self.line(self.l_margin, self.get_y() + 0.5, self.w - self.r_margin, self.get_y() + 0.5)
        self.ln(3)

    def h2(self, text):
        if self.get_y() > 240:
            self.add_page()
        self.ln(1.5)
        self.set_font(self._font(), 'B', 10.5)
        self.set_text_color(*INK)
        self.cell(0, 6, self.clean_text(text), new_x='LMARGIN', new_y='NEXT')
        self.ln(1)

    def para(self, text, size=9.5):
        self.set_font(self._font(), '', size)
        self.set_text_color(*INK)
        self.multi_cell(0, 5, self.clean_text(text), new_x='LMARGIN', new_y='NEXT')
        self.ln(1.5)

    def bullets(self, items, size=9.5):
        self.set_font(self._font(), '', size)
        self.set_text_color(*INK)
        for it in items:
            self.cell(5, 4.8, '-', new_x='RIGHT', new_y='TOP')
            self.multi_cell(0, 4.8, self.clean_text(it), new_x='LMARGIN', new_y='NEXT')
        self.ln(1.5)

    def steps(self, items):
        self.bullets([f'{i + 1}. {t}' for i, t in enumerate(items)])

    def note(self, text):
        y = self.get_y()
        self.set_fill_color(240, 249, 255)
        self.set_draw_color(37, 99, 235)
        self.set_line_width(0.3)
        self.set_font(self._font(), '', 9)
        self.set_text_color(*INK)
        txt = self.clean_text(text)
        lines = max(1, (len(txt) // 95) + 1)
        self.rect(self.l_margin, y, self.w - self.l_margin - self.r_margin,
                  lines * 4.8 + 5, style='DF')
        self.set_xy(self.l_margin + 3, y + 2.5)
        self.multi_cell(self.w - self.l_margin - self.r_margin - 6, 4.8, txt,
                        new_x='LMARGIN', new_y='NEXT')
        self.ln(3)

    def table(self, headers, rows, widths=None, size=8):
        if widths is None:
            widths = [self.w / len(headers)] * len(headers)
        line_h, pad = 4.3, 1.4

        def draw_header():
            self.set_font(self._font(), 'B', size)
            self.set_fill_color(15, 23, 42)
            self.set_text_color(255, 255, 255)
            for h, w in zip(headers, widths):
                self.cell(w, 6.5, self.clean_text(h), border=1, align='C', fill=True)
            self.ln()

        draw_header()
        self.set_font(self._font(), '', size)
        self.set_text_color(*INK)
        for i, row in enumerate(rows):
            wrapped = []
            for val, w in zip(row, widths):
                lines = self.multi_cell(w - 2 * pad, line_h,
                                        self.clean_text(str(val)),
                                        dry_run=True, output='LINES')
                wrapped.append(lines)
            h = max(len(lines) for lines in wrapped) * line_h + 2 * pad
            if self.get_y() + h > self.h - self.b_margin:
                self.add_page()
                draw_header()
                self.set_font(self._font(), '', size)
                self.set_text_color(*INK)
            y = self.get_y()
            x = self.l_margin
            if i % 2 == 1:
                self.set_fill_color(248, 250, 252)
            for lines, w in zip(wrapped, widths):
                if i % 2 == 1:
                    self.rect(x, y, w, h, style='F')
                self.set_xy(x + pad, y + pad)
                self.multi_cell(w - 2 * pad, line_h, '\n'.join(lines), border=0,
                                new_x='LMARGIN', new_y='NEXT')
                self.rect(x, y, w, h)
                x += w
            self.set_xy(self.l_margin, y + h)
        self.ln(2)

    def screenshot(self, path, caption):
        if not os.path.exists(path):
            return
        # Jangan pisahkan caption dari gambar saat halaman hampir penuh.
        if self.get_y() > 175:
            self.add_page()
        self.ln(1)
        self.set_font(self._font(), 'I', 8)
        self.set_text_color(*GRAY_LABEL)
        self.cell(0, 4, self.clean_text(caption), new_x='LMARGIN', new_y='NEXT')
        try:
            self.image(path, w=165)
            self.ln(3)
        except Exception:
            pass

    # ---------- cover & toc ----------
    def cover(self, scope):
        self.add_page()
        self.ln(28)
        self.set_font(self._font(), 'B', 21)
        self.cell(0, 12, 'PANDUAN RESMI PENGGUNA', align='C', new_x='LMARGIN', new_y='NEXT')
        self.set_font(self._font(), 'B', 16)
        self.set_text_color(*GRAY_LABEL)
        self.cell(0, 10, self.clean_text(self.doc_title.upper()), align='C',
                  new_x='LMARGIN', new_y='NEXT')
        self.set_text_color(*INK)
        self.ln(4)
        self.set_font(self._font(), '', 12)
        self.cell(0, 7, 'BPF WorkHub - Sistem Operasional Terpadu', align='C',
                  new_x='LMARGIN', new_y='NEXT')
        self.ln(18)
        self.table(['Dokumen', 'Keterangan'], [
            ['Judul', self.doc_title],
            ['Versi aplikasi', VERSION],
            ['Tanggal terbit', TANGGAL],
            ['Pemilik dokumen', 'IT / General Affairs - PT Bestprofit Futures'],
            ['Pembaca', self.audience],
            ['Cakupan', scope],
            ['Klasifikasi', 'Internal - gunakan sesuai wewenang akun masing-masing'],
        ], widths=[45, 120], size=9)
        self.ln(8)
        self.para('Dokumen ini merupakan panduan resmi penggunaan BPF WorkHub. Isi dapat '
                  'berubah mengikuti versi aplikasi; selalu gunakan dokumen dengan versi terbaru.')
        self.note('PIN dan kredensial tidak dicantumkan. Gunakan akun yang diberikan Admin dan '
                  'jangan bagikan PIN kepada pihak lain.')

    def toc(self, entries):
        self.add_page()
        self.h1('DAFTAR ISI')
        self.table(['No', 'Judul'], entries, widths=[18, 147], size=9)

    # ---------- konten umum ----------
    def common(self):
        self.h1('A. INFORMASI UMUM')
        self.h2('A.1 Cara Masuk (Login)')
        self.steps([
            'Buka alamat aplikasi BPF WorkHub di browser HP atau komputer.',
            'Masukkan Username dan PIN yang diberikan Admin.',
            'Tekan Masuk. Jika MFA aktif, masukkan kode 6 digit dari aplikasi authenticator.',
            'Sistem menampilkan halaman sesuai peran: Driver atau Dashboard GA.',
        ])
        self.note('PIN bersifat rahasia. Jika lupa, hubungi Admin untuk_reset PIN. Jangan mencoba '
                  'berulang kali - sistem membatasi percobaan login untuk keamanan.')
        self.h2('A.2 Verifikasi Dua Langkah (MFA)')
        self.bullets([
            'Sekali kali: daftarkan aplikasi authenticator melalui menu Pengaturan -> Keamanan.',
            'Login berikutnya: masukkan kode 6 digit yang berubah setiap 30 detik.',
            'Jika ponsel hilang atau aplikasi ter-reset, minta kode pemulihan dari Admin.',
        ])
        self.h2('A.3 Profil & Nama Tampilan')
        self.para('Nama yang tampil diambil dari Pengaturan -> Manajemen User (full_name / '
                  'display_name), bukan username operasional. Username tetap dipakai sistem untuk '
                  'mencatat transaksi dan notifikasi.')
        self.h2('A.4 Mode Offline & Sinkronisasi')
        self.bullets([
            'Data yang diisi tersimpan otomatis di HP (antrean lokal).',
            'Saat sinyal kembali, aplikasi mengirim sendiri datanya ke server.',
            'Tanda Online / Offline di atas layar menunjukkan status koneksi.',
            'Tekan Sinkron untuk mengirim manual, atau buka panel antrean untuk melihat data gagal.',
            'Jika sesi berakhir, login lagi - antrean tetap aman dan tidak.dobel.',
        ])
        self.h2('A.5 Notifikasi HP')
        self.para('Aktifkan lewat ikon lonceng di kanan atas agar tidak ketinggalan penugasan '
                  'atau kabar persetujuan. Android (Chrome) langsung berfungsi; iPhone/iPad '
                  'wajib iOS 16.4+ dan aplikasi sudah ditambahkan ke Layar Utama.')

    # ---------- driver ----------
    def driver(self):
        self.h1('B. PANDUAN DRIVER')
        self.para('Halaman Driver memiliki empat tab di bawah: BBM, Trip, OT, dan Service. '
                  'Kasbon berada di dalam tab BBM sebagai sub-tab, dan feedback km/L muncul '
                  'otomatis setelah laporan BBM berhasil dikirim.')
        self.h2('B.1 Tab BBM - Laporan Pemakaian')
        self.table(['Mode', 'Kapan dipakai', 'Yang diisi'], [
            ['Klaim BBM', 'Driver membayar dulu di SPBU, lalu diganti kantor',
             'Jenis BBM, nominal, ODO, foto ODO sebelum, nota + ODO sesudah, struk'],
            ['Voucher Rekanan', 'SPBU mitra memberi voucher + blanko; kantor membayar mitra',
             'SPBU mitra, nomor nota, liter dari nota, foto yang sama'],
        ], widths=[35, 60, 70], size=8)
        self.steps([
            'Buka tab BBM, pilih mode Klaim atau Voucher Rekanan.',
            'Isi nopol, tipe kendaraan, jenis BBM, harga/liter, dan ODO (km).',
            'Untuk Klaim isi nominal; untuk Voucher nominal terisi otomatis.',
            'Ambil foto wajib: ODO sebelum, nota + ODO sesudah, dan struk. SPBU non-rekanan wajib foto dispenser.',
            'Tekan Kirim Laporan BBM. Foto otomatis mendapat watermark perusahaan, tanggal, dan lokasi GPS.',
        ])
        self.note('Pastikan ODO terbaca jelas. Liter dari pengisian beruntun (top up) akan '
                  'diakumulasi ke pengisian penuh berikutnya oleh sistem untuk menghitung km/L.')
        self.h2('B.2 Sub-tab Kasbon & LPJ')
        self.steps([
            'Masuk ke tab BBM, lalu pilih sub-tab Kasbon & LPJ.',
            'Isi nominal dasar; sistem menambahkan kode unik harian agar pembayaran mudah dicocokkan.',
            'Tekan Ajukan Kasbon. Setelah disetujui GA dan Finance, dana diserahkan ke driver.',
            'Begitu dana cair, banner kewajiban LPJ muncul di form BBM. Isi bukti pemakaiannya.',
            'LPJ selesai setelah diverifikasi GA; status kasbon menjadi COMPLETED.',
        ])
        self.h2('B.3 Tab Trip')
        self.para('Catat tujuan, lokasi berangkat, lokasi tujuan, KM awal, dan KM akhir. Draft '
                  'tersimpan otomatis di HP. Lokasi lengkap dan SPBU terdekat ikut tersimpan sebagai bukti.')
        self.h2('B.4 Tab OT (Overtime)')
        self.para('Ajukan lembur dengan mengisi tanggal, jam mulai/selesai, dan keterangan. '
                  'Foto bukti bila diminta. Pengajuan masuk antrean persetujuan.')
        self.service_driver(heading='B.5')
        self.h2('B.6 Feedback km/L Setelah Submit BBM')
        self.para('Setelah laporan BBM berhasil dikirim, kartu feedback performa muncul otomatis '
                  'di tab BBM. Kartu menampilkan status HEMAT / CUKUP / BOROS, rata-rata km/liter, '
                  'dan saran perbaikan. Hanya transaksi sah yang dihitung.')
        self.note('Feedback tidak lagi berupa tab tersendiri. Jika ingin melihatnya lagi, '
                  'kirim laporan BBM berikutnya atau buka panduan dari menu Bantuan.')

    def service_driver(self, heading=''):
        title = f'{heading}. ' if heading else ''
        self.h2(title + 'Tab Service - Catatan Tambahan Service Mobil')
        self.para('Gunakan tab ini untuk menyampaikan keluhan atau kondisi kendaraan kepada GA. '
                  'Data langsung masuk antrean GA dan dapat dicetak sebagai dokumen resmi.')
        self.steps([
            'Buka tab Service di bawah.',
            'Periksa Nama Driver, Nomor Polisi, dan Jenis Mobil yang terisi otomatis.',
            'Isi KM Kendaraan secara manual sesuai ODO saat ini. Angka di profil hanya referensi.',
            'Tulis keluhan pada poin 1. Tekan Tambah Keluhan untuk poin berikutnya; maksimal 10 poin.',
            'Gunakan tombol silang di sebelah poin untuk menghapus keluhan yang tidak diperlukan.',
            'Tekan Kirim ke GA. Simpan nomor form yang muncul untuk referensi.',
        ])
        self.note('Minimal satu keluhan wajib diisi dan KM harus lebih dari 0. Riwayat di bawah '
                  'form menampilkan status SUBMITTED / REVIEWED / REJECTED beserta catatan GA.')
        self.screenshot(SHOT_DRIVER, 'Tampilan tab Service pada PWA Driver')

    # ---------- GA ----------
    def ga(self):
        self.h1('C. PANDUAN GA (GENERAL AFFAIRS)')
        self.para('Dashboard GA adalah pusat kendali: menyetujui klaim BBM, memverifikasi anomali, '
                  'menyetujui kasbon, meninjau perjalanan, dan memproses catatan service dari driver.')
        self.h2('C.1 Ringkasan Dashboard')
        self.bullets([
            'Antrean GA - klaim BBM yang menunggu persetujuan.',
            'Terverifikasi GA / Terarsip - jumlah transaksi yang sudah diproses.',
            'Kasbon menunggu approve - jumlah dan nominal pengajuan.',
            'Laporan perjalanan pending - trip yang belum ditinjau.',
            'Catatan Service Mobil - laporan kondisi kendaraan dari driver.',
        ])
        self.note('Dashboard terhubung realtime: klaim atau catatan service baru langsung '
                  'muncul tanpa perlu memuat ulang halaman.')
        self.h2('C.2 Menyetujui / Menolak Klaim BBM')
        self.steps([
            'Buka antrean klaim, lalu tekan Detail untuk melihat foto bukti dan hasil cross-check.',
            'Periksa nomor nota, ODO, nominal, dan kecocokan data Subsidi Tepat bila tersedia.',
            'Tekan Setujui. Untuk aksi yang menggerakkan uang, sistem meminta konfirmasi PIN ulang.',
            'Untuk menolak, tekan Tolak dan isi alasan wajib. Driver akan melihat alasan tersebut.',
            'Klaim dengan tanda anomali memakai tombol Verifikasi Anomali sebelum disetujui.',
        ])
        self.h2('C.3 Menyetujui & Menyerahkan Kasbon')
        self.para('Setujui pengajuan kasbon di antrean, lalu serahkan dana ke driver dan tandai '
                  'handover. Sistem otomatis membuat kewajiban LPJ; driver tidak bisa menganggap '
                  'kasbon selesai sebelum LPJ disetujui.')
        self.service_ga(heading='C.4')
        self.h2('C.5 Menu Terkait Lainnya')
        self.bullets([
            'Penugasan Driver - serah terima, tukar driver, catatan kondisi kendaraan, riwayat.',
            'Log Perjalanan - meninjau laporan trip driver.',
            'BBM, Kasbon & SPBU - melihat semua pengajuan dan data SPBU Subsidi Tepat.',
            'Analytics - performa armada dan efisiensi BBM.',
        ])

    def service_ga(self, heading=''):
        title = f'{heading}. ' if heading else ''
        self.h2(title + 'Memproses Catatan Service Mobil')
        self.steps([
            'Di panel Catatan Service Mobil, lihat jumlah laporan dengan status SUBMITTED.',
            'Tekan Detail untuk melihat KM manual dan daftar keluhan bernomor dari driver.',
            'Tambahkan catatan GA bila perlu (opsional, ikut tercetak di dokumen resmi).',
            'Tekan Selesaikan bila laporan sudah ditindaklanjuti, atau Tolak bila tidak valid.',
            'Tekan Cetak PDF untuk menghasilkan dokumen resmi berg kop perusahaan dan kolom tanda tangan.',
        ])
        self.note('Dokumen resmi berisi identitas driver, nopol, jenis mobil, KM kendaraan, '
                  'keluhan bernomor, pernyataan penyerahan, serta kolom tanda tangan Driver dan GA.')
        self.screenshot(SHOT_GA, 'Panel GA dan modal detail catatan service')

    # ---------- alur, faq, glosarium ----------
    def flow(self):
        self.h1('D. ALUR KERJA LINTAS PERAN')
        self.h2('D.1 Alur BBM')
        self.table(['Langkah', 'Peran', 'Hasil'], [
            ['1', 'Driver', 'Kirim laporan BBM (Klaim / Voucher) + foto bukti'],
            ['2', 'GA', 'Verifikasi foto, nominal, dan data pendukung'],
            ['3', 'GA', 'Setujui atau tolak dengan alasan'],
            ['4', 'Finance', 'Bayar klaim / tagihan voucher rekanan'],
            ['5', 'Driver', 'Lihat status di riwayat; baca feedback km/L'],
        ], widths=[18, 30, 117], size=8.5)
        self.h2('D.2 Alur Kasbon')
        self.table(['Langkah', 'Peran', 'Hasil'], [
            ['1', 'Driver', 'Ajukan nominal + kode unik harian'],
            ['2', 'GA', 'Setujui pengajuan'],
            ['3', 'Finance', 'Cairkan dana'],
            ['4', 'GA/Finance', 'Serahkan dana ke driver (handover)'],
            ['5', 'Driver', 'Isi LPJ lewat form BBM'],
            ['6', 'GA', 'Verifikasi LPJ - kasbon selesai'],
        ], widths=[18, 30, 117], size=8.5)
        self.h2('D.3 Alur Service Mobil')
        self.table(['Langkah', 'Peran', 'Hasil'], [
            ['1', 'Driver', 'Isi KM manual + keluhan bernomor di tab Service'],
            ['2', 'GA', 'Terima laporan secara realtime di Dashboard GA'],
            ['3', 'GA', 'Periksa detail, beri catatan, cetak dokumen resmi'],
            ['4', 'GA', 'Tandai Selesaikan / Tolak'],
        ], widths=[18, 30, 117], size=8.5)

    def faq(self):
        self.h1('E. FAQ & PEMECAHAN MASALAH')
        qs = [
            ('GPS tidak terdeteksi?', 'Izinkan lokasi di browser, keluar ruangan, lalu tekan Isi Lokasi & Jam. '
             'Aplikasi memakai posisi terakhir bila GPS gagal, tetapi sebaiknya tetap ambil bukti segar.'),
            ('Foto wajib apa saja?', 'ODO sebelum, nota + ODO sesudah, dan struk. SPBU non-rekanan wajib '
             'menambahkan foto dispenser. Semua foto mendapat watermark otomatis.'),
            ('Voucher dan klaim beda apa?', 'Klaim: driver membayar dulu lalu diganti. Voucher: SPBU mitra '
             'menyerahkan voucher, kantor yang membayar mitra per periode.'),
            ('Kenapa km/L saya 0?', 'km/L dihitung dari selisih ODO antar pengisian. Baris tanpa ODO '
             'atau pengisian pertama belum punya patokan jarak, jadi nilainya 0.'),
            ('Apakah KM service boleh ikut profil?', 'Boleh sebagai referensi, tetapi wajib dikonfirmasi '
             'dan diisi manual karena ODO profil bisa tertinggal.'),
            ('Berapa poin keluhan service?', 'Minimal 1, maksimal 10. Bisa ditambah dan dihapus sebelum dikirim.'),
            ('Bagaimana dokumen service dicetak?', 'GA membuka Detail lalu menekan Cetak PDF. Dokumen '
             'menggunakan kop perusahaan dan kolom tanda tangan Driver serta GA.'),
            ('Data saya belum terkirim?', 'Cek status di atas layar. Tekan Sinkron. Bila ada yang Gagal, '
             'perbaiki isinya lalu hubungi Admin. Data tidak akan.dobel saat dikirim ulang.'),
        ]
        for q, a in qs:
            self.h2(q)
            self.para(a)

    def glossary(self):
        self.h1('F. GLOSSARIUM & DAFTAR STATUS')
        self.table(['Istilah', 'Arti'], [
            ['BBM', 'Bahan bakar minyak; laporan pemakaian oleh driver'],
            ['Klaim', 'Driver menalangi pembelian, kantor mengganti'],
            ['Voucher', 'Pembelian di SPBU rekanan yang ditagihkan kantor'],
            ['Kasbon', 'Uang muka perjalanan; wajib di-LPJ'],
            ['LPJ', 'Laporan pertanggungjawaban pemakaian kasbon'],
            ['ODO', 'Odometer kendaraan dalam kilometer'],
            ['Top up', 'Pengisian beruntun yang liter ikut dihitung saat pengisian penuh'],
            ['Service', 'Catatan kondisi kendaraan dari driver ke GA'],
        ], widths=[35, 130], size=8.5)
        self.h2('Status yang Sering Muncul')
        self.table(['Status', 'Arti'], [
            ['SUBMITTED', 'Laporan terkirim dan menunggu diproses'],
            ['REVIEWED', 'Sudah ditindaklanjuti GA'],
            ['REJECTED', 'Ditolak; lihat catatan GA'],
            ['PENDING / MODIFIED', 'Klaim masih dalam pemeriksaan'],
            ['VERIFIED_GA', 'Disetujui GA'],
            ['OS_FINANCE', 'Menunggu pembayaran Finance'],
            ['ARCHIVED', 'Transaksi final/arsip'],
            ['FUNDS_WITH_DRIVER', 'Dana kasbon sudah di tangan driver, LPJ belum ada'],
        ], widths=[45, 120], size=8.5)
        self.ln(4)
        self.note('Untuk bantuan lebih lanjut, hubungi Admin BPF WorkHub atau GA cabang Anda. '
                  'Dokumen ini mengikuti versi aplikasi ' + VERSION + '.')

    # ---------- builder ----------
    def build_full(self, role):
        if role == 'driver':
            self.cover('Alur Driver: BBM, Kasbon, Trip, OT, Service, feedback km/L')
            self.toc([['A', 'Informasi Umum'], ['B', 'Panduan Driver'],
                      ['D', 'Alur Kerja Lintas Peran'], ['E', 'FAQ & Pemecahan Masalah'],
                      ['F', 'Glosarium & Daftar Status']])
            self.common(); self.driver()
        else:
            self.cover('Alur GA: klaim, kasbon, service, cetak dokumen resmi')
            self.toc([['A', 'Informasi Umum'], ['C', 'Panduan GA'],
                      ['D', 'Alur Kerja Lintas Peran'], ['E', 'FAQ & Pemecahan Masalah'],
                      ['F', 'Glosarium & Daftar Status']])
            self.common(); self.ga()
        self.flow(); self.faq(); self.glossary()

    def build_service(self, role):
        if role == 'driver':
            self.cover('KM manual, keluhan bernomor, kirim ke GA, pantau status')
            self.toc([['1', 'Tentang Fitur Service'], ['2', 'Langkah Mengisi'],
                      ['3', 'Keluhan Bernomor'], ['4', 'Status & Riwayat'],
                      ['5', 'Tips & FAQ'], ['6', 'Alur Singkat']])
            self.h1('1. TENTANG FITUR SERVICE')
            self.para('Tab Service di PWA driver dipakai untuk menyampaikan catatan tambahan '
                      'service mobil: kondisi atau keluhan yang dirasakan driver. Laporan langsung '
                      'masuk ke GA dan dapat dicetak sebagai dokumen resmi.')
            self.h1('2. LANGKAH MENGISI')
            self.service_driver(heading='')
            self.h1('3. KELUHAN BERNOMOR')
            self.bullets([
                'Poin pertama tersedia secara default. Tekan Tambah Keluhan untuk poin berikutnya.',
                'Maksimal 10 poin. Setiap poin diberi nomor otomatis.',
                'Tombol silang menghapus poin yang dipilih. Minimal satu poin harus tersisa.',
                'Nomor tersimpan bersama laporan dan ikut tercetak di dokumen GA.',
            ])
            self.h1('4. STATUS & RIWAYAT')
            self.table(['Status', 'Arti'], [
                ['SUBMITTED', 'Terkirim, menunggu GA'],
                ['REVIEWED', 'Sudah ditindaklanjuti GA'],
                ['REJECTED', 'Ditolak - baca catatan GA'],
            ], widths=[45, 120], size=9)
            self.h1('5. TIPS & FAQ')
            self.faq()
            self.h1('6. ALUR SINGKAT')
            self.flow()
        else:
            self.cover('Review laporan service & cetak dokumen resmi')
            self.toc([['1', 'Tentang Fitur Service'], ['2', 'Panel Antrean GA'],
                      ['3', 'Memproses Laporan'], ['4', 'Dokumen Resmi'],
                      ['5', 'Status & FAQ'], ['6', 'Alur Singkat']])
            self.h1('1. TENTANG FITUR SERVICE')
            self.para('Catatan Service Mobil masuk langsung ke Dashboard GA secara realtime. '
                      'GA bertugas memeriksa keluhan driver, menindaklanjutinya, dan mencetak '
                      'dokumen resmi sebagai bukti penyerahan.')
            self.h1('2. PANEL ANTREAN GA')
            self.bullets([
                'Panel berada di Dashboard GA dengan judul Catatan Service Mobil (Driver -> GA).',
                'Kolom: No. Form, Driver, Nopol, KM, Status, Tanggal.',
                'Jumlah laporan SUBMITTED ditampilkan di sebelah kanan judul panel.',
                'Tombol Detail membuka modal pemeriksaan; tombol Cetak langsung mengunduh PDF.',
            ])
            self.h1('3. MEMPROSES LAPORAN')
            self.service_ga(heading='')
            self.h1('4. DOKUMEN RESMI')
            self.table(['Bagian', 'Isi'], [
                ['Kop', 'Nama perusahaan, alamat, telepon (mengikuti identitas cabang)'],
                ['Identitas', 'Driver, nopol, jenis mobil, KM manual, tanggal, no. form'],
                ['Keluhan', 'Daftar bernomor dari driver, urut sesuai input'],
                ['Pernyataan', 'Kalimat penyerahan keluhan untuk bahan pertimbangan servis'],
                ['Tanda tangan', 'Kolom Driver Kendaraan dan G.A Cabang'],
                ['Catatan GA', 'Opsional, ikut tercetak bila diisi'],
            ], widths=[40, 125], size=8.5)
            self.h1('5. STATUS & FAQ')
            self.table(['Status', 'Arti'], [
                ['SUBMITTED', 'Menunggu diproses GA'],
                ['REVIEWED', 'Selesai ditindaklanjuti'],
                ['REJECTED', 'Ditolak dengan catatan'],
            ], widths=[45, 120], size=9)
            self.faq()
            self.h1('6. ALUR SINGKAT')
            self.flow()


    def build_all(self):
        """Panduan resmi untuk semua peran/tim dalam satu dokumen."""
        self.cover('Seluruh peran: Driver, OB, Security, GA, GA HR, Finance, Marketing, Chief Driver, Receptionist, Traineer, Content, Admin, dan IT. Lengkap dengan tangkapan layar tiap aksi kritis.')
        self.toc([
            ['A', 'Informasi Umum & Agenda'],
            ['B', 'Driver - BBM, Kasbon, Trip, OT, Service'],
            ['C', 'OB & Security - Air Minum dan Overtime'],
            ['D', 'GA - Verifikasi, Kasbon, Service, Aset'],
            ['E', 'Finance - Pembayaran, Rekap, Subsidi Tepat'],
            ['F', 'Marketing & Chief Driver'],
            ['G', 'Receptionist, Traineer, GA HR, Content'],
            ['H', 'Admin & IT'],
            ['I', 'Alur Kerja Lintas Peran'],
            ['J', 'FAQ, Status & Glosarium'],
        ])

        self.h1('A. INFORMASI UMUM & AGENDA')
        self.common()
        self.h2('A.6 Agenda Bersama')
        self.para('Agenda bisa dibaca semua peran. Admin dan Content Creator bisa menambah, '
                  'mengubah, dan membagikan agenda; peran lain hanya melihat. Buka menu Agenda '
                  'di sidebar atau kartu Agenda di dashboard.')
        self.screenshot(shot('agenda'), 'Gambar 1. Halaman Agenda')

        self.h1('B. DRIVER - BBM, KASBON, TRIP, OT, SERVICE')
        self.driver()
        self.screenshot(shot('driver_bbm'), 'Gambar 2. Form Laporan BBM mode Klaim')
        self.screenshot(shot('driver_voucher'), 'Gambar 3. Form mode Voucher Rekanan')

        self.h1('C. OB & SECURITY - AIR MINUM DAN OVERTIME')
        self.h2('C.1 OB - Pembelian Air Minum')
        self.para('Ajukan pengiriman air minum lewat menu Air Minum. Isi tanggal, item, jumlah, '
                  'dan keterangan. Finance akan memverifikasi pengajuan sebelum diproses.')
        self.screenshot(shot('ob_water'), 'Gambar 4. Daftar pengajuan air minum OB')
        self.screenshot(shot('ob_form'), 'Gambar 5. Form Ajukan Pengiriman air minum')
        self.h2('C.2 OB & Security - Overtime Saya')
        self.para('Buka Overtime Saya untuk mengisi tanggal, jam, dan keterangan lembur. '
                  'Pengajuan masuk antrean GA HR.')
        self.screenshot(shot('security_overtime'), 'Gambar 6. Form Overtime Saya')

        self.h1('D. GA - VERIFIKASI, KASBON, SERVICE, ASET')
        self.ga()
        self.screenshot(shot('ga_service'), 'Gambar 7. Dashboard GA dan panel Catatan Service')
        self.screenshot(shot('ga_claim_detail'), 'Gambar 8. Modal detail klaim BBM di GA')

        self.h1('E. FINANCE - PEMBAYARAN, REKAP, SUBSIDI TEPAT')
        self.h2('E.1 Dashboard Finance')
        self.para('Finance melihat antrean air minum, klaim siap bayar, kasbon, dan kartu '
                  'Subsidi Tepat. Verifikasi air minum sebelum pembayaran.')
        self.screenshot(shot('finance'), 'Gambar 9. Dashboard Finance')
        self.h2('E.2 Rekap Pengeluaran')
        self.para('Buka menu BBM, Kasbon & SPBU untuk melihat realisasi tiga kanal: LPJ, '
                  'voucher rekanan, dan klaim tunai. Total = LPJ + voucher + klaim.')
        self.screenshot(shot('finance_laporan'), 'Gambar 10. Laporan realisasi pengeluaran')
        self.screenshot(shot('finance_water_detail'), 'Gambar 11. Detail pengajuan air minum di Finance')

        self.h1('F. MARKETING & CHIEF DRIVER')
        self.h2('F.1 Marketing - Appointment')
        self.para('Buat jadwal kunjungan, pilih driver dan tanggal, lalu simpan. Hasil kunjungan '
                  'diisi driver dan menjadi bahan laporan konversi.')
        self.screenshot(shot('marketing'), 'Gambar 12. Dashboard Marketing / Appointment')
        self.h2('F.2 Chief Driver - Pembagian Tugas')
        self.para('Atur rute otomatis atau manual, tugaskan driver, dan unduh rekap harian. '
                  'Perubahan langsung terlihat driver lewat notifikasi.')
        self.screenshot(shot('chief'), 'Gambar 13. Dashboard Chief Driver')

        self.h1('G. RECEPTIONIST, TRAINEER, GA HR, CONTENT')
        self.h2('G.1 Receptionist - Rekrutmen')
        self.para('Input pelamar, perbarui status, dan sinkron data dari Sheet bila dipakai.')
        self.screenshot(shot('receptionist'), 'Gambar 14. Halaman Rekrutmen')
        self.h2('G.2 Traineer - Absensi FirstWork')
        self.para('Lihat dan verifikasi data pengisian FirstWork. Filter status, lalu tandai '
                  'terverifikasi atau tolak.')
        self.screenshot(shot('traineer'), 'Gambar 15. Absensi FirstWork')
        self.h2('G.3 GA HR - Overtime')
        self.para('Lihat pengajuan overtime driver/OB/security, unduh Excel atau PDF, dan '
                  'refresh data dari Google Sheet bila sumbernya sheet.')
        self.screenshot(shot('gahr'), 'Gambar 16. Data Overtime GA HR')

        self.h1('H. ADMIN & IT')
        self.h2('H.1 Admin - User & Pengaturan')
        self.para('Admin mengelola user, role, cabang, kendaraan, dan pengaturan sistem. '
                  'Perubahan role berpengaruh langsung pada menu yang tersedia.')
        self.screenshot(shot('admin'), 'Gambar 17. Dashboard Admin')
        self.screenshot(shot('admin_users'), 'Gambar 18. Manajemen User & Driver')
        self.h2('H.2 IT - News Scraper & Inventaris')
        self.para('IT cabang menjalankan scrape berita, mengelola inventaris aset, label QR, '
                  'dan transceiver/transcoder sesuai wewenang.')
        self.screenshot(shot('it'), 'Gambar 19. Modul News Scraper IT')

        self.flow()
        self.faq()
        self.glossary()

def make_pdf(filename, doc_title, audience, builder, role):
    pdf = GuidePDF(doc_title, audience)
    try:
        pdf.set_identity()
    except Exception:
        pass
    if builder == 'full':
        pdf.build_full(role)
    elif builder == 'service':
        pdf.build_service(role)
    else:
        pdf.build_all()
    pdf.output(filename)
    print('OK:', filename)


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else ROOT
    os.makedirs(out_dir, exist_ok=True)
    make_pdf(os.path.join(out_dir, f'Panduan_Resmi_Driver_{VERSION}.pdf'),
             'Panduan Resmi Driver', 'Driver PWA cabang', 'full', 'driver')
    make_pdf(os.path.join(out_dir, f'Panduan_Resmi_GA_{VERSION}.pdf'),
             'Panduan Resmi GA', 'GA / General Affairs cabang', 'full', 'ga')
    make_pdf(os.path.join(out_dir, f'Panduan_Service_Driver_{VERSION}.pdf'),
             'Panduan Service - Driver', 'Driver PWA cabang', 'service', 'driver')
    make_pdf(os.path.join(out_dir, f'Panduan_Service_GA_{VERSION}.pdf'),
             'Panduan Service - GA', 'GA / General Affairs cabang', 'service', 'ga')
    make_pdf(os.path.join(out_dir, f'Panduan_Resmi_Semua_Pengguna_{VERSION}.pdf'),
             'Panduan Resmi Seluruh Pengguna', 'Semua peran BPF WorkHub', 'all', 'none')


if __name__ == '__main__':
    main()
