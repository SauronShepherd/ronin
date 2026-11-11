import { test, expect } from '@playwright/test';

test('command palette prioritizes locally recent Studios without storing credentials', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('ronin.recent-commands', JSON.stringify(['quality', 'sql']));
    localStorage.setItem('ronin.server-token', 'must-not-be-read');
  });
  await page.goto('./#home', { waitUntil: 'load' });
  await page.locator('[data-action="open-command"]').click();

  const options = page.locator('.command-option');
  await expect(options.first()).toHaveAttribute('data-command-route', 'quality');
  await expect(options.nth(1)).toHaveAttribute('data-command-route', 'sql');

  await options.first().click();
  await expect(page).toHaveURL(/#quality$/);
  expect(await page.evaluate(() => localStorage.getItem('ronin.recent-commands'))).toBe('["quality","sql"]');
  expect(await page.evaluate(() => localStorage.getItem('ronin.server-token'))).toBe('must-not-be-read');
});
