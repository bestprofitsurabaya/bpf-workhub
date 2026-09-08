-- v2.37.6 — Data identitas cabang untuk kop dokumen (sumber resmi:
-- https://www.bestprofit-futures.co.id/hubungi-kami) + penonaktifan Palembang.
USE bpf_asset_system;

UPDATE branches SET
  address='Graha Bukopin, Lantai 11, Jl. Panglima Sudirman No. 10-18, Surabaya 60271',
  phone='031-5349888', city='Surabaya', company_subtitle='Cabang Surabaya'
WHERE code='SBY';

UPDATE branches SET
  address='Equity Tower Lt. 47, Kawasan Niaga Terpadu Sudirman (SCBD), Jl. Jend. Sudirman Kav. 52-53, Jakarta 12190',
  phone='021-29035005', city='Jakarta', company_subtitle='Kantor Pusat | Jakarta'
WHERE code='JKT';

UPDATE branches SET
  address='Pacific Place Mall Shop Lt. 3, Unit 3-99, Jl. Jend. Sudirman Kav. 52-53, SCBD, Jakarta Selatan 12190',
  phone='021-57973015', city='Jakarta', company_subtitle='Cabang Pacific Place'
WHERE code='JKT2';

UPDATE branches SET
  address='Jl. Jakarta No. 21, Kel. Kacapiring, Kec. Batununggal, Kota Bandung 40271',
  phone='022-20504000', city='Bandung', company_subtitle='Cabang Bandung'
WHERE code='BDG';

UPDATE branches SET
  address='Ruko Pelita, Jl. Letjen S. Parman No. 59 Kav. 1, 3-5, Malang, Jawa Timur 65122',
  phone='0341-4345999', city='Malang', company_subtitle='Sistem Operasional | Malang'
WHERE code='MLG';

UPDATE branches SET
  address='Jl. Veteran No. 61, RT 5/RW 6, Kel. Lempongsari, Kec. Gajahmungkur, Kota Semarang, Jawa Tengah 50231',
  phone='024-76444722', city='Semarang', company_subtitle='Cabang Semarang'
WHERE code='SMG';

UPDATE branches SET
  address='Ruko Jati Junction, Jl. Perintis Kemerdekaan No. P9A-10A, Kel. Perintis, Kec. Medan Timur, Medan 20218',
  phone='061-80501610', city='Medan', company_subtitle='Cabang Medan'
WHERE code='MDN';

UPDATE branches SET
  address='Jl. Ahmad Yani KM. 4.5 No. 71/339, Kel. Kebun Bunga, Kec. Banjarmasin Timur, Kalimantan Selatan 70235',
  phone='0511-3263838', city='Banjarmasin', company_subtitle='Cabang Banjarmasin'
WHERE code='BJM';

UPDATE branches SET
  address='Jl. Jenderal Ahmad Yani No. 55, Kel. Pelita, Kec. Enggal, Kota Bandar Lampung 35117',
  phone='0721-5608000', city='Bandar Lampung', company_subtitle='Cabang Lampung'
WHERE code='LPG';

-- Palembang: tidak ada kantor cabang — nonaktifkan cabang + user-nya.
UPDATE branches SET is_active=0 WHERE code='PLM';
UPDATE users SET is_active=0 WHERE branch_code='PLM';

-- v2.37.7 — Cabang baru dari situs resmi (bestprofit-futures.co.id/hubungi-kami).
-- Ditambahkan NONAKTIF (is_active=0): data tercatat, diaktifkan Admin saat
-- kantor mulai dipakai (buat DB + akun via Pengaturan → Cabang & Nomor).
INSERT IGNORE INTO branches (code, name, db_name, city, address, phone, company_name, company_subtitle, system_name, system_version, is_active)
VALUES
  ('JMB', 'Cabang Jambi', 'bpf_branch_jmb', 'Jambi',
   'Jl. Kolonel Abunjani No. 29 C, Sipin, Kel. Selamat, Kec. Danau Sipin, Jambi 36129', '0741-668288',
   'PT BESTPROFIT FUTURES', 'Cabang Jambi', 'BPF WorkHub', 'v2.37.7', 0),
  ('PTK', 'Cabang Pontianak', 'bpf_branch_ptk', 'Pontianak',
   'Komplek Sentra Bisnis A. Yani Megamall C1-C5, Jl. A. Yani, Pontianak 78121', '0561-766133',
   'PT BESTPROFIT FUTURES', 'Cabang Pontianak', 'BPF WorkHub', 'v2.37.7', 0),
  ('PKU', 'Cabang Pekanbaru', 'bpf_branch_pku', 'Pekanbaru',
   'Komplek Sudirman City Square, Jl. Jend. Sudirman Blok C 5-6-7, Pekanbaru 28288', '0761-888828',
   'PT BESTPROFIT FUTURES', 'Cabang Pekanbaru', 'BPF WorkHub', 'v2.37.7', 0);
