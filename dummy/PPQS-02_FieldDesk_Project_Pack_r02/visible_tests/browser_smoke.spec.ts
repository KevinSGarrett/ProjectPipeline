
import { test, expect } from '@playwright/test';

test('dashboard has accessible shell', async ({ page }) => {
  await page.goto(process.env.FIELDDESK_WEB_URL ?? 'http://127.0.0.1:3000');
  await expect(page.getByRole('heading', { name: /fielddesk/i })).toBeVisible();
  await expect(page.getByRole('navigation')).toBeVisible();
});
