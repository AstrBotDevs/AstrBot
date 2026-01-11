/**
 * Some plugin READMEs (including the reference repo) use a centered HTML block like:
 *   <div align="center">
 *     ![Version](...) ![License](...)
 *     **...**
 *   </div>
 *
 * markdown-it (and thus markstream-vue) treats HTML blocks as `html_block`,
 * and it will NOT parse markdown syntax inside the HTML block.
 * Result: badges show up as raw `![...]()` text.
 *
 * This preprocessor converts a small subset of markdown inside centered HTML blocks
 * into equivalent HTML so it can render correctly without changing the markdown parser.
 *
 * Scope: only touches blocks that have `align="center"` and contain markdown image syntax.
 */

export type PreprocessPluginMarkdownOptions = {
  /**
   * When provided, rewrites relative asset URLs in markdown/HTML to absolute URLs.
   * Example: https://raw.githubusercontent.com/AstrBotDevs/AstrBot/master/
   */
  baseUrl?: string;
};

export function preprocessPluginMarkdown(
  markdown: string,
  options?: PreprocessPluginMarkdownOptions,
): string {
  if (!markdown) return markdown;

  const baseUrl = normalizeBaseUrl(options?.baseUrl);
  let text = String(markdown);

  // 0) 修复破损的 closing tag（上游 README 末尾存在 `</div` 缺少 `>` 的情况）。
  // 这会导致 markdown-it 将后续内容整体吞进 html_block，从而把图片语法当纯文本渲染。
  text = fixBrokenHtmlClosingTags(text);

  // 0.1) markdown-it 的 html_block 结束条件非常严格：closing tag 必须从行首开始。
  // 上游 README 中存在缩进的 `</div>`（或其它 block tag），会导致 HTML block 无法正确结束，
  // 从而把后续大段 Markdown 当作纯文本（例如 `![...](...)`）渲染。
  text = normalizeHtmlBlockClosingTags(text);

  // 1) 修复非标准的 <img ... href="..."> 标签（上游 README 中存在此类写法）
  // 将其转换为标准的 <a href="..."><img ...></a>
  text = text.replace(
    /<img\b([^>]*?)\bhref="([^"]+)"([^>]*?)>/gi,
    '<a href="$2"><img$1$3 /></a>',
  );

  // 2) 处理 <div align="center"> / <p align="center"> 块
  // 由于 markdown-it 会跳过 HTML 块内部的 Markdown 解析，我们需要手动转换内部的常用语法。
  // 注意：上游 README 的 center block 内部存在嵌套 <div>，用正则会“提前遇到第一个 </div> 就结束”，从而破坏后续 markdown 解析。
  text = replaceAlignedCenterHtmlBlocks(text, (tag, attrs, inner) => {
    let converted = replaceMarkdownImagesWithHtml(inner, baseUrl);
    converted = replaceMarkdownStrongWithHtml(converted);
    converted = replaceMarkdownLinksWithHtml(converted);

    // markdown-it 的 html_block 对 <div> 不做嵌套匹配：align="center" 块里如果再出现
    // 纯 <div> / </div> 包裹行，会导致 outer html_block 提前结束或后续整篇被吞进 html_block。
    // 这里直接移除 inner 中的 <div> / </div> 包裹行（仅限 align="center" 的 inner），保留内容本身。
    converted = stripInnerDivWrapperLines(converted);

    // markdown-it's html_block rule only recognizes a closing tag when it starts a new line.
    // Keep the closing tag at BOL to avoid swallowing subsequent markdown as raw text.
    return `<${tag}${attrs}>\n${converted}\n</${tag}>\n\n`;
  });

  // 3) 将 markdown 图片语法中相对路径改写为绝对 URL
  text = rewriteMarkdownImageUrls(text, baseUrl);

  // 4) 将 HTML 标签内的 src/srcset 相对路径改写为绝对 URL（处理 <img>/<picture>/<source> 等）
  text = rewriteHtmlAssetUrls(text, baseUrl);

  return text;
}

function replaceMarkdownStrongWithHtml(text: string): string {
  return text
    .replace(/\*\*([^*]+?)\*\*/g, "<strong>$1</strong>")
    .replace(/__([^_]+?)__/g, "<strong>$1</strong>");
}

type ReplaceMarkdownLinksOptions = {
  /**
   * When true, only converts links whose label already contains HTML (e.g. "<img .../>").
   * This is used after converting markdown images to HTML, to handle [<img .../>](href)
   * without affecting normal markdown links.
   */
  onlyWhenLabelHasHtml?: boolean;
};

function replaceMarkdownLinksWithHtml(
  text: string,
  options?: ReplaceMarkdownLinksOptions,
): string {
  // Convert markdown links to HTML anchors for content inside html_block.
  // Must handle both:
  //   [text](href)
  //   [![alt](img)](href)  (after image conversion: [<img ... />](href))
  //
  // Regex-based replacement is too fragile for nested constructs and can corrupt HTML,
  // which then causes markdown-it to treat the rest of the document as html_block.
  const onlyWhenLabelHasHtml = options?.onlyWhenLabelHasHtml ?? false;

  let result = "";
  let i = 0;

  while (i < text.length) {
    const open = text.indexOf("[", i);
    if (open === -1) {
      result += text.slice(i);
      break;
    }

    // Skip image syntax: ![alt](...)
    if (open > 0 && text[open - 1] === "!") {
      result += text.slice(i, open + 1);
      i = open + 1;
      continue;
    }

    result += text.slice(i, open);

    const close = findMatchingBracket(text, open + 1);
    if (close === -1 || close + 1 >= text.length || text[close + 1] !== "(") {
      result += "[";
      i = open + 1;
      continue;
    }

    const label = text.slice(open + 1, close);
    const urlStart = close + 2;

    const { url, endIndex } = readBalancedParensUrl(text, urlStart);
    if (!url || endIndex === -1) {
      result += text.slice(open, urlStart);
      i = urlStart;
      continue;
    }

    if (onlyWhenLabelHasHtml && !label.includes("<")) {
      result += text.slice(open, endIndex + 1);
      i = endIndex + 1;
      continue;
    }

    const { urlPart, trailing } = splitMarkdownLinkDestination(url.trim());
    const href = escapeHtmlAttr(urlPart);
    const titleAttr = toOptionalTitleAttr(trailing);

    const innerHtml = label.includes("<") ? label : escapeHtmlText(label);
    result += `<a href="${href}"${titleAttr}>${innerHtml}</a>`;

    i = endIndex + 1;
  }

  return result;
}


function replaceMarkdownImagesWithHtml(text: string, baseUrl?: string): string {
  // Convert markdown image syntax to HTML img to make it render inside markdown-it html_block.
  // Supports: ![Alt](url) and ![Alt](url "title")
  let result = "";
  let i = 0;

  while (i < text.length) {
    const start = text.indexOf("![", i);
    if (start === -1) {
      result += text.slice(i);
      break;
    }

    // Copy preceding text
    result += text.slice(i, start);

    const altStart = start + 2;
    const altEnd = text.indexOf("]", altStart);
    if (altEnd === -1 || altEnd + 1 >= text.length || text[altEnd + 1] !== "(") {
      result += text.slice(start, start + 2);
      i = altStart;
      continue;
    }

    const alt = text.slice(altStart, altEnd);
    const urlStart = altEnd + 2;

    const { url, endIndex } = readBalancedParensUrl(text, urlStart);
    if (!url || endIndex === -1) {
      result += text.slice(start, altEnd + 2);
      i = urlStart;
      continue;
    }

    const { urlPart, trailing } = splitMarkdownLinkDestination(url.trim());
    const resolvedUrl = resolveRelativeUrl(urlPart, baseUrl);

    const safeAlt = escapeHtmlAttr(alt);
    const safeUrl = escapeHtmlAttr(resolvedUrl);
    const titleAttr = toOptionalTitleAttr(trailing);

    result += `<img alt="${safeAlt}" src="${safeUrl}"${titleAttr} />`;
    i = endIndex + 1;
  }

  return result;
}

function readBalancedParensUrl(
  text: string,
  startIndex: number,
): { url: string; endIndex: number } {
  // Reads until the matching ')' considering nested parentheses in URLs.
  let depth = 1;
  for (let i = startIndex; i < text.length; i++) {
    const ch = text[i];
    if (ch === "(") depth++;
    else if (ch === ")") {
      depth--;
      if (depth === 0) {
        return { url: text.slice(startIndex, i), endIndex: i };
      }
    }
  }
  return { url: "", endIndex: -1 };
}

function escapeHtmlAttr(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}
function escapeHtmlText(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function findMatchingBracket(text: string, startIndex: number): number {
  // Find the matching ']' for a link label, allowing nested brackets.
  let depth = 0;
  for (let i = startIndex; i < text.length; i++) {
    const ch = text[i];
    if (ch === "[") depth += 1;
    else if (ch === "]") {
      if (depth === 0) return i;
      depth -= 1;
    }
  }
  return -1;
}

type CenterBlockReplacer = (tag: string, attrs: string, inner: string) => string;

function replaceAlignedCenterHtmlBlocks(text: string, replacer: CenterBlockReplacer): string {
  const openTagRegex =
    /<(div|p)\b([^>]*\balign\s*=\s*(?:"center"|'center')[^>]*?)>/gi;

  let result = "";
  let lastIndex = 0;

  for (;;) {
    const match = openTagRegex.exec(text);
    if (!match) break;

    const matchIndex = match.index ?? 0;
    const tag = String(match[1]);
    const attrs = String(match[2] ?? "");
    const openTagText = String(match[0]);

    const contentStart = matchIndex + openTagText.length;
    const closeTagStart = findMatchingCloseTagStart(text, tag, contentStart);
    if (closeTagStart === -1) continue;

    const closeTagEnd = text.indexOf(">", closeTagStart);
    if (closeTagEnd === -1) continue;

    result += text.slice(lastIndex, matchIndex);

    const inner = text.slice(contentStart, closeTagStart);
    result += replacer(tag, attrs, inner);

    lastIndex = closeTagEnd + 1;
    openTagRegex.lastIndex = lastIndex;
  }

  result += text.slice(lastIndex);
  return result;
}

function findMatchingCloseTagStart(text: string, tag: string, startIndex: number): number {
  const lowerTag = tag.toLowerCase();
  let depth = 1;
  let i = startIndex;

  while (i < text.length) {
    const lt = text.indexOf("<", i);
    if (lt === -1) return -1;

    // Skip HTML comments
    if (text.startsWith("<!--", lt)) {
      const end = text.indexOf("-->", lt + 4);
      i = end === -1 ? text.length : end + 3;
      continue;
    }

    const snippet = text.slice(lt, Math.min(text.length, lt + lowerTag.length + 3)).toLowerCase();

    // Closing tag: </div> or </p>
    if (snippet.startsWith(`</${lowerTag}`)) {
      depth -= 1;
      if (depth === 0) return lt;
      i = lt + 2;
      continue;
    }

    // Opening tag: <div ...> or <p ...>
    if (snippet.startsWith(`<${lowerTag}`)) {
      const next = text[lt + 1 + lowerTag.length] ?? "";
      // Ensure boundary: whitespace, '>' or '/'
      if (next === ">" || next === "/" || /\s/.test(next)) {
        depth += 1;
      }
      i = lt + 1;
      continue;
    }

    i = lt + 1;
  }

  return -1;
}

function fixBrokenHtmlClosingTags(text: string): string {
  // Fix cases like:
  //   </div\n   or  </div\r\n   (missing closing '>')
  // This pattern appears in the upstream README and breaks markdown-it parsing.
  const tags = "(div|p|details|summary|table|picture|section|article|center)";
  const missingGtBeforeLineBreak = new RegExp(`</${tags}\\s*(?=\\r?\\n)`, "gi");
  const missingGtAtEof = new RegExp(`</${tags}\\s*$`, "gi");

  return text
    .replace(missingGtBeforeLineBreak, "</$1>")
    .replace(missingGtAtEof, "</$1>");
}

function normalizeHtmlBlockClosingTags(text: string): string {
  // markdown-it's html_block rule only recognizes a closing tag when it starts at BOL.
  // To avoid swallowing subsequent markdown as raw text, normalize indented closing tags:
  //   "  </div>" -> "</div>"
  // Skip fenced code blocks (``` / ~~~) to avoid rewriting examples.
  const lines = text.split("\n");

  let out = "";

  let inFence = false;
  let fenceChar: "`" | "~" | null = null;
  let fenceLen = 0;

  const closingTagLine = /^[ \t]+<\/(div|p|details|summary|table|picture|section|article|center)>\s*$/i;

  for (let lineIndex = 0; lineIndex < lines.length; lineIndex++) {
    const line = lines[lineIndex];
    const lineWithNl = lineIndex < lines.length - 1 ? `${line}\n` : line;

    const fenceMatch = line.match(/^[ \t]*([`~]{3,})/);
    if (fenceMatch) {
      const marker = fenceMatch[1];
      const ch = marker[0] as "`" | "~";

      if (!inFence) {
        inFence = true;
        fenceChar = ch;
        fenceLen = marker.length;
        out += lineWithNl;
        continue;
      }

      if (fenceChar === ch && marker.length >= fenceLen) {
        out += lineWithNl;
        inFence = false;
        fenceChar = null;
        fenceLen = 0;
        continue;
      }
    }

    if (inFence) {
      out += lineWithNl;
      continue;
    }

    const match = line.match(closingTagLine);
    if (match) {
      out += `</${match[1]}>\n`;
      continue;
    }

    out += lineWithNl;
  }

  return out;
}

function stripInnerDivWrapperLines(inner: string): string {
  // Only strips lines that are just "<div ...>" or "</div>" (optionally surrounded by whitespace).
  // This is specifically to avoid markdown-it html_block prematurely terminating on nested </div>,
  // or swallowing the rest of the document if nested <div> is not properly closed.
  return inner
    .replace(/^[ \t]*<div\b[^>]*>[ \t]*\r?$/gim, "")
    .replace(/^[ \t]*<\/div>[ \t]*\r?$/gim, "");
}

function normalizeBaseUrl(baseUrl?: string): string | undefined {
  if (!baseUrl) return undefined;
  const trimmed = String(baseUrl).trim();
  if (!trimmed) return undefined;
  return trimmed.endsWith("/") ? trimmed : `${trimmed}/`;
}

function isAbsoluteOrSpecialUrl(url: string): boolean {
  const trimmed = url.trim();
  if (!trimmed) return true;
  if (trimmed.startsWith("#")) return true;
  if (trimmed.startsWith("//")) return true;
  return /^[a-z][a-z0-9+.-]*:/i.test(trimmed);
}

function resolveRelativeUrl(url: string, baseUrl?: string): string {
  if (!baseUrl) return url;
  const trimmed = url.trim();
  if (!trimmed) return url;
  if (isAbsoluteOrSpecialUrl(trimmed)) return url;

  try {
    if (trimmed.startsWith("/")) {
      return new URL(trimmed.slice(1), baseUrl).toString();
    }
    return new URL(trimmed, baseUrl).toString();
  } catch {
    return url;
  }
}

function splitMarkdownLinkDestination(dest: string): {
  urlPart: string;
  trailing: string;
} {
  // Handles: url "title" | url 'title' (common patterns)
  const match = dest.match(/^(\S+)(\s+["'][\s\S]*["'])$/);
  if (!match) return { urlPart: dest, trailing: "" };
  return { urlPart: match[1], trailing: match[2] };
}

function toOptionalTitleAttr(trailing: string): string {
  const trimmed = trailing.trim();
  if (!trimmed) return "";
  const match = trimmed.match(/^["']([\s\S]*)["']$/);
  if (!match) return "";
  return ` title="${escapeHtmlAttr(match[1])}"`;
}

function rewriteMarkdownImageUrls(text: string, baseUrl?: string): string {
  if (!baseUrl) return text;

  let result = "";
  let i = 0;

  while (i < text.length) {
    const start = text.indexOf("![", i);
    if (start === -1) {
      result += text.slice(i);
      break;
    }

    result += text.slice(i, start);

    const altStart = start + 2;
    const altEnd = text.indexOf("]", altStart);
    if (altEnd === -1 || altEnd + 1 >= text.length || text[altEnd + 1] !== "(") {
      result += text.slice(start, start + 2);
      i = altStart;
      continue;
    }

    const alt = text.slice(altStart, altEnd);
    const urlStart = altEnd + 2;

    const { url, endIndex } = readBalancedParensUrl(text, urlStart);
    if (!url || endIndex === -1) {
      result += text.slice(start, altEnd + 2);
      i = urlStart;
      continue;
    }

    const { urlPart, trailing } = splitMarkdownLinkDestination(url.trim());
    const resolvedUrl = resolveRelativeUrl(urlPart, baseUrl);

    result += `![${alt}](${resolvedUrl}${trailing})`;
    i = endIndex + 1;
  }

  return result;
}

function rewriteHtmlAssetUrls(text: string, baseUrl?: string): string {
  if (!baseUrl) return text;

  // Rewrite src attributes (images/media), but DO NOT rewrite href (links).
  let out = text.replace(
    /\bsrc\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))/gi,
    (_match, v1, v2, v3) => {
      const rawValue = (v1 ?? v2 ?? v3 ?? "").trim();
      const quote = v1 != null ? '"' : v2 != null ? "'" : "";
      const resolved = resolveRelativeUrl(rawValue, baseUrl);
      if (quote) return `src=${quote}${resolved}${quote}`;
      return `src=${resolved}`;
    },
  );

  // Rewrite srcset (supports: "a 1x, b 2x")
  out = out.replace(
    /\bsrcset\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))/gi,
    (_match, v1, v2, v3) => {
      const rawValue = (v1 ?? v2 ?? v3 ?? "").trim();
      const quote = v1 != null ? '"' : v2 != null ? "'" : "";
      const rewritten = rawValue
        .split(",")
        .map((part: string) => {
          const trimmed = part.trim();
          if (!trimmed) return trimmed;
          const pieces = trimmed.split(/\s+/);
          const first = pieces.shift() ?? "";
          const resolved = resolveRelativeUrl(first, baseUrl);
          return [resolved, ...pieces].join(" ");
        })
        .join(", ");
      if (quote) return `srcset=${quote}${rewritten}${quote}`;
      return `srcset=${rewritten}`;
    },
  );

  return out;
}