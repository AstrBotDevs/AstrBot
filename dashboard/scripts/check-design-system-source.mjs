import { readdirSync, readFileSync } from 'node:fs';
import { join, relative } from 'node:path';

const sourceRoot = 'src';
const allowedDynamicStyles = new Map([
  ['src/layouts/full/FullLayout.vue', ['appearance.rootStyle']],
  ['src/layouts/full/vertical-sidebar/NavItem.vue', ['itemStyle']],
  ['src/views/extension/PluginDetailPage.vue', ['item.depth']],
  ['src/components/appearance/DashboardWallpaperLayer.vue', ['layerStyle']],
  [
    'src/components/appearance/DashboardAppearanceSettings.vue',
    ['previewImageStyle', 'previewShadeStyle', 'previewSurfaceStyle'],
  ],
  ['src/components/shared/TraceDisplayer.vue', ['tableHeight']],
  ['src/components/chat/LiveOrb.vue', ['styleVars', 'col.style']],
  ['src/components/shared/PluginPlatformChip.vue', ['marginLeft']],
  ['src/components/chat/ChatInput.vue', ['--attachment-color']],
  ['src/components/chat/ChatMessageList.vue', ['--attachment-color']],
  ['src/components/chat/MessageList.vue', ['--attachment-color']],
  ['src/components/chat/StandaloneChat.vue', ['--attachment-color']],
  ['src/components/chat/CommandSuggestion.vue', ['panelStyle', 'tooltipStyle']],
  ['src/components/folder/BaseMoveTargetNode.vue', ['paddingLeft']],
  ['src/components/folder/BaseFolderTreeNode.vue', ['paddingLeft']],
  ['src/components/chat/Chat.vue', ['threadSelection.left']],
  ['src/components/chat/message_list_comps/ActionRef.vue', ['zIndex']],
  ['src/components/chat/message_list_comps/RefNode.vue', ['chipStyle']],
]);

const allowedRoundedValues = new Set(['0', 'sm', 'md', 'circle']);
const namedRawColors =
  'black|white|red|orange|yellow|green|blue|purple|pink|grey|gray|indigo';
const rawColorAttribute = new RegExp(
  String.raw`(?<!:)\b(?:color|bg-color|base-color|text-color|icon-color)\s*=\s*(["'])\s*(?:#[0-9a-fA-F]{3,8}|rgba?\(|hsla?\(|${namedRawColors})`,
  'i',
);
const roundedAttribute = /(?<!:)\brounded\s*=\s*(["'])([^"']+)\1/g;
const elevationAttribute = /(?<!:)\belevation\s*=\s*(["'])(\d+)\1/g;

function vueFiles(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const entryPath = join(directory, entry.name);
    if (entry.isDirectory()) return vueFiles(entryPath);
    return entry.name.endsWith('.vue') ? [entryPath] : [];
  });
}

const violations = [];

for (const filePath of vueFiles(sourceRoot)) {
  const source = readFileSync(filePath, 'utf8');
  const template = source.match(/<template\b[^>]*>([\s\S]*?)<\/template>/)?.[1];
  if (!template) continue;

  const file = relative('.', filePath).replaceAll('\\', '/');
  const allowed = allowedDynamicStyles.get(file) ?? [];
  const templateWithoutComments = template.replaceAll(/<!--[\s\S]*?-->/g, '');
  const lines = templateWithoutComments.split('\n');
  for (const [index, line] of lines.entries()) {
    const lineNumber = index + 1;
    if (/\sstyle\s*=/.test(line)) {
      violations.push(`${file}:${lineNumber}: static style attribute`);
      continue;
    }
    if (!/:style\s*=/.test(line)) continue;

    const expression = lines.slice(index, index + 10).join('\n');
    if (!allowed.some((marker) => expression.includes(marker))) {
      violations.push(`${file}:${lineNumber}: unapproved dynamic style`);
      continue;
    }
    if (/(?:borderRadius|boxShadow|#[0-9a-fA-F]{3,8})/.test(expression)) {
      violations.push(`${file}:${lineNumber}: inline visual token`);
    }
    if (/(?:z-index|zIndex)\s*:\s*\d+\s*[,}]/.test(expression)) {
      violations.push(`${file}:${lineNumber}: fixed inline z-index`);
    }
  }

  if (rawColorAttribute.test(templateWithoutComments)) {
    violations.push(`${file}: bare color in template`);
  }

  for (const match of templateWithoutComments.matchAll(roundedAttribute)) {
    if (!allowedRoundedValues.has(match[2])) {
      violations.push(`${file}: non-system rounded value ${match[2]}`);
    }
  }

  for (const match of templateWithoutComments.matchAll(elevationAttribute)) {
    if (Number(match[2]) > 4) {
      violations.push(`${file}: excessive elevation ${match[2]}`);
    }
  }

  if (/\brounded-(?:lg|xl|pill)\b/.test(templateWithoutComments)) {
    violations.push(`${file}: non-system rounded utility`);
  }
}

if (violations.length > 0) {
  throw new Error(
    `Dashboard design-system source guard failed:\n${violations.join('\n')}`,
  );
}
