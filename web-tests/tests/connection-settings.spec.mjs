import { test, expect } from '@playwright/test';

test('server connection dialog stays usable across viewport sizes and preserves its configured address', async ({ page }) => {
  await page.goto('./#home');
  const open = page.getByRole('button', { name: 'Server connection' });
  for (const width of [320, 390, 520, 768, 900, 1024, 1440]) {
    await page.setViewportSize({ width, height: 844 });
    await expect(open).toBeVisible();
    const bounds = await open.boundingBox();
    expect(bounds).not.toBeNull();
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
  }
  await open.click();
  const dialog = page.locator('#connection-dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText('Most people do not need to change anything');
  await expect(dialog).toContainText('Only enter a different address if your administrator gave you one');
  const formBounds = await page.locator('#connection-form').boundingBox();
  expect(formBounds).not.toBeNull();
  expect(formBounds.x + formBounds.width).toBeLessThanOrEqual(1440);

  await page.locator('#api-url').fill('https://ronin.example/control/');
  await page.locator('#api-token').fill('session-secret');
  await page.getByRole('button', { name: 'Save connection' }).click();
  await expect(page.locator('#toast')).toContainText('Server settings saved');
  expect(await page.evaluate(() => localStorage.getItem('ronin.api'))).toBe('https://ronin.example/control');
  expect(await page.evaluate(() => sessionStorage.getItem('ronin.session'))).toBe('session-secret');

  await open.click();
  await expect(page.locator('#api-url')).toHaveValue('https://ronin.example/control');
  await expect(page.locator('#api-token')).toHaveValue('');
  await page.locator('#api-token-clear').check();
  await page.getByRole('button', { name: 'Save connection' }).click();
  expect(await page.evaluate(() => sessionStorage.getItem('ronin.session'))).toBeNull();
  expect(await page.evaluate(() => localStorage.getItem('ronin.api'))).toBe('https://ronin.example/control');

  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
});

test('invalid and insecure server addresses do not replace the active connection or key', async ({ page }) => {
  await page.goto('./');
  await page.evaluate(() => {
    localStorage.setItem('ronin.api', 'https://existing.example');
    sessionStorage.setItem('ronin.session', 'existing-secret');
  });
  await page.reload();
  await page.getByRole('button', { name: 'Server connection' }).click();
  await page.locator('#api-url').fill('https://user:password@untrusted.example');
  await page.locator('#api-token').fill('replacement-secret');
  await page.getByRole('button', { name: 'Save connection' }).click();
  await expect(page.getByRole('alert')).toContainText('without a username, password');
  expect(await page.evaluate(() => localStorage.getItem('ronin.api'))).toBe('https://existing.example');
  expect(await page.evaluate(() => sessionStorage.getItem('ronin.session'))).toBe('existing-secret');

  await page.locator('#api-url').fill('http://remote.example');
  await page.getByRole('button', { name: 'Save connection' }).click();
  await expect(page.getByRole('alert')).toContainText('Access keys require HTTPS');
  expect(await page.evaluate(() => localStorage.getItem('ronin.api'))).toBe('https://existing.example');
  expect(await page.evaluate(() => sessionStorage.getItem('ronin.session'))).toBe('existing-secret');
});
