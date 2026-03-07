#!/usr/bin/env node
/**
 * subset-mdi-font.mjs
 *
 * Build script that:
 * 1. Scans src/ for all mdi-* icon names used in .vue/.ts files
 * 2. Resolves their Unicode codepoints from @mdi/font CSS
 * 3. Subsets the MDI woff2 font to include only those glyphs (via pyftsubset)
 * 4. Generates a minimal CSS file with only the needed icon classes
 * 5. Outputs to src/assets/mdi-subset/
 */
import { execSync } from "child_process";
import { readFileSync, writeFileSync, readdirSync, statSync } from "fs";
import { join, resolve, extname } from "path";

const ROOT = resolve(import.meta.dirname, "..");
const SRC = join(ROOT, "src");
const MDI_CSS = join(
    ROOT,
    "node_modules/@mdi/font/css/materialdesignicons.css"
);
const MDI_TTF = join(
    ROOT,
    "node_modules/@mdi/font/fonts/materialdesignicons-webfont.ttf"
);
const OUT_DIR = join(ROOT, "src/assets/mdi-subset");

// ── Step 1: Scan source files for mdi-* icon names ──────────────────────────
function collectFiles(dir, exts) {
    let files = [];
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
        const full = join(dir, entry.name);
        if (entry.isDirectory() && entry.name !== "node_modules") {
            files = files.concat(collectFiles(full, exts));
        } else if (exts.includes(extname(entry.name))) {
            files.push(full);
        }
    }
    return files;
}

const sourceFiles = collectFiles(SRC, [".vue", ".ts", ".js"]);
const iconPattern = /mdi-[a-z][a-z0-9-]*/g;
const usedIcons = new Set();
for (const file of sourceFiles) {
    const content = readFileSync(file, "utf-8");
    for (const match of content.matchAll(iconPattern)) {
        // Exclude pseudo-classes like mdi-set, mdi-spin (utility classes, not icons)
        if (!["mdi-set", "mdi-spin", "mdi-rotate-45", "mdi-rotate-90", "mdi-rotate-135",
            "mdi-rotate-180", "mdi-rotate-225", "mdi-rotate-270", "mdi-rotate-315",
            "mdi-flip-h", "mdi-flip-v", "mdi-light", "mdi-dark", "mdi-inactive",
            "mdi-18px", "mdi-24px", "mdi-36px", "mdi-48px"].includes(match[0])) {
            usedIcons.add(match[0]);
        }
    }
}

console.log(`✅ Found ${usedIcons.size} unique mdi-* icons in source files`);

// ── Step 2: Parse @mdi/font CSS to get codepoints for each icon ─────────────
const mdiCSS = readFileSync(MDI_CSS, "utf-8");
const classPattern = /\.(mdi-[a-z][a-z0-9-]*)::before\s*\{\s*content:\s*"\\([0-9A-Fa-f]+)"/g;
const iconMap = new Map(); // iconName -> unicode codepoint (hex string)
for (const match of mdiCSS.matchAll(classPattern)) {
    iconMap.set(match[1], match[2]);
}

console.log(`📦 MDI font CSS contains ${iconMap.size} icon definitions`);

// ── Step 3: Resolve codepoints for used icons ───────────────────────────────
const codepoints = [];
const resolvedIcons = [];
const missingIcons = [];
for (const icon of usedIcons) {
    const cp = iconMap.get(icon);
    if (cp) {
        codepoints.push(`U+${cp}`);
        resolvedIcons.push(icon);
    } else {
        missingIcons.push(icon);
    }
}

if (missingIcons.length > 0) {
    console.warn(`⚠️  ${missingIcons.length} icons not found in MDI CSS:`, missingIcons.join(", "));
}
console.log(`🔍 Resolved ${codepoints.length} codepoints for subsetting`);

// Always include the base glyph ranges needed for the font to work
// U+F0000-F FFFF is the private use area where MDI places glyphs
const unicodeRange = [
    "U+0020",          // space
    ...codepoints,
].join(",");

// ── Step 4: Subset font with pyftsubset ─────────────────────────────────────
const outWoff2 = join(OUT_DIR, "materialdesignicons-webfont-subset.woff2");
const outWoff = join(OUT_DIR, "materialdesignicons-webfont-subset.woff");

const pyftsubsetCmd = [
    "pyftsubset",
    `"${MDI_TTF}"`,
    `--unicodes="${unicodeRange}"`,
    `--output-file="${outWoff2}"`,
    "--flavor=woff2",
    "--no-hinting",
    "--desubroutinize",
].join(" ");
console.log(`🔧 Running pyftsubset for woff2...`);
execSync(pyftsubsetCmd, { stdio: "inherit" });

const pyftsubsetWoffCmd = [
    "pyftsubset",
    `"${MDI_TTF}"`,
    `--unicodes="${unicodeRange}"`,
    `--output-file="${outWoff}"`,
    "--flavor=woff",
    "--no-hinting",
    "--desubroutinize",
].join(" ");
console.log(`🔧 Running pyftsubset for woff...`);
execSync(pyftsubsetWoffCmd, { stdio: "inherit" });

// ── Step 5: Generate subset CSS ─────────────────────────────────────────────
let css = `/* Auto-generated MDI subset – ${resolvedIcons.length} icons */
/* Do not edit manually. Run: pnpm run subset-icons */

@font-face {
  font-family: "Material Design Icons";
  src: url("./materialdesignicons-webfont-subset.woff2") format("woff2"),
       url("./materialdesignicons-webfont-subset.woff") format("woff");
  font-weight: normal;
  font-style: normal;
}

.mdi:before,
.mdi-set {
  display: inline-block;
  font: normal normal normal 24px/1 "Material Design Icons";
  font-size: inherit;
  text-rendering: auto;
  line-height: inherit;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

`;

for (const icon of resolvedIcons.sort()) {
    const cp = iconMap.get(icon);
    css += `.${icon}::before {\n  content: "\\${cp}";\n}\n\n`;
}

// Add the mdi-spin utility class (used for loading spinners)
css += `/* Utility classes */
.mdi-spin {
  -webkit-animation: mdi-spin 2s infinite linear;
  animation: mdi-spin 2s infinite linear;
}

@-webkit-keyframes mdi-spin {
  0% { -webkit-transform: rotate(0deg); transform: rotate(0deg); }
  100% { -webkit-transform: rotate(359deg); transform: rotate(359deg); }
}

@keyframes mdi-spin {
  0% { -webkit-transform: rotate(0deg); transform: rotate(0deg); }
  100% { -webkit-transform: rotate(359deg); transform: rotate(359deg); }
}
`;

const outCSS = join(OUT_DIR, "materialdesignicons-subset.css");
writeFileSync(outCSS, css);

// ── Report ──────────────────────────────────────────────────────────────────
const origSize = statSync(MDI_TTF).size;
const subsetWoff2Size = statSync(outWoff2).size;
console.log(`\n📊 Results:`);
console.log(`   Original TTF font: ${(origSize / 1024).toFixed(1)} KB`);
console.log(`   Subset WOFF2:      ${(subsetWoff2Size / 1024).toFixed(1)} KB`);
console.log(`   Reduction:         ${((1 - subsetWoff2Size / origSize) * 100).toFixed(1)}%`);
console.log(`   Icons included:    ${resolvedIcons.length}`);
console.log(`   CSS file:          ${outCSS}`);
console.log(`\n✅ MDI font subset generated successfully!`);
