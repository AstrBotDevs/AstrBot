import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

function readSource(path: string): string {
  return readFileSync(path, 'utf8');
}

describe('Vuetify 4 API usage', () => {
  it('uses raw select slot items instead of the removed item wrapper shape', () => {
    const t2iEditor = readSource('src/components/shared/T2ITemplateEditor.vue');
    const knowledgeBaseList = readSource('src/views/knowledge-base/KBList.vue');

    expect(t2iEditor).toContain(':title="item.name"');
    expect(t2iEditor).not.toContain('item.raw.name');
    expect(knowledgeBaseList).toContain('id: item.id');
    expect(knowledgeBaseList).not.toContain('providerSelectItem(item)');
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
  });
});
