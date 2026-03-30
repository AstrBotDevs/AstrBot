/**
 * Patch monaco-editor's bundled DOMPurify from 3.2.7 (vulnerable)
 * to 3.3.2 (patched) to fix XSS vulnerability.
 *
 * monaco-editor@0.55.1 hardcodes dompurify@3.2.7 as a bundled dependency.
 * This script replaces the bundled file with the patched version.
 *
 * Affected vulnerability: CVE in DOMPurify 3.1.3-3.3.1 (SAFE_FOR_XML bypass
 * via noscript, xmp, noembed, noframes, iframe rawtext elements).
 */

import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { resolve, dirname, join } from "node:path";
import https from "node:https";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");
const MONACO_DOMPURIFY = join(
  ROOT,
  "node_modules",
  "monaco-editor",
  "esm",
  "vs",
  "base",
  "browser",
  "dompurify",
  "dompurify.js"
);

// Files inside monaco-editor dev/min bundles that embed dompurify source
const BUNDLED_FILES = [
  join(ROOT, "node_modules", "monaco-editor", "dev", "vs", "editor.api.js"),
  join(ROOT, "node_modules", "monaco-editor", "min", "vs", "editor.api.min.js"),
];

const PATCHED_VERSION = "3.3.3";
const PATCHED_URL = "https://raw.githubusercontent.com/cure53/DOMPurify/main/dist/purify.js";

const dompurifyVersion = (content) => {
  const m = content.match(/DOMPurify\s+(\d+\.\d+\.\d+)/);
  return m ? m[1] : null;
};

const isVulnerable = (version) => {
  if (!version) return false;
  const [major, minor, patch] = version.split(".").map(Number);
  if (major !== 3) return false;
  if (minor === 1 && patch >= 3) return true;
  if (minor === 2) return true;
  if (minor === 3 && patch <= 1) return true;
  return false;
};

const download = (url) =>
  new Promise((resolve, reject) => {
    https
      .get(url, (res) => {
        if (res.statusCode !== 200) {
          reject(new Error(`HTTP ${res.statusCode}`));
          return;
        }
        let d = "";
        res.on("data", (c) => (d += c));
        res.on("end", () => resolve(d));
      })
      .on("error", reject);
  });

async function patchFile(source, target) {
  const content = existsSync(target) ? readFileSync(target, "utf8") : null;
  const currentVersion = content ? dompurifyVersion(content) : null;

  if (currentVersion && !isVulnerable(currentVersion)) {
    console.log(
      `[patch-dompurify] ${target} already at safe version ${currentVersion}, skipping.`
    );
    return;
  }

  console.log(`[patch-dompurify] Downloading patched DOMPurify ${PATCHED_VERSION}...`);
  const patched = await download(source);
  const patchedVer = dompurifyVersion(patched);

  if (!patchedVer || isVulnerable(patchedVer)) {
    throw new Error(
      `Downloaded DOMPurify version is still vulnerable: got ${patchedVer}`
    );
  }

  writeFileSync(target, patched, "utf8");
  console.log(
    `[patch-dompurify] Patched ${target} (${currentVersion || "new"} -> ${PATCHED_VERSION})`
  );
}

async function patchBundledContent(target) {
  if (!existsSync(target)) return;

  const content = readFileSync(target, "utf8");
  const currentVersion = dompurifyVersion(content);

  if (!currentVersion || !isVulnerable(currentVersion)) return;

  console.log(
    `[patch-dompurify] Downloading patched DOMPurify ${PATCHED_VERSION} for bundling...`
  );
  const patched = await download(PATCHED_URL);

  // Replace the dompurify version header + IIFE in the bundled file
  const patchedHeader = patched.match(
    /\/\*! @license DOMPurify [\d.]+ \|[\s\S]*?Mozilla Public License 2.0 \*\/[\s\S]*?^\(function\(\)/m
  )?.[0];

  if (patchedHeader) {
    const newContent = content.replace(
      /\/\*! @license DOMPurify 3\.2\.7[\s\S]*?^\(function\(\)/m,
      patchedHeader
    );
    writeFileSync(target, newContent, "utf8");
    console.log(
      `[patch-dompurify] Patched bundled dompurify in ${target} (${currentVersion} -> ${PATCHED_VERSION})`
    );
  } else {
    console.warn(
      `[patch-dompurify] Could not find dompurify IIFE pattern in ${target}, skipping.`
    );
  }
}

async function main() {
  console.log("[patch-dompurify] Starting DOMPurify patch...");

  try {
    await patchFile(PATCHED_URL, MONACO_DOMPURIFY);

    for (const file of BUNDLED_FILES) {
      await patchBundledContent(file);
    }

    console.log("[patch-dompurify] Done.");
  } catch (err) {
    // Don't fail the install
    console.error(`[patch-dompurify] ERROR: ${err.message}`);
    process.exit(0);
  }
}

main();
