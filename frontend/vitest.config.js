import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'happy-dom',
    include: ['src/**/*.test.js'],
    globals: true,
    // v2.47.1: worker dibatasi. Default vitest melahirkan banyak worker per
    // proses — di mesin 4 core yang sedang sibuk (server + Docker), test yang
    // aman sendiri bisa timeout 5 dtk karena berebut CPU (teramati:
    // SettingsView & AdminDashboard gagal lalu lulus saat dijalankan sendiri).
    // Batas worker menyelesaikannya TANPA menaikkan timeout/assertion.
    maxWorkers: 4,
    minWorkers: 1,
    // Timeout test dinaikkan (bukan assertion diubah): di mesin sibuk test
    // interaktif-butuh DOM yang biasanya 50-800ms bisa melebihi 5 dtk hanya
    // karena antrean CPU -> merah palsu. Gagal fungsi tetap gagal (tetap ada
    // assertion & pesan error yang sama).
    testTimeout: 15000,
  },
})
