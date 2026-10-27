import { expect, test } from '@playwright/test';

test('a visitor selects an Invoice and returns to the same Demo Company', async ({
  page,
  context,
  isMobile,
}, testInfo) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));

  await page.goto('/');

  const sidebar = page.getByRole('complementary', { name: 'Invoices' });
  const detail = page.getByRole('main', { name: 'Invoice details' });
  await expect(sidebar.getByRole('button', { name: /INV-1042/ })).toBeVisible();
  await expect(detail.getByRole('heading', { name: 'INV-1042' })).toBeVisible();

  const session = (await context.cookies()).find(
    (cookie) => cookie.name === 'demo_company',
  );
  expect(session?.value).toBeTruthy();
  expect(session?.httpOnly).toBe(true);

  await sidebar.getByRole('button', { name: /INV-0309/ }).click();

  await expect(detail.getByRole('heading', { name: 'INV-0309' })).toBeVisible();
  await expect(detail.getByText('Paper & Co.', { exact: true })).toBeVisible();
  await expect(detail.getByLabel('Invoice total')).toContainText('2,678.40');
  await expect(detail.getByText('In Review', { exact: true })).toBeVisible();

  await page.reload();

  await expect(detail.getByRole('heading', { name: 'INV-1042' })).toBeVisible();
  expect(
    (await context.cookies()).find((cookie) => cookie.name === 'demo_company')
      ?.value,
  ).toBe(session?.value);
  expect(
    await page.evaluate(
      () =>
        document.documentElement.scrollWidth >
        document.documentElement.clientWidth,
    ),
  ).toBe(false);
  expect(errors).toEqual([]);

  const sidebarBounds = await sidebar.boundingBox();
  const detailBounds = await detail.boundingBox();
  if (sidebarBounds === null || detailBounds === null) {
    throw new Error('The Invoice list and detail pane must both be visible.');
  }
  if (isMobile) {
    expect(Math.round(detailBounds.y)).toBeGreaterThanOrEqual(
      Math.round(sidebarBounds.y + sidebarBounds.height),
    );
  } else {
    expect(Math.round(detailBounds.x)).toBeGreaterThanOrEqual(
      Math.round(sidebarBounds.x + sidebarBounds.width),
    );
  }
  await page.screenshot({
    path: testInfo.outputPath('split-view.png'),
    fullPage: true,
  });
});

test('a visitor uploads an Invoice and watches an unknown Supplier stop the run', async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');

  const sidebar = page.getByRole('complementary', { name: 'Invoices' });
  const detail = page.getByRole('main', { name: 'Invoice details' });
  await expect(sidebar.getByRole('button', { name: /INV-1042/ })).toBeVisible();

  await sidebar.getByRole('button', { name: 'Upload Invoice' }).click();
  await expect(
    detail.getByRole('heading', { name: 'Upload Invoice' }),
  ).toBeVisible();
  await detail.getByLabel('Invoice file').setInputFiles({
    name: 'invoice.png',
    mimeType: 'image/png',
    buffer: Buffer.from(
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8' +
        '/x8AAwMCAO+jRZkAAAAASUVORK5CYII=',
      'base64',
    ),
  });

  const uploadedResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith('/api/invoices') &&
      response.request().method() === 'POST',
  );
  await detail
    .getByRole('button', { name: 'Upload Invoice', exact: true })
    .click();
  const response = await uploadedResponse;
  expect(response.status()).toBe(202);
  const uploaded = await response.json();
  expect(uploaded.status).toBe('Processing');
  expect(uploaded.steps[0].status).toBe('Pending');

  await expect(
    detail.getByRole('heading', { name: 'INV-2026-42' }),
  ).toBeVisible();
  await expect(
    detail.getByText('Baltic Office Supplies', { exact: true }),
  ).toBeVisible();
  const steps = detail.getByRole('list', { name: 'Agent steps' });
  const readStep = steps
    .getByRole('listitem')
    .filter({ hasText: 'Read Invoice' });
  await expect(readStep.getByText('Completed', { exact: true })).toBeVisible();
  const supplierStep = steps
    .getByRole('listitem')
    .filter({ hasText: 'Find Supplier' });
  await expect(
    supplierStep.getByText('Completed', { exact: true }),
  ).toBeVisible();
  await expect(steps.getByRole('listitem')).toHaveCount(8);
  await expect(steps.getByText('Skipped', { exact: true })).toHaveCount(6);
  await expect(
    detail.getByRole('region', { name: 'Review reasons' }),
  ).toHaveText('Review reasonsUnknown Supplier');
  await expect(
    detail.getByRole('cell', { name: 'Printer paper' }),
  ).toBeVisible();
  await expect(detail.getByLabel('Invoice total')).toContainText('45.38');
  await expect(detail.getByText('In Review', { exact: true })).toBeVisible();
  await expect(
    sidebar.getByRole('button', { name: /INV-2026-42/ }),
  ).toHaveAttribute('aria-pressed', 'true');
  expect(
    await page.evaluate(
      () =>
        document.documentElement.scrollWidth >
        document.documentElement.clientWidth,
    ),
  ).toBe(false);
  expect(errors).toEqual([]);
  await page.screenshot({
    path: testInfo.outputPath('uploaded-invoice.png'),
    fullPage: true,
  });
});
