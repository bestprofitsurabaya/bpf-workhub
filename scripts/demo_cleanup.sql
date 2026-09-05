-- ============================================================
-- Bersihkan DATA DEMO (label DEMO) dari database
-- Cara pakai (password root dari .env):
--   ROOT_PW=$(grep -E '^MYSQL_ROOT_PASSWORD=' .env | cut -d= -f2-)
--   docker exec -i bbm_mariadb mariadb -uroot -p"$ROOT_PW" bpf_asset_system < scripts/demo_cleanup.sql
-- ============================================================
USE bpf_asset_system;

DELETE FROM water_purchase_items WHERE purchase_id IN (SELECT id FROM water_purchases WHERE display_id LIKE 'WTR-DEMO-%');
DELETE FROM water_purchases      WHERE display_id LIKE 'WTR-DEMO-%';
DELETE FROM transactions         WHERE display_id LIKE 'BPF-DEMO-%';
DELETE FROM fuel_cash_requests   WHERE display_id LIKE 'CASH-DEMO-%';
DELETE FROM trip_masters         WHERE display_id LIKE 'TRIP-DEMO-%';
DELETE FROM appointments         WHERE display_id LIKE 'APPT-DEMO-%';

-- OPSIONAL: hapus juga merk air minum contoh yang dibuat untuk demo.
-- Hapus tanda komentar hanya jika merk di atas memang murni data demo.
-- DELETE FROM water_drink_brands WHERE brand IN ('AQUA Galon','Club','Le Minerale','VIT Botol','VIT Gelas');
