import { test, expect } from '@playwright/test';
import routes from '../../web/routes.json' with { type: 'json' };

test('server settings explain defaults and update or remove the access key', async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('ronin.session', 'previous-secret');
    sessionStorage.setItem('ronin.api', location.origin);
  });
  await page.goto('./#home', { waitUntil: 'load' });
  await page.getByRole('button', { name: 'Server connection' }).click();

  await expect(page.getByRole('heading', { name: 'Where does Ronin run?' })).toBeVisible();
  await expect(page.getByText(/They normally connect automatically/)).toBeVisible();
  await expect(page.locator('#api-url')).toHaveValue('');
  await expect(page.locator('#api-token-help')).toContainText('key already saved for this tab');

  await page.locator('#api-url').fill('https://ronin.example.test/base///');
  await page.locator('#api-token').fill('new-secret');
  await page.getByRole('button', { name: 'Save connection' }).click();
  await expect(page.locator('#toast')).toContainText('Server settings saved');
  await expect.poll(() => page.evaluate(() => localStorage.getItem('ronin.api'))).toBe('https://ronin.example.test/base');
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem('ronin.api'))).toBeNull();
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem('ronin.session'))).toBe('new-secret');

  await page.getByRole('button', { name: 'Server connection' }).click();
  await expect(page.locator('#api-token')).toHaveValue('');
  await page.locator('#api-token-clear').check();
  await page.getByRole('button', { name: 'Save connection' }).click();
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem('ronin.session'))).toBeNull();
  await expect(page.locator('body')).not.toContainText('previous-secret');
});

test('server settings never send an access key to a remote HTTP server', async ({ page }) => {
  await page.goto('./#home', { waitUntil: 'load' });
  await page.getByRole('button', { name: 'Server connection' }).click();
  await page.locator('#api-url').fill('http://ronin.example.test');
  await page.locator('#api-token').fill('must-not-leave-the-browser');
  await page.getByRole('button', { name: 'Save connection' }).click();

  await expect(page.locator('#connection-dialog')).toBeVisible();
  await expect(page.getByRole('alert')).toContainText('Access keys require HTTPS');
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem('ronin.session'))).toBeNull();
});

test('navigation groups every route and the paw toggle keeps icons visible', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto('./#home', { waitUntil: 'load' });
  await expect(page.locator('#rail .nav-item')).toHaveCount(routes.length);
  await expect(page.locator('#rail .nav-section')).toHaveCount(7);
  await expect(page.locator('#rail')).not.toContainText('Control plane');

  const paw = page.locator('.rail-toggle-icon svg');
  await expect(paw).toBeVisible();
  const vertical = await paw.evaluate(element => getComputedStyle(element).transform);
  expect(vertical).toBe('matrix(1, 0, 0, 1, 0, 0)');
  await page.getByRole('button', { name: 'Collapse navigation' }).click();
  await expect(page.locator('#app')).toHaveClass(/sidebar-collapsed/);
  await expect(page.locator('#rail .nav-section-title:visible')).toHaveCount(0);
  await expect(page.locator('#rail .nav-icon svg:visible')).toHaveCount(routes.length);
  const rotated = await paw.evaluate(element => getComputedStyle(element).transform);
  expect(rotated).toBe('matrix(0, 1, -1, 0, 0, 0)');

  await page.getByRole('button', { name: 'Expand navigation' }).click();
  await expect(page.locator('#app')).not.toHaveClass(/sidebar-collapsed/);
  await expect(page.locator('#rail .nav-section-title:visible')).toHaveCount(7);
});
