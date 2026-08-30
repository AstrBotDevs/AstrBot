import { createHash } from 'node:crypto';
import {
  mkdtemp,
  mkdir,
  readFile,
  readdir,
  rename,
  rm,
  writeFile,
} from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { basename, dirname, extname, join, relative, resolve } from 'node:path';
import { inflateRawSync } from 'node:zlib';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const subsetFont = require('subset-font');

const __dirname = fileURLToPath(new URL('.', import.meta.url));
const DASHBOARD_ROOT = resolve(__dirname, '..');
const SOURCE_ROOT = join(DASHBOARD_ROOT, 'src');
const LOCALES_ROOT = join(SOURCE_ROOT, 'i18n', 'locales', 'zh-CN');
const FONT_ROOT = join(SOURCE_ROOT, 'assets', 'fonts');
const FONT_FILES = join(FONT_ROOT, 'files');
const FONT_METADATA = join(FONT_ROOT, 'sources.json');

const ASCII_AND_PUNCTUATION =
  ' !"#$%&\'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~\n\r\t';
const NOTO_UNICODE_RANGES = [
  [0x0000, 0x2fff],
  [0x3000, 0x4dff],
  [0x4e00, 0x6fff],
  [0x7000, 0x9fff],
  [0xa000, 0xffff],
  [0x10000, 0x1ffff],
  [0x20000, 0x2ffff],
  [0x30000, 0x3ffff],
  [0x40000, 0x10ffff],
];

export const FONT_SOURCES = {
  noto: {
    repository: 'https://github.com/notofonts/noto-cjk',
    releaseTag: 'Sans2.004',
    archiveUrl:
      'https://github.com/notofonts/noto-cjk/releases/download/Sans2.004/18_NotoSansSC.zip',
    archiveSha256:
      '4d107c09ada479d3e48b6e78c83835773cbd9214bf6e12cdb7b60f8e068292ec',
    licenseFile: 'LICENSE',
    licenseSha256:
      '6a73f9541c2de74158c0e7cf6b0a58ef774f5a780bf191f2d7ec9cc53efe2bf2',
    files: {
      regular: {
        name: 'NotoSansSC-Regular.otf',
        sha256:
          'faa6c9df652116dde789d351359f3d7e5d2285a2b2a1f04a2d7244df706d5ea9',
      },
      bold: {
        name: 'NotoSansSC-Bold.otf',
        sha256:
          'c6cb5a93abaa9edc8ee7463b7ebb7f42d618d40e6ed2f7a5371c97b0b64767c0',
      },
    },
  },
  maple: {
    repository: 'https://github.com/subframe7536/maple-font',
    releaseTag: 'v7.9',
    archiveUrl:
      'https://github.com/subframe7536/maple-font/releases/download/v7.9/MapleMono-Woff2.zip',
    archiveSha256:
      '5e38e83b007e7157c253c3f57c0a6f80415378f4859d43eb3cf4b1d858001681',
    licenseFile: 'LICENSE.txt',
    licenseSha256:
      'eb2d28d2e565a0757e3d64e34ebb452e75a0cad87c0ab3faf4e08ba7596de902',
    files: {
      regular: {
        name: 'MapleMono-Regular.ttf.woff2',
        sha256:
          'cc92b4284346c9ef924eaaa9f457d558c3dc68d132911403e94f8f498d529e9f',
      },
      bold: {
        name: 'MapleMono-Bold.ttf.woff2',
        sha256:
          'f6233931b1d0069b125a2bb119735fa0eca3e262d76df9e2ad905470a3d70130',
      },
      italic: {
        name: 'MapleMono-Italic.ttf.woff2',
        sha256:
          '6017607745733b64b023105ea593b5d0b9f7a98743694e79b6ab674210634e6d',
      },
    },
  },
};

function sha256(buffer) {
  return createHash('sha256').update(buffer).digest('hex');
}

function assertHash(buffer, expected, label) {
  const actual = sha256(buffer);
  if (actual !== expected) {
    throw new Error(
      `${label} SHA-256 mismatch: expected ${expected}, got ${actual}`,
    );
  }
}

async function fetchVerifiedArchive(source, tempDir) {
  const response = await fetch(source.archiveUrl, { redirect: 'follow' });
  if (!response.ok) {
    throw new Error(
      `Failed to download ${source.archiveUrl}: ${response.status}`,
    );
  }
  const archive = Buffer.from(await response.arrayBuffer());
  assertHash(archive, source.archiveSha256, source.archiveUrl);
  await writeFile(
    join(tempDir, basename(new URL(source.archiveUrl).pathname)),
    archive,
  );
  return archive;
}

function extractZipEntries(archive) {
  const minimumEocdSize = 22;
  let eocdOffset = -1;
  for (
    let offset = archive.length - minimumEocdSize;
    offset >= 0;
    offset -= 1
  ) {
    if (archive.readUInt32LE(offset) === 0x06054b50) {
      eocdOffset = offset;
      break;
    }
  }
  if (eocdOffset < 0)
    throw new Error('ZIP end-of-central-directory record was not found');

  const entryCount = archive.readUInt16LE(eocdOffset + 10);
  let offset = archive.readUInt32LE(eocdOffset + 16);
  const entries = new Map();
  for (let index = 0; index < entryCount; index += 1) {
    if (archive.readUInt32LE(offset) !== 0x02014b50) {
      throw new Error('Invalid ZIP central-directory entry');
    }
    const compression = archive.readUInt16LE(offset + 10);
    const compressedSize = archive.readUInt32LE(offset + 20);
    const fileNameLength = archive.readUInt16LE(offset + 28);
    const extraLength = archive.readUInt16LE(offset + 30);
    const commentLength = archive.readUInt16LE(offset + 32);
    const localOffset = archive.readUInt32LE(offset + 42);
    const name = archive
      .subarray(offset + 46, offset + 46 + fileNameLength)
      .toString('utf8');
    if (archive.readUInt32LE(localOffset) !== 0x04034b50) {
      throw new Error(`Invalid ZIP local entry for ${name}`);
    }
    const localNameLength = archive.readUInt16LE(localOffset + 26);
    const localExtraLength = archive.readUInt16LE(localOffset + 28);
    const dataStart = localOffset + 30 + localNameLength + localExtraLength;
    const compressed = archive.subarray(dataStart, dataStart + compressedSize);
    if (compression === 0) entries.set(name, compressed);
    else if (compression === 8) entries.set(name, inflateRawSync(compressed));
    else
      throw new Error(
        `Unsupported ZIP compression method ${compression} for ${name}`,
      );
    offset += 46 + fileNameLength + extraLength + commentLength;
  }
  return entries;
}

function zipEntry(entries, fileName) {
  const entry = entries.get(fileName);
  if (!entry)
    throw new Error(`Required archive entry ${fileName} was not found`);
  return entry;
}

export function collectOtfUnicodeRanges(font) {
  const tableCount = font.readUInt16BE(4);
  let cmapOffset;
  for (let index = 0; index < tableCount; index += 1) {
    const offset = 12 + index * 16;
    if (font.subarray(offset, offset + 4).toString('ascii') === 'cmap') {
      cmapOffset = font.readUInt32BE(offset + 8);
      break;
    }
  }
  if (cmapOffset === undefined)
    throw new Error('The source font does not contain a cmap table');

  const records = font.readUInt16BE(cmapOffset + 2);
  let format12Offset;
  let format4Offset;
  for (let index = 0; index < records; index += 1) {
    const offset = cmapOffset + 4 + index * 8;
    const subtableOffset = cmapOffset + font.readUInt32BE(offset + 4);
    const format = font.readUInt16BE(subtableOffset);
    if (format === 12) {
      format12Offset = subtableOffset;
      break;
    }
    if (format === 4 && format4Offset === undefined)
      format4Offset = subtableOffset;
  }
  if (format12Offset === undefined && format4Offset === undefined) {
    throw new Error('The source font does not contain a supported cmap');
  }

  const ranges = [];
  if (format12Offset !== undefined) {
    const groupCount = font.readUInt32BE(format12Offset + 12);
    for (let index = 0; index < groupCount; index += 1) {
      const offset = format12Offset + 16 + index * 12;
      ranges.push([font.readUInt32BE(offset), font.readUInt32BE(offset + 4)]);
    }
    return ranges;
  }

  const segmentCount = font.readUInt16BE(format4Offset + 6) / 2;
  const endCodesOffset = format4Offset + 14;
  const startCodesOffset = endCodesOffset + segmentCount * 2 + 2;
  const deltasOffset = startCodesOffset + segmentCount * 2;
  const rangeOffsetsOffset = deltasOffset + segmentCount * 2;
  for (let index = 0; index < segmentCount; index += 1) {
    const start = font.readUInt16BE(startCodesOffset + index * 2);
    const end = font.readUInt16BE(endCodesOffset + index * 2);
    const delta = font.readInt16BE(deltasOffset + index * 2);
    const rangeOffset = font.readUInt16BE(rangeOffsetsOffset + index * 2);
    let rangeStart;
    for (let codePoint = start; codePoint <= end; codePoint += 1) {
      let glyph = 0;
      if (rangeOffset === 0) glyph = (codePoint + delta) & 0xffff;
      else {
        const glyphOffset =
          rangeOffsetsOffset +
          index * 2 +
          rangeOffset +
          (codePoint - start) * 2;
        glyph = font.readUInt16BE(glyphOffset);
        if (glyph !== 0) glyph = (glyph + delta) & 0xffff;
      }
      if (glyph !== 0 && codePoint !== 0xffff) {
        if (rangeStart === undefined) rangeStart = codePoint;
      } else if (rangeStart !== undefined) {
        ranges.push([rangeStart, codePoint - 1]);
        rangeStart = undefined;
      }
    }
    if (rangeStart !== undefined) ranges.push([rangeStart, end]);
  }
  return ranges;
}

function charactersForRange(sourceRanges, start, end) {
  const characters = [];
  for (const [rangeStart, rangeEnd] of sourceRanges) {
    const from = Math.max(start, rangeStart);
    const to = Math.min(end, rangeEnd);
    for (let codePoint = from; codePoint <= to; codePoint += 1) {
      if (codePoint !== 0 && (codePoint < 0xd800 || codePoint > 0xdfff)) {
        characters.push(String.fromCodePoint(codePoint));
      }
    }
  }
  return characters.join('');
}

async function collectFiles(directory, extension, files = []) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) await collectFiles(path, extension, files);
    else if (extension.includes(extname(entry.name))) files.push(path);
  }
  return files;
}

export async function collectUiCharacters() {
  const files = await collectFiles(LOCALES_ROOT, ['.json', '.ts']);
  const text = await Promise.all(files.map((file) => readFile(file, 'utf8')));
  return [...new Set([...ASCII_AND_PUNCTUATION, ...text.join('')])]
    .filter((character) => character.codePointAt(0) >= 0x20)
    .sort((left, right) => left.codePointAt(0) - right.codePointAt(0));
}

function unicodeRange(start, end) {
  return `U+${start.toString(16).toUpperCase().padStart(4, '0')}-${end
    .toString(16)
    .toUpperCase()
    .padStart(4, '0')}`;
}

function fontFace(family, fileName, weight, style = 'normal', range) {
  return `@font-face {\n  font-family: "${family}";\n  src: url("./files/${fileName}") format("woff2");\n  font-weight: ${weight};\n  font-style: ${style};\n  font-display: swap;${range ? `\n  unicode-range: ${range};` : ''}\n}\n`;
}

function buildCss(notoFiles) {
  let css = '/* Generated by pnpm fonts:update. Do not edit manually. */\n\n';
  css += fontFace('AstrBot UI', 'astrbot-ui-regular.woff2', 400);
  css += '\n';
  css += fontFace('AstrBot UI', 'astrbot-ui-bold.woff2', 700);
  css += '\n';
  for (const file of notoFiles) {
    css += fontFace(
      'AstrBot Noto Sans SC',
      file.regular,
      400,
      'normal',
      file.range,
    );
    css += '\n';
    css += fontFace(
      'AstrBot Noto Sans SC',
      file.bold,
      700,
      'normal',
      file.range,
    );
    css += '\n';
  }
  css += fontFace('Maple Mono', 'maple-mono-regular.woff2', 400);
  css += '\n';
  css += fontFace('Maple Mono', 'maple-mono-bold.woff2', 700);
  css += '\n';
  css += fontFace('Maple Mono', 'maple-mono-italic.woff2', 400, 'italic');
  css += `
:root {
  --astrbot-font-ui: "AstrBot UI", "AstrBot Noto Sans SC", system-ui, sans-serif;
  --astrbot-font-mono: "Maple Mono", "AstrBot Noto Sans SC", ui-monospace, monospace;
  --ms-font-mono: var(--astrbot-font-mono);
  --v-font-body: var(--astrbot-font-ui);
  --v-font-heading: var(--astrbot-font-ui);
}

code,
kbd,
pre,
samp {
  font-family: var(--astrbot-font-mono);
}
`;
  return css;
}

async function writeAtomic(path, contents) {
  await mkdir(dirname(path), { recursive: true });
  const temporary = `${path}.${process.pid}.tmp`;
  await writeFile(temporary, contents);
  await rename(temporary, path);
}

function generatedRecord(path, kind) {
  return { file: relative(FONT_ROOT, path).replaceAll('\\', '/'), kind };
}

export async function updateFonts() {
  const tempDir = await mkdtemp(join(tmpdir(), 'astrbot-fonts-'));
  try {
    const [notoArchive, mapleArchive] = await Promise.all([
      fetchVerifiedArchive(FONT_SOURCES.noto, tempDir),
      fetchVerifiedArchive(FONT_SOURCES.maple, tempDir),
    ]);
    const notoEntries = extractZipEntries(notoArchive);
    const mapleEntries = extractZipEntries(mapleArchive);
    const notoRegular = zipEntry(
      notoEntries,
      FONT_SOURCES.noto.files.regular.name,
    );
    const notoBold = zipEntry(notoEntries, FONT_SOURCES.noto.files.bold.name);
    const notoLicense = zipEntry(notoEntries, FONT_SOURCES.noto.licenseFile);
    const mapleLicense = zipEntry(mapleEntries, FONT_SOURCES.maple.licenseFile);
    assertHash(
      notoRegular,
      FONT_SOURCES.noto.files.regular.sha256,
      'Noto regular',
    );
    assertHash(notoBold, FONT_SOURCES.noto.files.bold.sha256, 'Noto bold');
    assertHash(notoLicense, FONT_SOURCES.noto.licenseSha256, 'Noto license');
    assertHash(mapleLicense, FONT_SOURCES.maple.licenseSha256, 'Maple license');

    const outputs = new Map();
    const sourceRanges = collectOtfUnicodeRanges(notoRegular);
    const uiCharacters = (await collectUiCharacters()).filter((character) =>
      sourceRanges.some(
        ([start, end]) =>
          start <= character.codePointAt(0) && character.codePointAt(0) <= end,
      ),
    );
    const uiText = uiCharacters.join('');
    outputs.set(
      'files/astrbot-ui-regular.woff2',
      await subsetFont(notoRegular, uiText, { targetFormat: 'woff2' }),
    );
    outputs.set(
      'files/astrbot-ui-bold.woff2',
      await subsetFont(notoBold, uiText, { targetFormat: 'woff2' }),
    );

    const notoFiles = [];
    for (const [index, [start, end]] of NOTO_UNICODE_RANGES.entries()) {
      const text = charactersForRange(sourceRanges, start, end);
      if (!text) continue;
      const id = String(index).padStart(2, '0');
      const regular = `astrbot-noto-sans-sc-${id}-regular.woff2`;
      const bold = `astrbot-noto-sans-sc-${id}-bold.woff2`;
      outputs.set(
        `files/${regular}`,
        await subsetFont(notoRegular, text, { targetFormat: 'woff2' }),
      );
      outputs.set(
        `files/${bold}`,
        await subsetFont(notoBold, text, { targetFormat: 'woff2' }),
      );
      notoFiles.push({ regular, bold, range: unicodeRange(start, end) });
    }

    for (const [style, source] of Object.entries(FONT_SOURCES.maple.files)) {
      const buffer = zipEntry(mapleEntries, source.name);
      assertHash(buffer, source.sha256, `Maple ${style}`);
      outputs.set(`files/maple-mono-${style}.woff2`, buffer);
    }
    outputs.set('LICENSE-NotoSansSC.txt', notoLicense);
    outputs.set('LICENSE-MapleMono.txt', mapleLicense);
    outputs.set('fonts.css', Buffer.from(buildCss(notoFiles)));

    const outputFiles = new Set(outputs.keys());
    try {
      for (const entry of await readdir(FONT_FILES, { withFileTypes: true })) {
        const file = `files/${entry.name}`;
        if (entry.isFile() && !outputFiles.has(file)) {
          await rm(join(FONT_FILES, entry.name));
        }
      }
    } catch (error) {
      if (error?.code !== 'ENOENT') throw error;
    }

    const generated = [];
    for (const [file, contents] of outputs) {
      const outputPath = join(FONT_ROOT, file);
      await writeAtomic(outputPath, contents);
      generated.push({
        ...generatedRecord(
          outputPath,
          file.startsWith('files/') ? 'font' : 'support',
        ),
        sha256: sha256(contents),
        bytes: contents.length,
      });
    }
    const metadata = {
      schemaVersion: 1,
      sources: {
        noto: {
          ...FONT_SOURCES.noto,
          license:
            'SIL Open Font License 1.1; source family is Noto Sans SC. Generated subsets are presented as AstrBot UI and AstrBot Noto Sans SC.',
        },
        maple: {
          ...FONT_SOURCES.maple,
          license:
            'SIL Open Font License 1.1; Maple Mono is redistributed unmodified as WOFF2.',
        },
      },
      generated: {
        css: generated.find((entry) => entry.file === 'fonts.css'),
        files: generated.filter((entry) => entry.file !== 'fonts.css'),
        uiCodePoints: uiCharacters.map((character) =>
          character.codePointAt(0).toString(16).toUpperCase(),
        ),
        notoChunkCount: notoFiles.length,
      },
    };
    await writeAtomic(FONT_METADATA, `${JSON.stringify(metadata, null, 2)}\n`);
    console.log(
      `Updated ${notoFiles.length} Noto Unicode-range chunks and ${uiCharacters.length} UI characters.`,
    );
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  updateFonts().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
}
