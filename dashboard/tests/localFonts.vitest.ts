import { readFile, readdir } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const dashboardRoot = resolve(process.cwd());

async function cssSources(directory, files = []) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) await cssSources(path, files);
    else if (/\.(?:css|scss|vue)$/.test(entry.name)) files.push(path);
  }
  return files;
}

describe('local font policy', () => {
  it('keeps remote font URLs out of HTML and styles', async () => {
    const indexHtml = await readFile(join(dashboardRoot, 'index.html'), 'utf8');
    const styles = await Promise.all(
      (await cssSources(join(dashboardRoot, 'src'))).map((file) =>
        readFile(file, 'utf8'),
      ),
    );
    const content = [indexHtml, ...styles].join('\n');
    expect(content).not.toMatch(/fonts\.(?:googleapis|gstatic)\.com/i);
    expect(content).not.toMatch(/url\(\s*["']?https?:\/\//i);
  });

  it('defines Vuetify font variables in the local font stylesheet', async () => {
    const css = await readFile(
      join(dashboardRoot, 'src/assets/fonts/fonts.css'),
      'utf8',
    );
    expect(css).toContain('--v-font-body:');
    expect(css).toContain('--v-font-heading:');
    expect(css).toContain('--astrbot-font-mono:');
    expect(css).toContain('--ms-font-mono: var(--astrbot-font-mono);');
    expect(css).toContain('font-family: var(--astrbot-font-mono);');
  });
});
