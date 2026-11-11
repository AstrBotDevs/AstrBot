/**
 * Capture fish-console (:5173) screenshots for README.
 * Usage: node scripts/capture_fish_console_readme.mjs
 */
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const OUT = join(ROOT, "docs/assets/readme");
const BASE = "http://127.0.0.1:5173";
const LOGIN_EMAIL = "readme-shot@example.com";
const LOGIN_PASSWORD = "ReadmeShot2026!";

const PUBLIC_ROUTES = [
  { path: "/login", file: "console-login.png" },
  { path: "/register", file: "console-register.png" },
];

const AUTH_ROUTES = [
  { path: "/dashboard", file: "console-dashboard.png" },
  { path: "/plans", file: "console-plans.png" },
  { path: "/bot", file: "console-bot-bind.png" },
];

async function shot(page, path, file) {
  await page.goto(`${BASE}${path}`, { waitUntil: "networkidle", timeout: 30_000 });
  await page.waitForTimeout(800);
  await page.screenshot({ path: join(OUT, file), fullPage: false });
  console.log("saved", file);
}

async function main() {
  mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const viewport = { width: 1280, height: 800 };

  const guest = await browser.newContext({ viewport });
  const guestPage = await guest.newPage();
  for (const route of PUBLIC_ROUTES) {
    await shot(guestPage, route.path, route.file);
  }
  await guest.close();

  const authed = await browser.newContext({ viewport });
  const page = await authed.newPage();
  await page.goto(`${BASE}/login`, { waitUntil: "networkidle" });
  await page.locator("#email").fill(LOGIN_EMAIL);
  await page.locator("#password").fill(LOGIN_PASSWORD);
  await page.locator("form.login-form button[type='submit']").click();
  await page.waitForURL("**/dashboard", { timeout: 15_000 });
  await page.waitForTimeout(600);

  for (const route of AUTH_ROUTES) {
    await shot(page, route.path, route.file);
  }

  await authed.close();
  await browser.close();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
