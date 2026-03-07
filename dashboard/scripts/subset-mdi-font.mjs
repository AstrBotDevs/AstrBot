#!/usr/bin/env node
/**
 * subset-mdi-font.mjs
 *
 * Build script that:
 * 1. Scans src/ for all mdi-* icon names used in .vue/.ts files
 * 2. Resolves their Unicode codepoints from @mdi/font CSS
 * 3. Subsets the MDI font to include only those glyphs (via subset-font, pure JS)
 * 4. Generates a minimal CSS file with only the needed icon classes
 * 5. Outputs to src/assets/mdi-subset/
 *
 * Fallback: if any step fails, copies the original full @mdi/font CSS and fonts
 * so the build never breaks.
 */
import { readFileSync, writeFileSync, copyFileSync, readdirSync, statSync, existsSync, mkdirSync } from "fs";
import { join, resolve, extname } from "path";

const ROOT = resolve(import.meta.dirname, "..");
const SRC = join(ROOT, "src");
const MDI_CSS_PATH = join(ROOT, "node_modules/@mdi/font/css/materialdesignicons.css");
const MDI_TTF_PATH = join(ROOT, "node_modules/@mdi/font/fonts/materialdesignicons-webfont.ttf");
const MDI_WOFF2_PATH = join(ROOT, "node_modules/@mdi/font/fonts/materialdesignicons-webfont.woff2");
const MDI_WOFF_PATH = join(ROOT, "node_modules/@mdi/font/fonts/materialdesignicons-webfont.woff");
const OUT_DIR = join(ROOT, "src/assets/mdi-subset");

mkdirSync(OUT_DIR, { recursive: true });

// ── Fallback: copy original full MDI font if subsetting fails ───────────────
function fallbackToFullFont(reason) {
    console.warn(`\n⚠️  Subsetting failed: ${reason}`);
    console.warn(`⚠️  Falling back to full @mdi/font (build will not break)\n`);

    // Copy original font files
    if (existsSync(MDI_WOFF2_PATH)) {
        copyFileSync(MDI_WOFF2_PATH, join(OUT_DIR, "materialdesignicons-webfont-subset.woff2"));
    }
    if (existsSync(MDI_WOFF_PATH)) {
        copyFileSync(MDI_WOFF_PATH, join(OUT_DIR, "materialdesignicons-webfont-subset.woff"));
    }

    // Generate a CSS that imports the full font with the subset file names
    const mdiCSS = readFileSync(MDI_CSS_PATH, "utf-8");
    const fallbackCSS = mdiCSS
        .replace(/url\("\.\.\/fonts\/materialdesignicons-webfont\.(woff2?)\?[^"]*"\)/g,
            (_, ext) => `url("./materialdesignicons-webfont-subset.${ext}")`)
        .replace(/url\("\.\.\/fonts\/materialdesignicons-webfont\.(eot|ttf)\?[^"]*"\)[^,]*/g, "")
        .replace(/src:\s*,/g, "src:")
        .replace(/,\s*;/g, ";");
    writeFileSync(join(OUT_DIR, "materialdesignicons-subset.css"), fallbackCSS);

    const size = existsSync(MDI_WOFF2_PATH) ? statSync(MDI_WOFF2_PATH).size : 0;
    console.warn(`⚠️  Fallback complete: using full font (${(size / 1024).toFixed(1)} KB woff2)`);
}

try {
    // ── Pre-checks ────────────────────────────────────────────────────────────
    if (!existsSync(MDI_CSS_PATH)) {
        throw new Error(`@mdi/font CSS not found at ${MDI_CSS_PATH}. Run 'pnpm install' first.`);
    }
    if (!existsSync(MDI_TTF_PATH)) {
        throw new Error(`@mdi/font TTF not found at ${MDI_TTF_PATH}. Run 'pnpm install' first.`);
    }

    // Dynamic import subset-font (may not be installed in all environments)
    let subsetFont;
    try {
        subsetFont = (await import("subset-font")).default;
    } catch (e) {
        throw new Error(`subset-font package not available: ${e.message}. Run 'pnpm install' first.`);
    }

    // ── Step 1: Scan source files for mdi-* icon names ────────────────────────
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
    const utilityClasses = new Set([
        "mdi-set", "mdi-spin", "mdi-rotate-45", "mdi-rotate-90", "mdi-rotate-135",
        "mdi-rotate-180", "mdi-rotate-225", "mdi-rotate-270", "mdi-rotate-315",
        "mdi-flip-h", "mdi-flip-v", "mdi-light", "mdi-dark", "mdi-inactive",
        "mdi-18px", "mdi-24px", "mdi-36px", "mdi-48px",
    ]);
    for (const file of sourceFiles) {
        const content = readFileSync(file, "utf-8");
        for (const match of content.matchAll(iconPattern)) {
            if (!utilityClasses.has(match[0])) {
                usedIcons.add(match[0]);
            }
        }
    }

    if (usedIcons.size === 0) {
        throw new Error("No mdi-* icons found in source files. Something is wrong with scanning.");
    }
    console.log(`✅ Found ${usedIcons.size} unique mdi-* icons in source files`);

    // ── Step 2: Parse @mdi/font CSS to get codepoints for each icon ───────────
    const mdiCSS = readFileSync(MDI_CSS_PATH, "utf-8");
    const classPattern = /\.(mdi-[a-z][a-z0-9-]*)::before\s*\{\s*content:\s*"\\([0-9A-Fa-f]+)"/g;
    const iconMap = new Map();
    for (const match of mdiCSS.matchAll(classPattern)) {
        iconMap.set(match[1], match[2]);
    }

    if (iconMap.size === 0) {
        throw new Error("Could not parse any icon definitions from @mdi/font CSS. Format may have changed.");
    }
    console.log(`📦 MDI font CSS contains ${iconMap.size} icon definitions`);

    // ── Step 3: Resolve codepoints for used icons ─────────────────────────────
    const resolvedIcons = [];
    const missingIcons = [];
    const subsetChars = [];
    for (const icon of usedIcons) {
        const cp = iconMap.get(icon);
        if (cp) {
            resolvedIcons.push(icon);
            subsetChars.push(String.fromCodePoint(parseInt(cp, 16)));
        } else {
            missingIcons.push(icon);
        }
    }

    if (missingIcons.length > 0) {
        console.warn(`⚠️  ${missingIcons.length} icons not found in MDI CSS:`, missingIcons.join(", "));
    }
    if (resolvedIcons.length === 0) {
        throw new Error("No icon codepoints could be resolved. Icon name format may have changed.");
    }
    console.log(`🔍 Resolved ${resolvedIcons.length} codepoints for subsetting`);

    // Add space character
    subsetChars.push(" ");
    const subsetText = subsetChars.join("");

    // ── Step 4: Subset font with subset-font (pure JS/WASM) ──────────────────
    const fontBuffer = readFileSync(MDI_TTF_PATH);

    console.log(`🔧 Subsetting font to woff2...`);
    const woff2Buffer = await subsetFont(fontBuffer, subsetText, {
        targetFormat: "woff2",
    });

    console.log(`🔧 Subsetting font to woff...`);
    const woffBuffer = await subsetFont(fontBuffer, subsetText, {
        targetFormat: "woff",
    });

    if (woff2Buffer.length === 0 || woffBuffer.length === 0) {
        throw new Error("subset-font produced empty output. Font file may be corrupted.");
    }

    const outWoff2 = join(OUT_DIR, "materialdesignicons-webfont-subset.woff2");
    const outWoff = join(OUT_DIR, "materialdesignicons-webfont-subset.woff");
    writeFileSync(outWoff2, woff2Buffer);
    writeFileSync(outWoff, woffBuffer);

    // ── Step 5: Generate subset CSS ───────────────────────────────────────────
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

    // Extract all utility classes from the original MDI CSS
    // These are the non-icon classes: size modifiers, color themes, rotation, flip, spin
    const utilityStartMarker = ".mdi-18px.mdi-set";
    const utilityStartIndex = mdiCSS.indexOf(utilityStartMarker);
    if (utilityStartIndex !== -1) {
        const utilityCss = mdiCSS.slice(utilityStartIndex).replace(/\/\*# sourceMappingURL=.*\*\//, "").trim();
        css += `/* Utility classes (extracted from @mdi/font) */\n${utilityCss}\n`;
    } else {
        console.warn("⚠️  Could not find MDI utility classes in original CSS, skipping");
    }

    const outCSS = join(OUT_DIR, "materialdesignicons-subset.css");
    writeFileSync(outCSS, css);

    // ── Report ────────────────────────────────────────────────────────────────
    const origSize = statSync(MDI_TTF_PATH).size;
    const subsetWoff2Size = woff2Buffer.length;
    console.log(`\n📊 Results:`);
    console.log(`   Original TTF font: ${(origSize / 1024).toFixed(1)} KB`);
    console.log(`   Subset WOFF2:      ${(subsetWoff2Size / 1024).toFixed(1)} KB`);
    console.log(`   Reduction:         ${((1 - subsetWoff2Size / origSize) * 100).toFixed(1)}%`);
    console.log(`   Icons included:    ${resolvedIcons.length}`);
    console.log(`   CSS file:          ${outCSS}`);
    console.log(`\n✅ MDI font subset generated successfully!`);

} catch (err) {
    // ── Fallback: any failure → use original full font so build never breaks ──
    try {
        fallbackToFullFont(err.message);
    } catch (fallbackErr) {
        console.error(`❌ Fallback also failed: ${fallbackErr.message}`);
        console.error(`❌ Please ensure @mdi/font is installed: pnpm install`);
        process.exit(1);
    }
}
