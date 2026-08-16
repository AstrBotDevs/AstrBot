import { execFileSync } from 'node:child_process';
import { describe, expect, it } from 'vitest';

describe('Dashboard design-system source guard', () => {
  it('rejects inline visual rules in Vue templates', () => {
    expect(() => {
      execFileSync('node', ['scripts/check-design-system-source.mjs'], {
        cwd: process.cwd(),
        stdio: 'pipe',
      });
    }).not.toThrow();
  });
});
