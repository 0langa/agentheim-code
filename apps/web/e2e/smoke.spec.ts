import { test, expect } from "@playwright/test";

test.describe("Agentheim Code Web", () => {
  test("homepage loads", async ({ page }) => {
    await page.goto("/");
    // The app should render at minimum the shell layout
    await expect(page.locator("main.shell")).toBeVisible();
  });

  test("rail navigation is visible", async ({ page }) => {
    await page.goto("/");
    const rail = page.locator("nav.rail");
    await expect(rail).toBeVisible();
  });
});
