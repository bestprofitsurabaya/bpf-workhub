import { expect, test, type Page } from '@playwright/test'

// baseURL, download, dan browser diatur di playwright.config.ts.
// E2E selalu menuju Flask lokal yang di-start scripts/ci_e2e.sh terhadap
// MariaDB uji yang di-seed. Tidak pernah ke produksi.
const PIN = '123456'
const SEED_SERVICE_ID = 'SRV-E2E-SEED-0001'
const SEED_CLAIM_ID = 'BBM-E2E-SEED-0001'

async function loginAs(page: Page, username: string) {
  await page.goto('/login')
  await page.getByPlaceholder('Masukkan username').fill(username)
  await page.locator('input[type=password]').fill(PIN)
  await page.getByRole('button', { name: /Masuk/ }).click()
  await expect(page).not.toHaveURL(/\/login/)
}

test.beforeEach(async ({ page }) => {
  // Onboarding tour (timeout 700 ms) dan tab tersimpan bisa menutupi tombol.
  await page.addInitScript(() => {
    for (const user of ['driversby_guruh', 'ga_sby', 'finance_sby']) {
      localStorage.setItem(`bpf_onboarded:${user}`, '1')
    }
    localStorage.removeItem('driverTab')
  })
})

test('driver kirim KM manual + dua keluhan bernomor', async ({ page }) => {
  await page.goto('/login')
  await page.getByPlaceholder('Masukkan username').fill('driversby_guruh')
  await page.locator('input[type=password]').fill('123456')
  await page.getByRole('button', { name: /Masuk/ }).click()
  // Tunggu sesi benar-benar terbentuk sebelum pindah halaman (anti race
  // antara POST /api/auth/login dan navigasi penuh).
  await expect(page).not.toHaveURL(/\/login/)
  await page.goto('/app/driver')
  await page.getByRole('button', { name: /Service/ }).click()
  await page.locator('#svc-km').fill('78179')
  await page.getByPlaceholder(/Rem depan/).fill('Rem depan berbunyi')
  await page.getByRole('button', { name: /Tambah Keluhan/ }).click()
  await page.getByPlaceholder(/Tambah keluhan lain/).fill('AC kurang dingin')
  await page.getByRole('button', { name: /Kirim ke GA/ }).click()
  const toast = page.getByText(/Terkirim ke GA/i)
  await expect(toast).toBeVisible()
  // Backend membalas "Catatan service SRV-… terkirim ke GA." (huruf kecil;
  // flag i menjaga teks persis "/Terkirim ke GA/" tetap terpakai).
  const idBaru = (await toast.innerText()).match(/SRV-[A-Z0-9-]+/)?.[0]
  expect(idBaru, 'toast wajib menyertakan display_id laporan baru').toBeTruthy()
  // Kartu riwayat ditargetkan lewat display_id kiriman ini — bukan kartu basi.
  const riwayat = page.locator('.svc-card').filter({ hasText: idBaru! })
  await expect(riwayat).toBeVisible()
  await expect(riwayat).toContainText('1. Rem depan berbunyi')
  await expect(riwayat).toContainText('2. AC kurang dingin')
})

test('GA tinjau laporan service, tandai selesai, unduh PDF', async ({ page }) => {
  await loginAs(page, 'ga_sby')
  await page.goto('/app/ga')

  const row = page.locator('tr', { hasText: SEED_SERVICE_ID })
  await expect(row).toBeVisible()
  await expect(row.getByText('SUBMITTED')).toBeVisible()
  await row.getByRole('button', { name: /Detail/ }).click()

  const detail = page.getByRole('dialog', { name: new RegExp(SEED_SERVICE_ID) })
  await expect(detail).toBeVisible()
  await expect(detail.getByText(/Rem depan berbunyi/)).toBeVisible()
  await detail.getByPlaceholder(/Opsional — ikut tercetak/).fill('Sudah dicek, jadwalkan servis.')
  await detail.getByRole('button', { name: /Selesaikan/ }).click()
  await expect(detail).toHaveCount(0)

  // Daftar dimuat ulang dari API (bukan event socket) — lihat ruling progress.
  const refresh = await page.request.get('/api/ga/service-reports')
  expect(refresh.ok()).toBeTruthy()
  const laporan = (await refresh.json()).data.find((r: any) => r.display_id === SEED_SERVICE_ID)
  expect(laporan?.status).toBe('REVIEWED')
  await expect(page.locator('tr', { hasText: SEED_SERVICE_ID }).getByText('REVIEWED')).toBeVisible()

  // Dokumen resmi: endpoint PDF menghasilkan attachment PDF nyata.
  const pdf = await page.request.get(`/api/ga/service-reports/${laporan.id}/pdf`)
  expect(pdf.ok()).toBeTruthy()
  expect(pdf.headers()['content-type']).toContain('application/pdf')
  expect(pdf.headers()['content-disposition']).toContain('attachment')
  expect((await pdf.body()).subarray(0, 4).toString()).toBe('%PDF')

  // Tombol "Cetak" di baris memanggil endpoint PDF lewat window.open.
  const unduh = page.waitForEvent('download', { timeout: 10_000 })
  await page.locator('tr', { hasText: SEED_SERVICE_ID }).getByRole('button', { name: /Cetak/ }).click()
  expect((await unduh).suggestedFilename()).toContain('Form_Service_')
})

test('Finance melihat klaim siap bayar setelah GA approve', async ({ page, browser }) => {
  // ACC-2 (GA) lewat UI, termasuk step-up PIN.
  await loginAs(page, 'ga_sby')
  await page.goto('/app/ga')
  const row = page.locator('tr', { hasText: SEED_CLAIM_ID })
  await expect(row).toBeVisible()
  await row.getByRole('button', { name: /Setujui/ }).click()
  await page.getByRole('button', { name: 'Ya, setujui' }).click()

  const stepup = page.getByRole('dialog', { name: /Verifikasi PIN ulang/ })
  await expect(stepup).toBeVisible()
  await stepup.getByPlaceholder('PIN 6 digit').fill(PIN)
  await stepup.getByRole('button', { name: /Verifikasi/ }).click()
  await expect(stepup).toHaveCount(0)
  await expect(page.locator('tr', { hasText: SEED_CLAIM_ID })).toHaveCount(0)

  // Finance melihat antrean baru. Konteks terpisah karena sesi GA sudah ada.
  const financeContext = await browser.newContext({
    baseURL: process.env.E2E_BASE_URL || 'http://127.0.0.1:5000',
  })
  try {
    const financePage = await financeContext.newPage()
    await loginAs(financePage, 'finance_sby')
    await financePage.goto('/app/finance')
    await expect(financePage.getByTestId('finance-priorities')).toBeVisible()
    await expect(financePage.getByTestId('priority-bbm_verify_pending')).toBeVisible()

    // Ruling: E2E memastikan daftar Finance termuat ulang lewat API,
    // bukan menguji event socket realtime (task terpisah).
    const queue = await financePage.request.get('/api/queue?tab=finance')
    expect(queue.ok()).toBeTruthy()
    const rows = await queue.json()
    expect(Array.isArray(rows)).toBeTruthy()
    expect(rows.some((t: any) => t.display_id === SEED_CLAIM_ID)).toBeTruthy()
  } finally {
    await financeContext.close()
  }
})
