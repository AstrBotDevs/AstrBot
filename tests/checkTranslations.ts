/**
 * Translation Key Consistency Checker
 *
 * This script checks that all translation keys are present in all locale files.
 * Missing keys are reported with their file paths.
 *
 * Usage:
 *   npx tsx tests/checkTranslations.ts
 *   npx tsx tests/checkTranslations.ts --verbose
 */

import { readdir, readFile } from "fs/promises";
import { join, relative } from "path";

const LOCALES_DIR = join(__dirname, "../dashboard/src/i18n/locales");
const LOCALES = ["en-US", "zh-CN", "ru-RU"];

interface TranslationMap {
  [key: string]: string | TranslationMap;
}

interface FileReport {
  file: string;
  missingKeys: string[];
}

interface LocaleReport {
  locale: string;
  baseMissingKeys: string[];
  crossLocaleMissing: Map<string, string[]>; // key -> [files missing it]
}

/**
 * Recursively extract all dot-notation keys from a translation object
 */
function extractKeys(obj: TranslationMap, prefix = ""): Set<string> {
  const keys = new Set<string>();

  for (const [key, value] of Object.entries(obj)) {
    const fullKey = prefix ? `${prefix}.${key}` : key;

    if (typeof value === "object" && value !== null && !Array.isArray(value)) {
      // Recurse into nested objects
      const nestedKeys = extractKeys(value as TranslationMap, fullKey);
      nestedKeys.forEach((k) => keys.add(k));
    } else {
      keys.add(fullKey);
    }
  }

  return keys;
}

/**
 * Check for missing keys between two translation maps
 */
function findMissingKeys(source: Set<string>, target: Set<string>): string[] {
  const missing: string[] = [];

  for (const key of source) {
    if (!target.has(key)) {
      missing.push(key);
    }
  }

  return missing.sort();
}

/**
 * Load and parse a translation JSON file
 */
async function loadTranslationFile(filePath: string): Promise<TranslationMap | null> {
  try {
    const content = await readFile(filePath, "utf-8");
    return JSON.parse(content);
  } catch (error) {
    console.error(`Error loading ${filePath}: ${error}`);
    return null;
  }
}

/**
 * Get all JSON files in a directory recursively
 */
async function getJsonFiles(dir: string, baseDir = ""): Promise<string[]> {
  const files: string[] = [];
  const entries = await readdir(dir, { withFileTypes: true });

  for (const entry of entries) {
    const fullPath = join(dir, entry.name);
    const relativePath = baseDir ? `${baseDir}/${entry.name}` : entry.name;

    if (entry.isDirectory()) {
      const nestedFiles = await getJsonFiles(fullPath, relativePath);
      files.push(...nestedFiles);
    } else if (entry.name.endsWith(".json")) {
      files.push(fullPath);
    }
  }

  return files;
}

/**
 * Get relative path from locales directory
 * Normalizes the path to compare across locales
 */
function getRelativePath(filePath: string): string {
  // Remove locale prefix to get the relative path
  // e.g., /path/to/locales/en-US/features/test.json -> features/test.json
  const relativePath = relative(LOCALES_DIR, filePath);
  const parts = relativePath.split("/");

  // If the first part is a locale name (en-US, zh-CN, ru-RU), remove it
  if (parts.length > 1 && LOCALES.includes(parts[0])) {
    return parts.slice(1).join("/");
  }

  return relativePath;
}

/**
 * Main check function
 */
async function checkTranslations(verbose = false): Promise<void> {
  console.log("🔍 Checking translation key consistency...\n");

  // Load base locale (English) first
  const baseLocale = "en-US";
  const baseDir = join(LOCALES_DIR, baseLocale);
  const baseFiles = await getJsonFiles(baseDir);

  console.log(`📁 Base locale: ${baseLocale} (${baseFiles.length} files)\n`);

  // Build base translations map
  const baseTranslations = new Map<string, Set<string>>(); // file -> keys

  for (const file of baseFiles) {
    const relativePath = getRelativePath(file);
    const content = await loadTranslationFile(file);

    if (content) {
      const keys = extractKeys(content);
      baseTranslations.set(relativePath, keys);

      if (verbose) {
        console.log(`  ✅ ${relativePath}: ${keys.size} keys`);
      }
    }
  }

  // Check each other locale
  for (const locale of LOCALES) {
    if (locale === baseLocale) continue;

    console.log(`\n🌐 Checking locale: ${locale}`);

    const localeDir = join(LOCALES_DIR, locale);
    const localeFiles = await getJsonFiles(localeDir);

    const localeTranslations = new Map<string, Set<string>>();
    const missingFiles: string[] = [];
    const crossLocaleMissing = new Map<string, string[]>();

    // Load locale translations
    for (const file of localeFiles) {
      const relativePath = getRelativePath(file);
      const content = await loadTranslationFile(file);

      if (content) {
        const keys = extractKeys(content);
        localeTranslations.set(relativePath, keys);
      }
    }

    // Check for missing files in this locale
    for (const [baseFile] of baseTranslations) {
      if (!localeTranslations.has(baseFile)) {
        missingFiles.push(baseFile);
        if (!crossLocaleMissing.has(baseFile)) {
          crossLocaleMissing.set(baseFile, []);
        }
        crossLocaleMissing.get(baseFile)!.push(`${locale} (missing file)`);
      }
    }

    // Check for missing keys in each file
    for (const [baseFile, baseKeys] of baseTranslations) {
      const localeKeys = localeTranslations.get(baseFile);

      if (!localeKeys) continue; // Already reported as missing file

      const missing = findMissingKeys(baseKeys, localeKeys);

      if (missing.length > 0) {
        for (const key of missing) {
          if (!crossLocaleMissing.has(key)) {
            crossLocaleMissing.set(key, []);
          }
          crossLocaleMissing.get(key)!.push(`${locale}: ${baseFile}`);
        }
      }
    }

    // Report results
    if (missingFiles.length > 0) {
      console.log(`\n  ⚠️  Missing files in ${locale}:`);
      for (const file of missingFiles) {
        console.log(`     - ${file}`);
      }
    }

    if (crossLocaleMissing.size > 0) {
      console.log(`\n  ⚠️  Missing keys in ${locale}:`);

      let keyCount = 0;
      for (const [key, locations] of crossLocaleMissing) {
        if (locations.some((l) => l.includes("missing file"))) continue; // Skip file-level issues
        keyCount++;
        console.log(`\n     Key: ${key}`);
        for (const loc of locations) {
          console.log(`       → ${loc}`);
        }
      }

      console.log(`\n  📊 Total missing keys in ${locale}: ${crossLocaleMissing.size}`);
    } else {
      console.log(`  ✅ All keys present in ${locale}`);
    }
  }

  // Summary
  console.log("\n" + "=".repeat(60));
  console.log("📋 Summary");
  console.log("=".repeat(60));

  console.log(`\nBase locale: ${baseLocale}`);
  console.log(`Locales checked: ${LOCALES.filter((l) => l !== baseLocale).join(", ")}`);
  console.log(`Files in base: ${baseFiles.length}`);

  // Count total missing across all non-base locales
  let totalMissingKeys = 0;

  for (const locale of LOCALES) {
    if (locale === baseLocale) continue;

    const localeDir = join(LOCALES_DIR, locale);
    const localeFiles = await getJsonFiles(localeDir);
    const localeTranslations = new Map<string, Set<string>>();

    for (const file of localeFiles) {
      const relativePath = getRelativePath(file);
      const content = await loadTranslationFile(file);

      if (content) {
        const keys = extractKeys(content);
        localeTranslations.set(relativePath, keys);
      }
    }

    for (const [baseFile, baseKeys] of baseTranslations) {
      const localeKeys = localeTranslations.get(baseFile);
      if (!localeKeys) continue;

      const missing = findMissingKeys(baseKeys, localeKeys);
      totalMissingKeys += missing.length;
    }
  }

  console.log(`\nTotal missing translation keys: ${totalMissingKeys}`);

  if (totalMissingKeys === 0) {
    console.log("\n🎉 All translation keys are complete!");
  } else {
    console.log("\n⚠️  Please add the missing translation keys to complete the localization.");
  }

  console.log("\n💡 To run with verbose output: npx tsx tests/checkTranslations.ts --verbose");
}

// Parse command line arguments
const verbose = process.argv.includes("--verbose") || process.argv.includes("-v");

// Run the check
checkTranslations(verbose).catch(console.error);
