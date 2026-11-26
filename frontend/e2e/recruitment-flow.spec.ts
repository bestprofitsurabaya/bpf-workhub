import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

// E2E selalu menuju Flask lokal + MariaDB uji (lihat playwright.config.ts).
// NIK uji tidak pernah dipakai di produksi dan dibersihkan di afterAll.
const NIK = ['3573019900000001', '3573019900000002', '3573019900000003']
const BRANCH_TOKEN = 'tok-e2e-sby'
const BRANCH = 'SBY'
const PIN = '123456'

async function apiOk(request: APIRequestContext, path: string, options = {}) {
  const response = await request.get(path, options)
  expect(response.ok(), `${path} → ${response.status()}`).toBeTruthy()
  return response.json()
}

async function login(page: Page, username: string) {
  await page.goto('/login')
  await page.addInitScript(() => localStorage.clear())
  await page.getByPlaceholder('Masukkan username').fill(username)
  await page.locator('input[type=password]').fill(PIN)
  await page.getByRole('button', { name: /Masuk/ }).click()
  await expect(page).not.toHaveURL(/\/login/)
}

// Seed/pembersihan data uji dilakukan scripts/ci_e2e.sh langsung pada DB uji.
// Spesifikasi ini sengaja hanya memakai endpoint publik yang sama dengan
// aplikasi produksi — tidak ada endpoint khusus E2E di server.

test('resepsionis melihat data rekrutment berbasis NIK', async ({ page, request }) => {
  await login(page, 'resepsionis_sby')
  await page.goto('/app/recruitment?tab=pelamar')
  await expect(page.locator('[data-tab="pelamar"]')).toHaveAttribute('data-active', 'true')
  await expect(page.getByRole('heading', { name: 'Data Rekrutment' })).toBeVisible()
  await apiOk(request, '/api/recruitment/people', {
    params: { q: NIK[0] },
  })
})

test('portal cek NIK → CV → FirstWork → kartu PDF', async ({ page, request }) => {
  await page.goto(`/app/recruitment-portal?token=${BRANCH_TOKEN}`)
  await page.locator('#rp-nik').fill(NIK[1])
  await page.locator('form.rp-check button').click()
  await expect(page.getByText(/Langkah berikutnya/)).toBeVisible()
  const summary = await apiOk(request, '/api/recruitment/lookup', {
    params: { nik: NIK[1], token: BRANCH_TOKEN },
  })
  expect(summary.session_token).toBeTruthy()

  const card = await request.get('/api/recruitment/portal/summary', {
    params: { token: summary.session_token },
  })
  expect(card.ok()).toBeTruthy()
  const data = (await card.json()).data
  expect(data.nama_masked).toBeTruthy()
  expect(NIK[1]).not.toContain(data.nama_masked)
  expect(data.stages.map((s: any) => s.type)).toEqual(
    ['CV', 'TRAINING', 'TKD', 'FIRSTWORK'])

  // Unduhan kartu hanya lewat token purpose=card, bukan token portal.
  const csv = await request.get('/api/recruitment/people', {
    params: { q: NIK[1], view: 'firstwork' },
  })
  expect(csv.ok()).toBeTruthy()
})

test('pelamar lama tanpa NIK ditautkan ke kasus yang sama', async ({ request }) => {
  // Baris lama tanpa NIK sudah di-seed ci_e2e.sh dan ditautkan lewat task C12.
  const before = await apiOk(request, '/api/recruitment/lookup', {
    params: { nik: NIK[2], token: BRANCH_TOKEN },
  })
  expect(before.known).toBe(true)
  const after = await apiOk(request, '/api/recruitment/lookup', {
    params: { nik: NIK[2], token: BRANCH_TOKEN },
  })
  expect(after.session_token).toBeTruthy()
  expect(before.known).toBe(after.known)
})
