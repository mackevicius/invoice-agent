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
  const roleSwitch = sidebar.getByRole('group', { name: 'Viewing as' });
  await expect(roleSwitch.getByRole('button')).toHaveCount(3);
  await expect(
    roleSwitch.getByRole('button', { name: 'Submitter', exact: true }),
  ).toHaveAttribute('aria-pressed', 'true');
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

test('a Submitter uploads an unknown Supplier Invoice and a Reviewer approves it', async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');

  const sidebar = page.getByRole('complementary', { name: 'Invoices' });
  const detail = page.getByRole('main', { name: 'Invoice details' });
  await expect(sidebar.getByRole('button', { name: /INV-1042/ })).toBeVisible();

  const roleSwitch = sidebar.getByRole('group', { name: 'Viewing as' });
  await expect(
    roleSwitch.getByRole('button', { name: 'Submitter', exact: true }),
  ).toHaveAttribute('aria-pressed', 'true');
  await expect(sidebar.getByRole('tab', { name: /^Mine\b/ })).toHaveAttribute(
    'aria-selected',
    'true',
  );

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
  expect(uploaded.submitted_by).toBe('submitter');

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
  await expect(
    detail.getByRole('button', { name: 'Approve', exact: true }),
  ).toHaveCount(0);

  await roleSwitch
    .getByRole('button', { name: 'Reviewer', exact: true })
    .click();
  await expect(
    sidebar.getByRole('tab', { name: /^Review Queue\b/ }),
  ).toHaveAttribute('aria-selected', 'true');
  await sidebar.getByRole('button', { name: /INV-2026-42/ }).click();
  const approval = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/invoices/${uploaded.id}/approve`) &&
      response.request().method() === 'POST',
  );
  await detail.getByRole('button', { name: 'Approve', exact: true }).click();

  expect((await approval).status()).toBe(200);
  await expect(detail.getByText('Approved', { exact: true })).toBeVisible();
  await expect(
    sidebar.getByRole('button', { name: /INV-2026-42/ }),
  ).toHaveCount(0);
  await expect(sidebar.getByRole('tab', { name: /^Done\b/ })).toContainText(
    '4',
  );
  expect(
    await page.evaluate(
      () =>
        document.documentElement.scrollWidth >
        document.documentElement.clientWidth,
    ),
  ).toBe(false);
  expect(errors).toEqual([]);
  await page.screenshot({
    path: testInfo.outputPath('approved-invoice.png'),
    fullPage: true,
  });
});

test('Three-Way Match shows mismatches, savings, and every reason', async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  const lines = [
    {
      item_code: null,
      description: 'A4 recycled paper in boxes',
      quantity: '30',
      unit_price: '120.00',
    },
    {
      item_code: 'PAPER-A3',
      description: 'Recycled A3 paper, box',
      quantity: '6',
      unit_price: '100.00',
    },
  ];
  const purchaseLineId = '00000000-0000-4000-8000-000000000001';
  const otherPurchaseLineId = '00000000-0000-4000-8000-000000000002';
  const reasons = [
    'Line 1 (A4 recycled paper in boxes): unit price is more than 2% above the Purchase Order.',
    'Line 1 (A4 recycled paper in boxes): invoiced quantity does not equal received quantity.',
  ];
  await page.route('**/api/invoices/*', async (route) => {
    const response = await route.fetch();
    const original = await response.json();
    await route.fulfill({
      response,
      json: {
        ...original,
        invoice_number: 'INV-MATCH-42',
        supplier: 'Paper & Co.',
        total: '4200.00',
        status: 'In Review',
        fields: {
          supplier_name: 'Paper & Co.',
          invoice_number: 'INV-MATCH-42',
          purchase_order_number: 'PO-1002',
          issued_on: '2026-10-20',
          currency: 'EUR',
          lines,
          subtotal: '4200.00',
          tax: '0.00',
          total: '4200.00',
        },
        comparison: [
          {
            line_number: 1,
            invoice: lines[0],
            purchase_order: {
              id: purchaseLineId,
              item_code: 'PAPER-A4',
              description: 'Recycled A4 paper, box',
              quantity: '24',
              unit_price: '111.60',
            },
            goods_receipt: {
              purchase_order_line_id: purchaseLineId,
              quantity: '24',
            },
            paired_by: 'meaning',
            unit_price_difference: '8.40',
            unit_price_difference_percent: '7.53',
            price_passed: false,
            quantity_passed: false,
            mismatched_cells: [
              'invoice.unit_price',
              'purchase_order.unit_price',
              'invoice.quantity',
              'goods_receipt.quantity',
            ],
            reasons,
          },
          {
            line_number: 2,
            invoice: lines[1],
            purchase_order: {
              id: otherPurchaseLineId,
              item_code: 'PAPER-A3',
              description: 'Recycled A3 paper, box',
              quantity: '24',
              unit_price: '111.60',
            },
            goods_receipt: {
              purchase_order_line_id: otherPurchaseLineId,
              quantity: '6',
            },
            paired_by: 'item_code',
            unit_price_difference: '-11.60',
            unit_price_difference_percent: '-10.39',
            price_passed: true,
            quantity_passed: true,
            mismatched_cells: [],
            reasons: [],
          },
        ],
        reasons,
      },
    });
  });

  await page.goto('/');

  const detail = page.getByRole('main', { name: 'Invoice details' });
  const comparison = detail.getByRole('region', { name: 'Three-Way Match' });
  await expect(comparison).toBeVisible();
  await expect(comparison.getByText('PO-1002', { exact: true })).toBeVisible();
  const firstLine = comparison.getByRole('table', {
    name: 'Line 1 comparison',
  });
  const secondLine = comparison.getByRole('table', {
    name: 'Line 2 comparison',
  });
  await expect(firstLine).toBeVisible();
  await expect(secondLine).toBeVisible();
  const descriptions = firstLine.getByRole('row', { name: /^Item / });
  await expect(descriptions.getByRole('cell').nth(0)).toHaveText(
    'A4 recycled paper in boxes',
  );
  await expect(descriptions.getByRole('cell').nth(1)).toContainText(
    'Recycled A4 paper, box',
  );
  const price = firstLine.getByRole('row', { name: /^Unit price/ });
  await expect(price.getByRole('cell').nth(0)).toHaveAttribute(
    'data-mismatch',
    'true',
  );
  await expect(price.getByRole('cell').nth(0)).toHaveCSS(
    'color',
    'rgb(154, 60, 54)',
  );
  const quantities = firstLine.getByRole('row', { name: /^Quantity/ });
  await expect(quantities.getByRole('cell').nth(0)).toHaveAttribute(
    'data-mismatch',
    'true',
  );
  await expect(secondLine.locator('[data-mismatch="true"]')).toHaveCount(0);
  await expect(secondLine.getByText(/-.*11\.60/)).toBeVisible();
  await expect(secondLine.getByText('-10.39%')).toBeVisible();
  const review = detail.getByRole('region', { name: 'Review reasons' });
  await expect(review.getByRole('listitem')).toHaveText(reasons);
  const lastTableBounds = await secondLine.boundingBox();
  const reasonBounds = await review.boundingBox();
  if (lastTableBounds === null || reasonBounds === null) {
    throw new Error(
      'The comparison grid and review reasons must both be visible.',
    );
  }
  expect(reasonBounds.y).toBeGreaterThanOrEqual(
    lastTableBounds.y + lastTableBounds.height,
  );
  const layout = await page.evaluate(() => ({
    page: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));
  expect(layout.page, JSON.stringify(layout)).toBeLessThanOrEqual(
    layout.viewport,
  );
  expect(errors).toEqual([]);
  await firstLine.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: testInfo.outputPath('three-way-match.png'),
    fullPage: true,
  });
});

test('duplicate reasons link to each earlier Invoice', async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');

  const sidebar = page.getByRole('complementary', { name: 'Invoices' });
  const detail = page.getByRole('main', { name: 'Invoice details' });
  await expect(detail.getByRole('heading', { name: 'INV-1042' })).toBeVisible();
  const response = await page.request.get('/api/invoices?view=all');
  expect(response.ok()).toBe(true);
  const invoices: { id: string; invoice_number: string }[] =
    await response.json();
  const current = invoices.find(
    (invoice) => invoice.invoice_number === 'INV-1042',
  );
  const exact = invoices.find(
    (invoice) => invoice.invoice_number === 'INV-0309',
  );
  const possible = invoices.find(
    (invoice) => invoice.invoice_number === 'INV-0781',
  );
  if (!current || !exact || !possible) {
    throw new Error('The Demo Company must contain the sample Invoices.');
  }
  const matchReason = 'No Purchase Order is named on this Invoice.';
  const duplicates = [
    {
      invoice_id: exact.id,
      invoice_number: exact.invoice_number,
      reason: 'Duplicate Invoice: INV-0309 was already received.',
    },
    {
      invoice_id: possible.id,
      invoice_number: possible.invoice_number,
      reason:
        'Possible Duplicate: INV-0781 has the same total and was received within 30 days.',
    },
  ];
  await page.route(`**/api/invoices/${current.id}`, async (route) => {
    const originalResponse = await route.fetch();
    const original = await originalResponse.json();
    await route.fulfill({
      response: originalResponse,
      json: {
        ...original,
        status: 'In Review',
        reasons: [
          matchReason,
          ...duplicates.map((duplicate) => duplicate.reason),
        ],
        steps: [
          {
            name: 'Check Duplicates',
            status: 'Completed',
            inputs: {},
            outputs: { duplicates },
            started_at: '2026-10-30T12:00:00Z',
            completed_at: '2026-10-30T12:00:01Z',
          },
        ],
      },
    });
  });
  await page.reload();
  const roleSwitch = sidebar.getByRole('group', { name: 'Viewing as' });
  await roleSwitch.getByRole('button', { name: 'Admin', exact: true }).click();

  const review = detail.getByRole('region', { name: 'Review reasons' });
  await expect(review.getByRole('listitem')).toHaveText([
    matchReason,
    ...duplicates.map((duplicate) => duplicate.reason),
  ]);
  await expect(review.getByRole('link')).toHaveCount(2);
  const exactLink = review.getByRole('link', { name: duplicates[0].reason });
  await expect(exactLink).toHaveAttribute('href', `?invoice=${exact.id}`);
  await expect(
    review.getByRole('link', { name: duplicates[1].reason }),
  ).toHaveAttribute('href', `?invoice=${possible.id}`);
  await review.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: testInfo.outputPath('duplicate-reasons.png'),
    fullPage: true,
  });

  await exactLink.click();

  await expect(detail.getByRole('heading', { name: 'INV-0309' })).toBeVisible();
  await expect(
    roleSwitch.getByRole('button', { name: 'Admin', exact: true }),
  ).toHaveAttribute('aria-pressed', 'true');
  await page.goto(`/?invoice=${possible.id}`);
  await expect(detail.getByRole('heading', { name: 'INV-0781' })).toBeVisible();
  expect(
    await page.evaluate(
      () =>
        document.documentElement.scrollWidth >
        document.documentElement.clientWidth,
    ),
  ).toBe(false);
  expect(errors).toEqual([]);
});
