import { readdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

function readSource(path: string): string {
  return readFileSync(path, 'utf8');
}

function sourceFiles(root: string, suffixes: string[]): string[] {
  return readdirSync(root, { recursive: true })
    .filter((entry) => suffixes.some((suffix) => entry.endsWith(suffix)))
    .map((entry) => resolve(root, entry));
}

const srcRoot = resolve(process.cwd(), 'src');
const vueAndTsSources = sourceFiles(srcRoot, ['.vue', '.ts']);
const viteConfig = readSource('vite.config.ts');
const workspace = readSource('pnpm-workspace.yaml');
const packageJson = JSON.parse(readSource('package.json')) as {
  dependencies: Record<string, string>;
};
const vuetifyPlugin = readSource('src/plugins/vuetify.ts');
const vuetifySettings = readSource('src/scss/settings.scss');
const vuetifyOverrides = readSource('src/styles/vuetify-overrides.scss');

function collectMatches(pattern: RegExp): string[] {
  const globalPattern = new RegExp(
    pattern.source,
    pattern.flags.includes('g') ? pattern.flags : `${pattern.flags}g`,
  );
  return vueAndTsSources.flatMap((path) => {
    const source = readSource(path);
    return [...source.matchAll(globalPattern)].map(
      (match) => `${path}: ${match[0]}`,
    );
  });
}

describe('Vuetify 4 API usage', () => {
  it('uses raw select slot items instead of the removed item wrapper shape', () => {
    const t2iEditor = readSource('src/components/shared/T2ITemplateEditor.vue');
    const knowledgeBaseList = readSource('src/views/knowledge-base/KBList.vue');

    expect(t2iEditor).toContain(':title="item.name"');
    expect(t2iEditor).not.toContain('item.raw.name');
    expect(knowledgeBaseList).toContain('id: item.id');
    expect(knowledgeBaseList).not.toContain('providerSelectItem(item)');
    expect(collectMatches(/\bitem\.raw\b/)).toEqual([]);
  });

  it('does not pass props removed in Vuetify 4', () => {
    const app = readSource('src/App.vue');
    const fullLayout = readSource('src/layouts/full/FullLayout.vue');
    const consoleDisplayer = readSource(
      'src/components/shared/ConsoleDisplayer.vue',
    );

    expect(app).not.toContain('multi-line');
    expect(fullLayout).not.toMatch(/<v-progress-linear[^>]*\bfixed\b/);
    expect(fullLayout).not.toMatch(/<v-progress-linear[^>]*\s+top(?:\s|>)/);
    expect(consoleDisplayer).not.toContain('text-color');
    expect(collectMatches(/<v-container\b[^>]*\belevation=/)).toEqual([]);
    expect(collectMatches(/<v-row\b[^>]*\s:?align=/)).toEqual([]);
    expect(collectMatches(/<v-row\b[^>]*\s:?justify=/)).toEqual([]);
    expect(collectMatches(/<v-row\b[^>]*\s:?dense[\s=>]/)).toEqual([]);
  });

  it('follows the Vuetify 4 Vite install and theme APIs', () => {
    const vuetifyVersion = packageJson.dependencies.vuetify;

    expect(viteConfig).toContain('transformAssetUrls');
    expect(viteConfig).toMatch(
      /import vuetify, \{ transformAssetUrls \} from 'vite-plugin-vuetify'/,
    );
    expect(viteConfig).not.toContain('v-list-recognize-title');
    expect(vuetifyVersion).toMatch(/^\d+\.\d+\.\d+$/);
    expect(workspace).toContain(`- vuetify@${vuetifyVersion}`);
    expect(vuetifyPlugin).not.toMatch(/VBtn:\s*\{[^}]*minHeight/s);
    expect(vuetifySettings).toMatch(/\$button-height:\s*40px/);
    expect(vuetifySettings).toMatch(/\$button-text-letter-spacing:\s*0/);
    expect(vuetifyOverrides).not.toMatch(/\.v-btn\s*\{[^}]*text-transform:/s);
    expect(vuetifyOverrides).not.toMatch(/\.v-btn\s*\{[^}]*letter-spacing:/s);
    expect(collectMatches(/theme\.global\.themes/)).toEqual([]);
    expect(collectMatches(/v-list-recognize-title/)).toEqual([]);
  });
});
