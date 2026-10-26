import { expect, test } from '@playwright/test';

test('a visitor whose Demo Company expired starts a new one', async ({
  page,
  context,
}) => {
  await page.goto('/');

  const sidebar = page.getByRole('complementary', { name: 'Invoices' });
  await expect(sidebar.getByRole('button', { name: /INV-1042/ })).toBeVisible();
  const expired = (await context.cookies()).find(
    (cookie) => cookie.name === 'demo_company',
  );

  await context.clearCookies({ name: 'demo_company' });
  await page.getByRole('button', { name: 'Refresh Invoices' }).click();

  const alert = page
    .getByRole('main', { name: 'Invoice details' })
    .getByRole('alert');
  await expect(alert).toContainText('This Demo Company has expired.');
  await alert.getByRole('button', { name: 'Start a new Demo Company' }).click();

  await expect(sidebar.getByRole('button', { name: /INV-1042/ })).toBeVisible();
  await expect(alert).toBeHidden();
  const started = (await context.cookies()).find(
    (cookie) => cookie.name === 'demo_company',
  );
  expect(started?.value).toBeTruthy();
  expect(started?.value).not.toBe(expired?.value);
});
