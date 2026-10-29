// End-to-end journey through the real UI against a running backend that serves the build.
// Usage: BASE_URL=http://127.0.0.1:8000 RET_PASSWORD=... SHOTS=/tmp/shots node e2e/smoke.mjs
import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { chromium, expect } from "playwright/test";

const BASE = process.env.BASE_URL ?? "http://127.0.0.1:8000";
const PASSWORD = process.env.RET_PASSWORD;
const SHOTS = process.env.SHOTS ?? "e2e/shots";
const fixture = (n) => fileURLToPath(new URL(`./fixtures/${n}`, import.meta.url));
if (!PASSWORD) throw new Error("Set RET_PASSWORD to the admin password.");
mkdirSync(SHOTS, { recursive: true });

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, acceptDownloads: true });
const page = await ctx.newPage();
const problems = [];
// Browsers echo every 4xx as a console error; HTTP failures are tracked (and filtered) below.
page.on("console", (m) => m.type() === "error" && !/status of 4\d\d/.test(m.text()) && problems.push(`console: ${m.text()}`));
page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
page.on("response", (r) => {
  // 401 on the session probe and the deliberate bad login are expected.
  if (r.status() >= 400 && !(r.status() === 401 && /auth\/(me|login)/.test(r.url()))) {
    problems.push(`HTTP ${r.status()} ${r.request().method()} ${r.url()}`);
  }
});
const shot = (name) => page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true });
const step = (msg) => console.log(`✓ ${msg}`);

async function uploadAndConvert(name) {
  await page.goto(`${BASE}/`);
  await page.locator('input[type="file"]').setInputFiles(fixture(name));
  await page.waitForURL(/\/w\/[0-9a-f]+\/files/);
  await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
  await page.getByRole("button", { name: /^Convert 5 files$/ }).first().click();
  await expect(page.locator(".badge", { hasText: "Converted" })).toBeVisible({ timeout: 30_000 });
}

process.on("uncaughtException", async (e) => {
  console.error(`FAILED at ${page.url()}\n${e.message.split("\n").slice(0, 4).join("\n")}`);
  await page.screenshot({ path: `${SHOTS}/failure.png`, fullPage: true }).catch(() => {});
  console.error(`visible text: ${(await page.locator("body").innerText().catch(() => "")).slice(0, 600)}`);
  console.error(problems.join("\n"));
  process.exit(1);
});

// 1. Sign in (bad then good)
await page.goto(`${BASE}/`);
await page.waitForURL(/\/login/);
await page.getByLabel("Username").fill("admin");
await page.getByLabel("Password").fill("wrong-password");
await page.getByRole("button", { name: "Sign in" }).click();
await expect(page.getByRole("alert")).toContainText("Incorrect username or password");
await shot("01-login-error");
await page.getByLabel("Password").fill(PASSWORD);
await page.getByRole("button", { name: "Sign in" }).click();
await expect(page.getByRole("heading", { level: 1, name: "Workspaces" })).toBeVisible();
await expect(page.getByText("No workspaces yet")).toBeVisible();
await shot("02-home-empty");
step("sign-in flow, empty state");

// 2. Upload + scan + group tabs
await page.locator('input[type="file"]').setInputFiles(fixture("Export_20240101_1200.zip"));
await page.waitForURL(/\/w\/[0-9a-f]+\/files/);
const tabs = page.getByRole("toolbar", { name: "Filter files by module group" });
for (const code of ["AR", "FUN", "GL", "INV"]) await expect(tabs.getByRole("button", { name: new RegExp(`^${code}`) })).toBeVisible();
await tabs.getByRole("button", { name: /^AR/ }).click();
await expect(page.locator("p", { hasText: /AR\s*·\s*Receivables\s*·\s*Finance/ })).toBeVisible();
await shot("03-files-scanned");
step("upload, nested scan, module group tabs");

// 3. Convert
await tabs.getByRole("button", { name: /^All/ }).click();
await page.getByRole("button", { name: /^Convert 5 files$/ }).first().click();
await expect(page.locator(".badge", { hasText: "Converted" })).toBeVisible({ timeout: 30_000 });
await page.getByRole("link", { name: /^Data/ }).click();
step("conversion job");

// 4. Data grid: browse, search, edit
await page.getByRole("button", { name: /AR_PAYMENT_TERMS/ }).click();
const grid = page.getByRole("region", { name: "Rows of AR_PAYMENT_TERMS.CSV" });
await expect(grid.getByRole("cell", { name: "NET30" })).toBeVisible();
await page.getByPlaceholder("Find in rows…").fill("net6");
await expect(page.getByText("1–1 of 1 matching row")).toBeVisible();
await page.getByPlaceholder("Find in rows…").fill("");
await expect(page.getByText("1–3 of 3 rows")).toBeVisible();
await page.getByRole("button", { name: "Edit", exact: true }).click();
await grid.getByRole("button", { name: "Edit Name, row 3" }).click();
const cell = grid.getByRole("textbox", { name: "Name, row 3" });
await cell.fill("CASH ON DELIVERY");
await cell.press("Enter");
await expect(page.getByText("1 unsaved change")).toBeVisible();
await shot("04-data-editing");
await page.getByRole("button", { name: "Save" }).click();
await expect(page.getByRole("status").getByText(/Saved 1 change/)).toBeVisible();
await expect(grid.getByRole("cell", { name: "CASH ON DELIVERY" })).toBeVisible();
await shot("05-data-saved");
step("dataset grid: page, search, edit, save");

// 5. Structure
await page.getByRole("link", { name: "Structure" }).click();
const tree = page.getByRole("list", { name: "Business structure" });
await expect(tree.getByText("US Ledger")).toBeVisible();
await expect(tree.getByText("Dallas DC")).toBeVisible();
await page.getByPlaceholder("Ledger, legal entity, unit or org name").fill("leeds");
await expect(tree.getByText("Dallas DC")).toBeHidden();
await expect(tree.getByText("Leeds DC")).toBeVisible();
await shot("06-structure");
step("business structure outline and filter");

// 6. Ask: build index, ask, follow citation to the source row
await page.getByRole("link", { name: "Ask" }).click();
await page.getByRole("button", { name: "Build index" }).click();
await expect(page.getByText(/rows indexed/)).toBeVisible({ timeout: 30_000 });
await page.getByLabel("Your question").fill("Which inventory organization belongs to US Ops?");
await page.getByRole("button", { name: "Send question" }).click();
// Retrieval mode (no LLM configured): the answer lists matched rows with inline citations.
const match = page.locator(".md li", { hasText: "INVENTORYORGANIZATIONMASTER" }).filter({ hasText: "Dallas DC" });
await expect(match).toBeVisible({ timeout: 15_000 });
await shot("07-ask-answer");
await match.getByRole("button", { name: /^Source \d+$/ }).click();
await page.waitForURL(/\/data\?d=.*&row=/);
await expect(page.locator("tr.focus")).toContainText("Dallas DC");
await shot("08-citation-row");
step("index, grounded answer with citations, jump to cited row");

// 7. Second extract + comparison with drilldown
await uploadAndConvert("Export_20240202_0900.zip");
await page.getByRole("link", { name: "Compare" }).first().click();
await page.getByRole("button", { name: "Compare", exact: true }).click();
await page.waitForURL(/\/compare\/[0-9a-f]+/, { timeout: 30_000 });
// Before = first upload (edited COD row), After = second upload.
await expect(page.getByRole("button", { name: /Modified/ })).toContainText("1");
await page.getByRole("button", { name: "AR_PAYMENT_TERMS.CSV" }).click();
const diff = page.getByRole("region", { name: "Row differences" });
await expect(diff.getByText("45")).toBeVisible();
await shot("09-comparison-diff");
step("comparison summary and row-level drilldown");

// 8. Admin: create a user, issue a reset code
await page.getByRole("link", { name: "Admin", exact: true }).click();
await page.getByLabel("Username").fill("analyst1");
await page.getByLabel("Initial password").fill("Analyst-Pass-01");
await page.getByRole("button", { name: "Add user" }).click();
await expect(page.getByRole("rowheader", { name: "analyst1" })).toBeVisible();
await page.getByRole("row", { name: /analyst1/ }).getByRole("button", { name: "Reset code" }).click();
await expect(page.getByRole("dialog", { name: "Reset code for analyst1" })).toBeVisible();
await shot("10-admin-reset-code");
await page.getByRole("button", { name: "Done" }).click();
await page.getByRole("button", { name: "Audit log" }).click();
await expect(page.getByRole("cell", { name: "user.created" }).first()).toBeVisible();
step("admin: create user, reset code dialog, audit log");

// 9. Appearance: dark theme persists across reload
await page.getByRole("link", { name: /Account settings/ }).click();
await page.getByText("Dark", { exact: true }).click();
await page.reload();
expect(await page.evaluate(() => getComputedStyle(document.documentElement).colorScheme)).toBe("dark");
await page.goto(page.url().replace("/account", "/"));
await page.getByRole("link", { name: "Export_20240101_1200.zip", exact: true }).click();
await page.getByRole("link", { name: /^Data/ }).click();
await shot("11-data-dark");
step("dark theme applies before paint and persists");

// 10. Mobile layout: no horizontal page overflow
await page.setViewportSize({ width: 390, height: 844 });
for (const tab of ["Data", "Structure", "Ask"]) {
  await page.getByRole("link", { name: new RegExp(`^${tab}`) }).click();
  await page.waitForTimeout(300);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  if (overflow > 0) problems.push(`mobile overflow ${overflow}px on ${tab}`);
  await shot(`12-mobile-${tab.toLowerCase()}`);
}
step("mobile layout fits 390px");

await browser.close();
if (problems.length) {
  console.error(`\n${problems.length} problem(s):\n${problems.join("\n")}`);
  process.exit(1);
}
console.log("\nAll journeys passed with no console errors or failed requests.");
