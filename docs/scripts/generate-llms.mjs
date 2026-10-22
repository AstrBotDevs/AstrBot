import { randomUUID } from "node:crypto";
import {
  mkdir,
  open,
  readFile,
  readdir,
  rename,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
import { dirname, join, posix, relative, resolve, sep } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { fileURLToPath } from "node:url";

export const SITE_URL = "https://docs.astrbot.app";

const SCRIPT_PATH = fileURLToPath(import.meta.url);
const DOCS_ROOT = dirname(dirname(SCRIPT_PATH));
const DEFAULT_PUBLIC_DIR = join(DOCS_ROOT, "public");
const MAX_LANGUAGE_BYTES = 3 * 1024 * 1024;
const MAX_FULL_BYTES = 5 * 1024 * 1024;
const GENERATED_TEXT_FILES = [
  "llms.txt",
  "llms-full.txt",
  "llms-zh.txt",
  "llms-en.txt",
];
const GENERATOR_LOCK_FILE = ".llms-generator.lock";
const GENERATOR_LOCK_TIMEOUT_MS = 30_000;
const GENERATOR_LOCK_STALE_MS = 5 * 60 * 1000;

const LOCALES = {
  zh: {
    label: "简体中文",
    fullTitle: "AstrBot 中文文档 - 完整 Markdown",
    fullSummary:
      "AstrBot 官方中文文档，涵盖部署、平台接入、AI 配置、使用和插件开发。",
  },
  en: {
    label: "English",
    fullTitle: "AstrBot Documentation - Complete Markdown",
    fullSummary:
      "Official AstrBot documentation covering deployment, platform integrations, AI configuration, usage, and plugin development.",
  },
};

const CATEGORY_LABELS = {
  zh: {
    root: "简介",
    config: "配置",
    deploy: "部署",
    platform: "接入消息平台",
    providers: "接入 AI",
    use: "使用",
    dev: "开发",
    others: "其他",
    "community-events": "社区活动",
    ospp: "开源之夏",
  },
  en: {
    root: "Introduction",
    config: "Configuration",
    deploy: "Deployment",
    platform: "Messaging Platforms",
    providers: "AI Integration",
    use: "Usage",
    dev: "Development",
    others: "Others",
    "community-events": "Community Events",
    ospp: "Open Source Summer",
  },
};

const CATEGORY_ORDER = [
  "root",
  "config",
  "deploy",
  "platform",
  "providers",
  "use",
  "dev",
  "others",
  "community-events",
  "ospp",
];

const EXCLUDED_SEGMENTS = new Set([
  ".vitepress",
  "node_modules",
  "public",
]);

const CONTAINER_TYPES = new Set([
  "tip",
  "info",
  "warning",
  "danger",
  "details",
]);

const LINK_RE = /(!?\[[^\]]*\]\()([^)\s]+)((?:\s+["'][^"']*["'])?\))/g;

/**
 * Converts a native file path to a POSIX-style path.
 *
 * @param {string} value File path to normalize.
 * @returns {string} Normalized POSIX-style path.
 */
function toPosix(value) {
  return value.split(sep).join(posix.sep);
}

/**
 * Compares strings by Unicode code point for deterministic cross-platform output.
 *
 * @param {string} left Left value.
 * @param {string} right Right value.
 * @returns {number} Negative, zero, or positive comparison result.
 */
function compareStrings(left, right) {
  return left < right ? -1 : left > right ? 1 : 0;
}

/**
 * Encodes a path for use in generated Markdown links.
 *
 * @param {string} pathname Absolute site path.
 * @returns {string} URL-safe site path.
 */
function encodeSitePath(pathname) {
  return pathname
    .split("/")
    .map((segment) => {
      let decodedSegment = segment;
      try {
        decodedSegment = decodeURIComponent(segment);
      } catch {
        // A literal percent sign is encoded safely below.
      }
      return encodeURIComponent(decodedSegment);
    })
    .join("/");
}

/**
 * Builds the clean canonical route for a localized Markdown page.
 *
 * @param {"zh" | "en"} language Documentation language.
 * @param {string} relativePath Markdown path relative to the language root.
 * @returns {string} Canonical site path without an HTML extension.
 */
export function canonicalPathFor(language, relativePath) {
  const normalizedPath = toPosix(relativePath).replace(/^\/+/, "");
  if (!LOCALES[language]) {
    throw new Error(`Unsupported documentation language: ${language}`);
  }
  if (!normalizedPath.endsWith(".md")) {
    throw new Error(`Expected a Markdown path: ${relativePath}`);
  }

  const withoutExtension = normalizedPath.slice(0, -3);
  let pagePath;
  if (withoutExtension === "index") {
    pagePath = "/";
  } else if (withoutExtension.endsWith("/index")) {
    pagePath = `/${withoutExtension.slice(0, -6)}/`;
  } else {
    pagePath = `/${withoutExtension}`;
  }

  if (language === "en") {
    return pagePath === "/" ? "/en/" : `/en${pagePath}`;
  }
  return pagePath;
}

/**
 * Builds the raw Markdown route from a VitePress page path.
 *
 * @param {string} relativePath Page path relative to the VitePress source root.
 * @returns {string | null} Raw Markdown site path, or null for non-document pages.
 */
export function rawMarkdownPathForPage(relativePath) {
  const normalizedPath = toPosix(relativePath).replace(/^\.\/+/, "");
  if (!/^(zh|en)\/.+\.md$/.test(normalizedPath)) {
    return null;
  }
  return encodeSitePath(`/raw/${normalizedPath}`);
}

/**
 * Creates the public URL for a site path.
 *
 * @param {string} pathname Absolute site path.
 * @returns {string} Absolute URL.
 */
function publicUrl(pathname) {
  return `${SITE_URL}${encodeSitePath(pathname)}`;
}

/**
 * Recursively collects Markdown files in deterministic order.
 *
 * @param {string} root Directory to scan.
 * @returns {Promise<string[]>} POSIX-style relative Markdown paths.
 */
async function collectMarkdownFiles(root) {
  const files = [];

  async function visit(directory) {
    const entries = await readdir(directory, { withFileTypes: true });
    entries.sort((left, right) => compareStrings(left.name, right.name));

    for (const entry of entries) {
      if (EXCLUDED_SEGMENTS.has(entry.name) || entry.isSymbolicLink()) {
        continue;
      }

      const absolutePath = join(directory, entry.name);
      if (entry.isDirectory()) {
        await visit(absolutePath);
      } else if (entry.isFile() && entry.name.endsWith(".md")) {
        files.push(toPosix(relative(root, absolutePath)));
      }
    }
  }

  await visit(root);
  return files.sort();
}

/**
 * Splits optional YAML frontmatter from Markdown content.
 *
 * @param {string} content Markdown content.
 * @returns {{ frontmatter: string, body: string, normalized: string }} Parsed content.
 */
function splitFrontmatter(content) {
  const normalized = content.replace(/\r\n?/g, "\n");
  const match = normalized.match(/^---\n([\s\S]*?)\n---(?:\n|$)/);
  if (!match) {
    return { frontmatter: "", body: normalized, normalized };
  }
  return {
    frontmatter: match[1],
    body: normalized.slice(match[0].length),
    normalized,
  };
}

/**
 * Removes common inline Markdown syntax from generated metadata.
 *
 * @param {string} value Markdown text.
 * @returns {string} Plain text.
 */
function stripInlineMarkdown(value) {
  return value
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/<[^>]+>/g, "")
    .replace(/(`+)(.*?)\1/g, "$2")
    .replace(/[*_~]/g, "")
    .replace(/^\s*(?:>\s*)?(?:\d+[.)]|[-+*])\s+/, "")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Finds the first level-one heading outside fenced code blocks.
 *
 * @param {string[]} lines Markdown lines.
 * @returns {{ index: number, title: string } | null} Heading information.
 */
function findFirstH1(lines) {
  let fence = null;
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const fenceMatch = line.match(/^\s*(`{3,}|~{3,})/);
    if (fence) {
      if (fenceMatch && fenceMatch[1][0] === fence[0]) {
        fence = null;
      }
      continue;
    }
    if (fenceMatch) {
      fence = fenceMatch[1];
      continue;
    }

    const headingMatch = line.match(/^#\s+(.+?)\s*$/);
    if (headingMatch) {
      return {
        index,
        title: stripInlineMarkdown(
          headingMatch[1].replace(/\s*\{#[^}]+\}\s*$/, ""),
        ),
      };
    }
  }
  return null;
}

/**
 * Extracts a compact summary from the first prose paragraph after the title.
 *
 * @param {string[]} lines Markdown lines.
 * @param {number} startIndex Line index after which extraction starts.
 * @returns {string} Page summary.
 */
function extractSummary(lines, startIndex) {
  let fence = null;
  let paragraph = [];
  let paragraphStarted = false;

  for (let index = startIndex + 1; index < lines.length; index += 1) {
    const line = lines[index];
    const fenceMatch = line.match(/^\s*(`{3,}|~{3,})/);
    if (fence) {
      if (fenceMatch && fenceMatch[1][0] === fence[0]) {
        fence = null;
      }
      continue;
    }
    if (fenceMatch) {
      fence = fenceMatch[1];
      continue;
    }

    if (
      /^\s*(?:#{1,6}(?:\s|$)|>{1,2}(?:\s|$)|:{3,}|<script\b|<!--|import\s|\||!\[)/.test(
        line,
      )
    ) {
      continue;
    }

    const plainText = stripInlineMarkdown(line);
    if (!plainText) {
      if (paragraphStarted) {
        break;
      }
      continue;
    }

    paragraphStarted = true;
    paragraph.push(plainText);
  }

  const summary = paragraph.join(" ");
  if (summary.length <= 180) {
    return summary;
  }
  return `${summary.slice(0, 177).trimEnd()}...`;
}

/**
 * Parses metadata needed for indexes, full text, and alternate links.
 *
 * @param {"zh" | "en"} language Documentation language.
 * @param {string} relativePath Markdown path relative to the language root.
 * @param {Buffer} sourceBuffer Original source bytes.
 * @returns {object} Parsed document metadata.
 */
function parseDocument(language, relativePath, sourceBuffer) {
  const source = sourceBuffer.toString("utf8");
  const { frontmatter, body } = splitFrontmatter(source);
  const lines = body.split("\n");
  const firstH1 = findFirstH1(lines);
  const isHomePage = /^\s*layout:\s*home\s*(?:#.*)?$/m.test(frontmatter);
  const frontmatterTitle = frontmatter.match(
    /^\s*title:\s*(?:"([^"]+)"|'([^']+)'|(.+?))\s*$/m,
  );
  const fallbackTitle = relativePath
    .slice(0, -3)
    .split("/")
    .at(-1)
    .replaceAll("-", " ")
    .replaceAll("_", " ");
  const title = isHomePage
    ? language === "zh"
      ? "AstrBot 文档"
      : "AstrBot Documentation"
    : (frontmatterTitle &&
        (frontmatterTitle[1] || frontmatterTitle[2] || frontmatterTitle[3])) ||
      firstH1?.title ||
      fallbackTitle;
  const summary = isHomePage
    ? LOCALES[language].fullSummary
    : firstH1
      ? extractSummary(lines, firstH1.index)
      : "";
  const categorySegment = relativePath.includes("/")
    ? relativePath.split("/")[0]
    : "root";
  const canonicalPath = canonicalPathFor(language, relativePath);
  const rawPath = `/raw/${language}/${relativePath}`;

  return {
    language,
    relativePath,
    sourceBuffer,
    body,
    title: stripInlineMarkdown(title),
    summary,
    firstH1Index: firstH1?.index ?? -1,
    categorySegment,
    canonicalPath,
    canonicalUrl: publicUrl(canonicalPath),
    rawPath,
    rawUrl: publicUrl(rawPath),
    isDraft: /^\s*draft:\s*true\s*(?:#.*)?$/m.test(frontmatter),
    isLayoutFalse: /^\s*layout:\s*false\s*(?:#.*)?$/m.test(frontmatter),
    isNoindex: /^\s*content:\s*["']?noindex\b/m.test(frontmatter),
  };
}

/**
 * Returns whether a document may appear in AI-facing indexes.
 *
 * @param {object} document Parsed document.
 * @returns {boolean} True when the page is canonical content.
 */
function isCanonicalDocument(document) {
  return (
    !document.isDraft &&
    !document.isLayoutFalse &&
    !document.isNoindex
  );
}

/**
 * Cleans VitePress-only syntax while retaining meaningful page content.
 *
 * @param {object} document Parsed document.
 * @returns {string} Portable Markdown.
 */
function normalizeBody(document) {
  const lines = document.body.split("\n");
  const output = [];
  let fence = null;
  let inSetupScript = false;
  let removedH1 = false;

  for (const line of lines) {
    const fenceMatch = line.match(/^\s*(`{3,}|~{3,})/);
    if (fence) {
      output.push(line);
      if (fenceMatch && fenceMatch[1][0] === fence[0]) {
        fence = null;
      }
      continue;
    }
    if (inSetupScript) {
      if (/^\s*<\/script>\s*$/.test(line)) {
        inSetupScript = false;
      }
      continue;
    }
    if (fenceMatch) {
      fence = fenceMatch[1];
      output.push(line);
      continue;
    }
    if (/^\s*<script\s+setup\b/.test(line)) {
      if (!/<\/script>\s*$/.test(line)) {
        inSetupScript = true;
      }
      continue;
    }

    if (!removedH1 && /^#\s+/.test(line)) {
      removedH1 = true;
      continue;
    }

    const containerMatch = line.match(
      /^\s*:{3,}\s*([A-Za-z0-9_-]+)(?:\s+(.*?))?\s*$/,
    );
    if (containerMatch) {
      const containerType = containerMatch[1].toLowerCase();
      const containerTitle = stripInlineMarkdown(containerMatch[2] || "");
      if (CONTAINER_TYPES.has(containerType)) {
        const label =
          containerType.charAt(0).toUpperCase() + containerType.slice(1);
        output.push(
          containerTitle ? `**${label}: ${containerTitle}**` : `**${label}**`,
        );
      }
      continue;
    }
    if (/^\s*:{3,}\s*$/.test(line)) {
      continue;
    }

    output.push(line);
  }

  return convertInternalLinks(
    output.join("\n").replace(/\n{3,}/g, "\n\n").trim(),
    document,
  );
}

/**
 * Removes a clean-URL suffix from a site path.
 *
 * @param {string} pathname Site path ending in .md, .html, or index variants.
 * @returns {string} Clean canonical path.
 */
function cleanSitePath(pathname) {
  let cleanPath = pathname.replace(/\.md$/i, "").replace(/\.html$/i, "");
  if (cleanPath === "/index" || cleanPath === "index") {
    return "/";
  }
  if (cleanPath.endsWith("/index")) {
    cleanPath = `${cleanPath.slice(0, -5)}/`;
  }
  return cleanPath || "/";
}

/**
 * Adds the English locale prefix to documentation links without changing assets.
 *
 * @param {string} pathname Site-root path.
 * @param {"zh" | "en"} language Source documentation language.
 * @returns {string} Locale-aware site path.
 */
function localizeSiteRootPath(pathname, language) {
  const cleanPath = cleanSitePath(pathname);
  if (
    language !== "en" ||
    cleanPath === "/en" ||
    cleanPath.startsWith("/en/") ||
    cleanPath.startsWith("/raw/") ||
    cleanPath.startsWith("/api/") ||
    cleanPath.startsWith("/assets/") ||
    cleanPath.startsWith("/llms") ||
    pathname === "/scalar.html"
  ) {
    return cleanPath;
  }

  const hasFileExtension = /\.[A-Za-z0-9]+$/.test(pathname);
  const isDocumentLink =
    pathname === "/" ||
    /\.(?:md|html?)$/i.test(pathname) ||
    !hasFileExtension;
  if (!isDocumentLink) {
    return cleanPath;
  }

  return cleanPath === "/" ? "/en/" : `/en${cleanPath}`;
}

/**
 * Resolves a relative or site-root link from a documentation page.
 *
 * @param {string} target Original Markdown link target.
 * @param {object} document Source document.
 * @returns {string} Absolute URL suitable for full-text output.
 */
function resolveInternalLink(target, document) {
  if (!target) {
    return target;
  }
  if (target.startsWith("#")) {
    return `${document.canonicalUrl}${target}`;
  }
  if (
    target.startsWith("//") ||
    /^[A-Za-z][A-Za-z0-9+.-]*:/.test(target)
  ) {
    return target;
  }

  const suffixMatch = target.match(/([?#].*)$/);
  const suffix = suffixMatch?.[1] || "";
  const pathname = suffix ? target.slice(0, -suffix.length) : target;
  if (!pathname) {
    return target;
  }

  let sitePath;
  if (pathname.startsWith("/")) {
    sitePath = localizeSiteRootPath(pathname, document.language);
  } else {
    const languagePrefix = document.language === "en" ? "/en" : "";
    const baseDirectory = posix.dirname(document.relativePath);
    const resolvedPath = posix.normalize(
      posix.join(baseDirectory === "." ? "" : baseDirectory, pathname),
    );

    if (/\.md$/i.test(pathname)) {
      sitePath = canonicalPathFor(document.language, resolvedPath);
    } else if (/\.html$/i.test(pathname)) {
      sitePath = `${languagePrefix}${cleanSitePath(`/${resolvedPath}`)}`;
    } else {
      sitePath = `${languagePrefix}/${resolvedPath}`.replace(/\/{2,}/g, "/");
    }
  }

  return `${publicUrl(sitePath)}${suffix}`;
}

/**
 * Converts internal links to absolute URLs outside fenced code blocks.
 *
 * @param {string} body Markdown body.
 * @param {object} document Source document.
 * @returns {string} Markdown with absolute internal links.
 */
function convertInternalLinks(body, document) {
  let fence = null;
  return body
    .split("\n")
    .map((line) => {
      const fenceMatch = line.match(/^\s*(`{3,}|~{3,})/);
      if (fence) {
        if (fenceMatch && fenceMatch[1][0] === fence[0]) {
          fence = null;
        }
        return line;
      }
      if (fenceMatch) {
        fence = fenceMatch[1];
        return line;
      }

      return line.replace(
        LINK_RE,
        (match, prefix, target, suffix) =>
          `${prefix}${resolveInternalLink(target, document)}${suffix}`,
      );
    })
    .join("\n");
}

/**
 * Escapes text used inside a generated Markdown link label.
 *
 * @param {string} value Link label.
 * @returns {string} Escaped label.
 */
function escapeLinkLabel(value) {
  return value.replaceAll("\\", "\\\\").replaceAll("[", "\\[");
}

/**
 * Formats one document for a full-text output.
 *
 * @param {object} document Parsed document.
 * @param {number} headingLevel Markdown heading level.
 * @param {string} languageLabel Human-readable language label.
 * @returns {string[]} Markdown output lines.
 */
function formatFullDocument(document, headingLevel, languageLabel) {
  return [
    "---",
    "",
    `${"#".repeat(headingLevel)} [${escapeLinkLabel(document.title)}](${document.canonicalUrl})`,
    "",
    `> Language: ${languageLabel}`,
    `> Source: ${document.canonicalUrl}`,
    `> Raw Markdown: ${document.rawUrl}`,
    "",
    normalizeBody(document),
    "",
  ];
}

/**
 * Builds a complete-language Markdown file.
 *
 * @param {"zh" | "en"} language Documentation language.
 * @param {object[]} documents Canonical documents for the language.
 * @returns {string} Generated full-text content.
 */
function formatLanguageFullText(language, documents) {
  const locale = LOCALES[language];
  const lines = [
    `# ${locale.fullTitle}`,
    "",
    `> ${locale.fullSummary}`,
    "> Generated from the repository Markdown sources.",
    "",
  ];

  for (const document of documents) {
    lines.push(
      ...formatFullDocument(document, 2, locale.label),
    );
  }
  return `${lines.join("\n").trimEnd()}\n`;
}

/**
 * Builds the combined bilingual full-text file.
 *
 * @param {Record<"zh" | "en", object[]>} documentsByLanguage Canonical documents by language.
 * @returns {string} Generated bilingual full-text content.
 */
function formatCombinedFullText(documentsByLanguage) {
  const lines = [
    "# AstrBot Documentation",
    "",
    "> Official AstrBot documentation in Chinese and English.",
    "> Generated from the repository Markdown sources.",
    "",
  ];

  for (const language of Object.keys(LOCALES)) {
    lines.push(`## ${LOCALES[language].label}`, "");
    for (const document of documentsByLanguage[language]) {
      lines.push(
        ...formatFullDocument(document, 3, LOCALES[language].label),
      );
    }
  }
  return `${lines.join("\n").trimEnd()}\n`;
}

/**
 * Groups documents by their first-level source directory.
 *
 * @param {"zh" | "en"} language Documentation language.
 * @param {object[]} documents Parsed documents.
 * @returns {Array<{ key: string, label: string, documents: object[] }>} Categories.
 */
function groupDocuments(language, documents) {
  const groups = new Map();
  for (const document of documents) {
    const key = document.categorySegment;
    if (!groups.has(key)) {
      groups.set(key, []);
    }
    groups.get(key).push(document);
  }

  return [...groups.entries()]
    .map(([key, groupedDocuments]) => ({
      key,
      label:
        CATEGORY_LABELS[language][key] ||
        key.replaceAll("-", " ").replaceAll("_", " "),
      documents: groupedDocuments.sort((left, right) =>
        compareStrings(left.relativePath, right.relativePath),
      ),
    }))
    .sort((left, right) => {
      const leftIndex = CATEGORY_ORDER.indexOf(left.key);
      const rightIndex = CATEGORY_ORDER.indexOf(right.key);
      const leftRank = leftIndex === -1 ? Number.MAX_SAFE_INTEGER : leftIndex;
      const rightRank = rightIndex === -1 ? Number.MAX_SAFE_INTEGER : rightIndex;
      return leftRank - rightRank || compareStrings(left.key, right.key);
    });
}

/**
 * Builds the llms.txt discovery index.
 *
 * @param {Record<"zh" | "en", object[]>} documentsByLanguage Canonical documents by language.
 * @returns {string} Generated llms.txt content.
 */
function formatLlmsIndex(documentsByLanguage) {
  const lines = [
    "# AstrBot Documentation",
    "",
    "> Official AstrBot documentation for deploying, configuring, using, and extending AstrBot.",
    "> Chinese pages use the site root; English pages use the /en/ prefix.",
    "> Fetch individual Markdown when possible, or use a language-specific full text for broader context.",
    "",
    "## Complete Documentation",
    "",
    `- [All documentation](${publicUrl("/llms-full.txt")}): Bilingual full text in one file.`,
    `- [简体中文完整文档](${publicUrl("/llms-zh.txt")}): Chinese documentation in one file.`,
    `- [English documentation](${publicUrl("/llms-en.txt")}): English documentation in one file.`,
    "",
  ];

  for (const language of Object.keys(LOCALES)) {
    lines.push(
      ...groupDocuments(language, documentsByLanguage[language]).flatMap(
        (group) => [
          `## ${LOCALES[language].label} · ${group.label}`,
          "",
          ...group.documents.map((document) => {
            const summary =
              document.summary ||
              (language === "zh"
                ? "AstrBot 官方文档页面。"
                : "Official AstrBot documentation page.");
            return `- [${escapeLinkLabel(document.title)}](${document.canonicalUrl}): ${summary} Markdown: [raw source](${document.rawUrl})`;
          }),
          "",
        ],
      ),
    );
  }

  return `${lines.join("\n").trimEnd()}\n`;
}

/**
 * Enforces a generated file size limit before deployment.
 *
 * @param {string} label Human-readable output name.
 * @param {string} content Generated content.
 * @param {number} limit Maximum allowed UTF-8 bytes.
 * @returns {number} Generated byte size.
 */
function assertSize(label, content, limit) {
  const byteSize = Buffer.byteLength(content);
  if (byteSize > limit) {
    throw new Error(
      `${label} is ${byteSize} bytes, exceeding the ${limit}-byte limit.`,
    );
  }
  return byteSize;
}

/**
 * Checks whether a filesystem path currently exists.
 *
 * @param {string} pathname Filesystem path.
 * @returns {Promise<boolean>} True when the path exists.
 */
async function pathExists(pathname) {
  try {
    await stat(pathname);
    return true;
  } catch (error) {
    if (error.code === "ENOENT") {
      return false;
    }
    throw error;
  }
}

/**
 * Serializes generator runs with a cross-process lock file.
 *
 * @param {string} publicDir VitePress public directory.
 * @returns {Promise<() => Promise<void>>} Lock release function.
 */
async function acquireGeneratorLock(publicDir) {
  await mkdir(publicDir, { recursive: true });
  const lockPath = join(publicDir, GENERATOR_LOCK_FILE);
  const deadline = Date.now() + GENERATOR_LOCK_TIMEOUT_MS;

  while (true) {
    try {
      const handle = await open(lockPath, "wx");
      try {
        await handle.writeFile(`${process.pid}\n`);
      } catch (error) {
        await handle.close();
        await rm(lockPath, { force: true });
        throw error;
      }

      let released = false;
      return async () => {
        if (released) {
          return;
        }
        released = true;
        await handle.close();
        await rm(lockPath, { force: true });
      };
    } catch (error) {
      if (error.code !== "EEXIST") {
        throw error;
      }

      let isStale = false;
      try {
        const [lockContent, lockStat] = await Promise.all([
          readFile(lockPath, "utf8"),
          stat(lockPath),
        ]);
        const ownerPid = Number.parseInt(lockContent.trim(), 10);
        if (Number.isInteger(ownerPid) && ownerPid > 0) {
          try {
            process.kill(ownerPid, 0);
          } catch (ownerError) {
            isStale = ownerError.code === "ESRCH";
          }
        }
        if (Date.now() - lockStat.mtimeMs > GENERATOR_LOCK_STALE_MS) {
          isStale = true;
        }
      } catch (lockError) {
        if (lockError.code === "ENOENT") {
          continue;
        }
        isStale = true;
      }

      if (isStale) {
        await rm(lockPath, { force: true });
        continue;
      }
      if (Date.now() >= deadline) {
        throw new Error(
          `Timed out waiting for the llms generator lock at ${lockPath}.`,
        );
      }
      await delay(100);
    }
  }
}

/**
 * Publishes fully staged outputs while preserving the previous version on error.
 *
 * @param {string} stagingDir Completed staging directory.
 * @param {string} publicDir VitePress public directory.
 * @returns {Promise<void>} Resolves after outputs are published.
 */
async function publishGeneratedOutputs(stagingDir, publicDir) {
  const backupDir = join(publicDir, `.llms-backup-${randomUUID()}`);
  const rawRoot = join(publicDir, "raw");
  const stagedRawRoot = join(stagingDir, "raw");
  const stagedRawFiles = await collectMarkdownFiles(stagedRawRoot);
  const stagedRawFileSet = new Set(stagedRawFiles);
  const previousRawFiles = (await pathExists(rawRoot))
    ? await collectMarkdownFiles(rawRoot)
    : [];
  const movedToBackup = [];
  const installedOutputs = [];
  let canCleanupBackup = false;

  await mkdir(backupDir, { recursive: true });
  try {
    for (const relativePath of stagedRawFiles) {
      const outputPath = join(rawRoot, ...relativePath.split("/"));
      await mkdir(dirname(outputPath), { recursive: true });
      if (await pathExists(outputPath)) {
        const backupPath = join(
          backupDir,
          "raw",
          ...relativePath.split("/"),
        );
        await mkdir(dirname(backupPath), { recursive: true });
        await rename(outputPath, backupPath);
        movedToBackup.push({ original: outputPath, backup: backupPath });
      }
      await rename(
        join(stagedRawRoot, ...relativePath.split("/")),
        outputPath,
      );
      installedOutputs.push(outputPath);
    }

    for (const relativePath of previousRawFiles) {
      if (stagedRawFileSet.has(relativePath)) {
        continue;
      }
      const outputPath = join(rawRoot, ...relativePath.split("/"));
      if (await pathExists(outputPath)) {
        const backupPath = join(
          backupDir,
          "raw",
          ...relativePath.split("/"),
        );
        await mkdir(dirname(backupPath), { recursive: true });
        await rename(outputPath, backupPath);
        movedToBackup.push({ original: outputPath, backup: backupPath });
      }
    }

    for (const filename of GENERATED_TEXT_FILES) {
      const outputPath = join(publicDir, filename);
      if (await pathExists(outputPath)) {
        const backupPath = join(backupDir, filename);
        await rename(outputPath, backupPath);
        movedToBackup.push({ original: outputPath, backup: backupPath });
      }
      await rename(join(stagingDir, filename), outputPath);
      installedOutputs.push(outputPath);
    }
    canCleanupBackup = true;
  } catch (error) {
    const restorationErrors = [];
    for (const outputPath of installedOutputs.reverse()) {
      try {
        await rm(outputPath, { recursive: true, force: true });
      } catch (restoreError) {
        restorationErrors.push(restoreError);
      }
    }
    for (const { original, backup } of movedToBackup.reverse()) {
      try {
        await rename(backup, original);
      } catch (restoreError) {
        restorationErrors.push(restoreError);
      }
    }
    if (restorationErrors.length > 0) {
      throw new AggregateError(
        [error, ...restorationErrors],
        `Failed to publish generated documentation and restore the previous outputs. Backups remain at ${backupDir}.`,
      );
    }
    canCleanupBackup = true;
    throw error;
  } finally {
    if (canCleanupBackup) {
      await rm(backupDir, { recursive: true, force: true });
    }
  }
}

/**
 * Generates llms discovery files and raw Markdown under the public directory.
 *
 * @param {object} [options] Generator options.
 * @param {string} [options.docsRoot] Documentation source directory.
 * @param {string} [options.publicDir] VitePress public directory.
 * @param {number} [options.maxLanguageBytes] Per-language full-text limit.
 * @param {number} [options.maxFullBytes] Combined full-text limit.
 * @returns {Promise<object>} Generation summary.
 */
export async function generateLlms({
  docsRoot = DOCS_ROOT,
  publicDir = DEFAULT_PUBLIC_DIR,
  maxLanguageBytes = MAX_LANGUAGE_BYTES,
  maxFullBytes = MAX_FULL_BYTES,
} = {}) {
  const allDocuments = [];

  for (const language of Object.keys(LOCALES)) {
    const languageRoot = join(docsRoot, language);
    const markdownFiles = await collectMarkdownFiles(languageRoot);
    for (const relativePath of markdownFiles) {
      const sourceBuffer = await readFile(join(languageRoot, relativePath));
      allDocuments.push(parseDocument(language, relativePath, sourceBuffer));
    }
  }

  const documentsByLanguage = Object.fromEntries(
    Object.keys(LOCALES).map((language) => [
      language,
      allDocuments
        .filter(
          (document) =>
            document.language === language && isCanonicalDocument(document),
        )
        .sort((left, right) =>
          compareStrings(left.relativePath, right.relativePath),
        ),
    ]),
  );

  const languageFullText = Object.fromEntries(
    Object.keys(LOCALES).map((language) => [
      language,
      formatLanguageFullText(language, documentsByLanguage[language]),
    ]),
  );
  const combinedFullText = formatCombinedFullText(documentsByLanguage);
  const llmsIndex = formatLlmsIndex(documentsByLanguage);

  const sizes = {
    zh: assertSize(
      "Chinese full documentation",
      languageFullText.zh,
      maxLanguageBytes,
    ),
    en: assertSize(
      "English full documentation",
      languageFullText.en,
      maxLanguageBytes,
    ),
    full: assertSize(
      "Combined full documentation",
      combinedFullText,
      maxFullBytes,
    ),
    index: Buffer.byteLength(llmsIndex),
  };

  const releaseLock = await acquireGeneratorLock(publicDir);
  const stagingDir = join(publicDir, `.llms-staging-${randomUUID()}`);
  const stagedRawRoot = join(stagingDir, "raw");
  try {
    await mkdir(stagedRawRoot, { recursive: true });

    for (const document of allDocuments) {
      if (document.isDraft) {
        continue;
      }
      const rawOutputPath = join(
        stagedRawRoot,
        document.language,
        ...document.relativePath.split("/"),
      );
      await mkdir(dirname(rawOutputPath), { recursive: true });
      await writeFile(rawOutputPath, document.sourceBuffer);
    }

    await Promise.all([
      writeFile(join(stagingDir, "llms.txt"), llmsIndex),
      writeFile(join(stagingDir, "llms-full.txt"), combinedFullText),
      writeFile(join(stagingDir, "llms-zh.txt"), languageFullText.zh),
      writeFile(join(stagingDir, "llms-en.txt"), languageFullText.en),
    ]);

    await publishGeneratedOutputs(stagingDir, publicDir);
  } finally {
    await rm(stagingDir, { recursive: true, force: true });
    await releaseLock();
  }

  return {
    sourceDocuments: allDocuments.length,
    canonicalDocuments: allDocuments.filter(isCanonicalDocument).length,
    rawDocuments: allDocuments.filter((document) => !document.isDraft).length,
    sizes,
  };
}

if (resolve(process.argv[1] || "") === resolve(SCRIPT_PATH)) {
  generateLlms()
    .then((result) => {
      console.log(
        `Generated ${result.rawDocuments} raw Markdown files and llms.txt for ${result.canonicalDocuments} canonical pages.`,
      );
    })
    .catch((error) => {
      console.error(error);
      process.exitCode = 1;
    });
}
