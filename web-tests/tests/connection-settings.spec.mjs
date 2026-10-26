import { test, expect } from '@playwright/test';

test('API connection is understandable, persistent by scope, removable and usable on mobile', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('./');

  const form = page.locator('#connection-form');
  for (const width of [320, 390, 520, 768, 900, 901, 1024]) {
    await page.setViewportSize({ width, height: 900 });
    await expect(form).toBeVisible();
    const formBounds = await form.boundingBox();
    const buttonBounds = await form.getByRole('button', { name: 'Save connection' }).boundingBox();
    expect(formBounds).not.toBeNull();
    expect(buttonBounds).not.toBeNull();
    expect(formBounds.x + formBounds.width).toBeLessThanOrEqual(width);
    expect(buttonBounds.x + buttonBounds.width).toBeLessThanOrEqual(width);
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(form.getByLabel('Ronin API server URL')).toHaveAttribute('placeholder', 'API server URL (optional)');
  await expect(page.locator('.connection-help summary[aria-label="Explain the API connection"]')).toBeVisible();
  await page.locator('.connection-help summary').click();
  await expect(page.locator('.connection-help')).toContainText('token supplied by your Ronin administrator');
  await expect(page.locator('.connection-help')).toContainText('trusted HTTPS server');

  await page.locator('#api-url').fill('https://ronin.example/control/');
  await page.locator('#api-token').fill('session-secret');
  await form.getByRole('button', { name: 'Save connection' }).click();
  await expect(page.locator('#api-token')).toHaveValue('');
  expect(await page.evaluate(() => localStorage.getItem('ronin.api'))).toBe('https://ronin.example/control');
  expect(await page.evaluate(() => sessionStorage.getItem('ronin.session'))).toBe('session-secret');

  await page.locator('#api-token').fill('');
  await form.getByRole('button', { name: 'Save connection' }).click();
  expect(await page.evaluate(() => sessionStorage.getItem('ronin.session'))).toBeNull();
  expect(await page.evaluate(() => localStorage.getItem('ronin.api'))).toBe('https://ronin.example/control');

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('./#settings');
  await expect(page.locator('#settings-api-url')).toHaveValue('https://ronin.example/control');
  await page.locator('#settings-api-url').fill('');
  await page.locator('#settings-form').getByRole('button', { name: 'Save settings' }).click();
  expect(await page.evaluate(() => localStorage.getItem('ronin.api'))).toBeNull();

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('./');
  await expect(form).toBeVisible();
  const bounds = await form.boundingBox();
  expect(bounds).not.toBeNull();
  expect(bounds.x + bounds.width).toBeLessThanOrEqual(390);
  expect(await page.evaluate(() => document.querySelector('#main').scrollWidth <= document.querySelector('#main').clientWidth)).toBe(true);
});

test('invalid API URL does not replace the active connection or token', async ({ page }) => {
  await page.goto('./');
  await page.evaluate(() => {
    localStorage.setItem('ronin.api', 'https://existing.example');
    sessionStorage.setItem('ronin.session', 'existing-secret');
  });
  await page.reload();
  await page.locator('#api-url').fill('https://user:password@untrusted.example');
  await page.locator('#api-token').fill('replacement-secret');
  await page.locator('#connection-form').getByRole('button', { name: 'Save connection' }).click();
  await expect(page.locator('#toast')).toContainText('cannot contain credentials');
  expect(await page.evaluate(() => localStorage.getItem('ronin.api'))).toBe('https://existing.example');
  expect(await page.evaluate(() => sessionStorage.getItem('ronin.session'))).toBe('existing-secret');
});

test('legacy API URL migrates to persistent storage and invalid saved URL clears its token', async ({ page }) => {
  await page.goto('./');
  await page.evaluate(() => sessionStorage.setItem('ronin.api', 'https://legacy.example/'));
  await page.reload();
  expect(await page.evaluate(() => localStorage.getItem('ronin.api'))).toBe('https://legacy.example');
  expect(await page.evaluate(() => sessionStorage.getItem('ronin.api'))).toBeNull();
  await expect(page.locator('#api-url')).toHaveValue('https://legacy.example');

  await page.evaluate(() => {
    localStorage.setItem('ronin.api', 'javascript:alert(1)');
    sessionStorage.setItem('ronin.session', 'token-for-old-server');
  });
  await page.reload();
  await expect(page.locator('#breadcrumb')).toHaveText('Overview');
  expect(await page.evaluate(() => localStorage.getItem('ronin.api'))).toBeNull();
  expect(await page.evaluate(() => sessionStorage.getItem('ronin.session'))).toBeNull();
  await expect(page.locator('#api-url')).toHaveValue('');
});
