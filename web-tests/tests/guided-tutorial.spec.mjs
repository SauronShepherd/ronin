import { expect, test } from '@playwright/test';

test('mobile tour keeps the highlighted Ronin avatar visible above its dialog', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('./#home');
  await page.getByRole('button', { name: /Start the Ronin tour/ }).first().click();

  const target = page.locator('.tutorial-hero-art');
  const dialog = page.locator('.tutorial-dialog');
  await expect(dialog).toBeVisible();
  await expect(page.locator('#tutorial-step-counter')).toContainText('STEP 1 OF 10');

  const boxes = await Promise.all([target.boundingBox(), dialog.boundingBox()]);
  expect(boxes[0]).not.toBeNull();
  expect(boxes[1]).not.toBeNull();
  expect(boxes[1].y).toBeGreaterThanOrEqual(boxes[0].y + boxes[0].height);
  expect(boxes[1].x).toBeGreaterThanOrEqual(0);
  expect(boxes[1].x + boxes[1].width).toBeLessThanOrEqual(390);
  expect(boxes[1].y + boxes[1].height).toBeLessThanOrEqual(844);
});

test('tour can be exited with Escape and restores focus to its launch control', async ({ page }) => {
  await page.goto('./#home');
  const start = page.getByRole('button', { name: /Start the Ronin tour/ }).first();
  await start.click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toBeHidden();
  await expect(start).toBeFocused();
});

test('finishing the complete tour offers a related tutorial that can be started', async ({ page }) => {
  await page.goto('./#home');
  await page.getByRole('button', { name: /Start the Ronin tour/ }).first().click();
  const next = page.locator('[data-tutorial-next]');

  for (let step = 1; step < 10; step += 1) {
    await next.click();
    await expect(page.locator('#tutorial-step-counter')).toContainText(`STEP ${step + 1} OF 10`);
  }
  await next.click();

  await expect(page.locator('#tutorial-step-counter')).toHaveText('TRAIL COMPLETE');
  await expect(page.locator('#tutorial-recommendations')).toBeVisible();
  const recommendation = page.locator('#tutorial-recommendations [data-tutorial-start]').first();
  await recommendation.click();
  await expect(page.locator('#tutorial-step-counter')).toContainText('STEP 1 OF');
});
