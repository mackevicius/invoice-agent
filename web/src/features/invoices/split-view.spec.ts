import { expect, test } from "@playwright/test";

test("a visitor selects an Invoice and returns to the same Demo Company", async ({
  page,
  context,
  isMobile,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));

  await page.goto("/");

  const sidebar = page.getByRole("complementary", { name: "Invoices" });
  const detail = page.getByRole("main", { name: "Invoice details" });
  await expect(sidebar.getByRole("button", { name: /INV-1042/ })).toBeVisible();
  await expect(detail.getByRole("heading", { name: "INV-1042" })).toBeVisible();

  const session = (await context.cookies()).find(
    (cookie) => cookie.name === "demo_company",
  );
  expect(session?.value).toBeTruthy();
  expect(session?.httpOnly).toBe(true);

  await sidebar.getByRole("button", { name: /INV-0309/ }).click();

  await expect(detail.getByRole("heading", { name: "INV-0309" })).toBeVisible();
  await expect(detail.getByText("Paper & Co.", { exact: true })).toBeVisible();
  await expect(detail.getByLabel("Invoice total")).toContainText("2,678.40");
  await expect(detail.getByText("In Review", { exact: true })).toBeVisible();

  await page.reload();

  await expect(detail.getByRole("heading", { name: "INV-1042" })).toBeVisible();
  expect(
    (await context.cookies()).find((cookie) => cookie.name === "demo_company")
      ?.value,
  ).toBe(session?.value);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
    ),
  ).toBe(false);
  expect(errors).toEqual([]);

  const sidebarBounds = await sidebar.boundingBox();
  const detailBounds = await detail.boundingBox();
  if (sidebarBounds === null || detailBounds === null) {
    throw new Error("The Invoice list and detail pane must both be visible.");
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
  await page.screenshot({ path: testInfo.outputPath("split-view.png"), fullPage: true });
});
