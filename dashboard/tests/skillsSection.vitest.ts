import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const skillsSection = readFileSync(
  resolve(process.cwd(), 'src/components/extension/SkillsSection.vue'),
  'utf8',
);

describe('SkillsSection builtin presets', () => {
  it('renders builtin sources and keeps their operations readonly', () => {
    expect(skillsSection).toContain("sourceType === 'builtin_preset'");
    expect(skillsSection).toContain('isBuiltinPresetSkill(skill)');
    expect(skillsSection).toContain('skill.readonly === true');
    expect(skillsSection).toContain('isReadOnlySourceSkill(skill)');
    expect(skillsSection).toContain("tm('skills.builtinReadonly')");
  });

  it('keeps skills from disabled plugins visible but non-interactive', () => {
    expect(skillsSection).toContain('plugin_active?: boolean');
    expect(skillsSection).toContain('isInactivePluginSkill(skill)');
    expect(skillsSection).toContain('skill-list-item--inactive');
    expect(skillsSection).toContain("tm('skills.pluginDisabled')");
  });
});
