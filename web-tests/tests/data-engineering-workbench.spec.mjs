import { test, expect } from '@playwright/test';

test('Data Engineering Studio presents a mode-based workbench and keeps it usable on phone', async ({ page }) => {
  await page.goto('./#data');

  await expect(page.locator('.de-hero h2')).toHaveText('Shape, query and ship data with evidence attached.');
  await expect(page.locator('.de-mode-card')).toHaveCount(3);
  await expect(page.locator('.de-mode-card').nth(0)).toContainText('Query');
  await expect(page.locator('.de-mode-card').nth(1)).toContainText('Compose');
  await expect(page.locator('.de-mode-card').nth(2)).toContainText('Observe');
  await expect(page.locator('#de-sql-workbench')).toContainText('read-only · bounded · exportable');
  await expect(page.locator('#de-pipeline-workbench')).toContainText('versioned · reviewable · reversible');
  await expect(page.locator('#de-ops-workbench')).toContainText('Know the operating boundary');

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator('.de-hero')).toBeVisible();
  await expect(page.locator('#de-sql-form')).toBeVisible();
  await expect(page.locator('#de-pipeline-form')).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
  expect(overflow).toBe(false);
});
