import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { flushPromises } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import SkillsSection from '@/components/extension/SkillsSection.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

const skillsSection = readFileSync(
  resolve(process.cwd(), 'src/components/extension/SkillsSection.vue'),
  'utf8',
);

const api = vi.hoisted(() => ({
  list: vi.fn(),
  delete: vi.fn(),
  getConfig: vi.fn(),
}));

vi.mock('@/api/v1', () => ({
  skillApi: {
    list: api.list,
    delete: api.delete,
  },
  systemConfigApi: {
    get: api.getConfig,
  },
}));

vi.mock('@guolao/vue-monaco-editor', () => ({
  VueMonacoEditor: { template: '<div class="monaco-stub"></div>' },
}));

vi.mock('@/utils/monacoLoader', () => ({}));

const localSkills = [
  {
    name: 'local-one',
    description: 'First local skill',
    path: '/skills/local-one',
    active: true,
    source_type: 'local_only',
  },
  {
    name: 'local-two',
    description: 'Second local skill',
    path: '/skills/local-two',
    active: true,
    source_type: 'local_only',
  },
];

const readOnlySkills = [
  {
    name: 'builtin-skill',
    description: 'Builtin preset',
    path: '/skills/builtin',
    active: true,
    source_type: 'builtin_preset',
    readonly: true,
  },
  {
    name: 'plugin-skill',
    description: 'From a plugin',
    path: '/skills/plugin',
    active: true,
    source_type: 'plugin',
    plugin_name: 'demo-plugin',
    plugin_active: true,
  },
];

function ok(data: unknown) {
  return { data: { status: 'ok', data } };
}

function findButton(
  wrapper: { findAll: (selector: string) => Array<{ text: () => string }> },
  label: string,
) {
  const button = wrapper
    .findAll('button')
    .find((item) => item.text().replace(/\s+/g, ' ').trim() === label);
  expect(button).toBeTruthy();
  return button!;
}

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

  it('opens the skill editor fullscreen on compact viewports', () => {
    expect(skillsSection).toContain(':fullscreen="$vuetify.display.mdAndDown"');
    expect(skillsSection).toContain('max-height: none;');
    expect(skillsSection).toContain('overflow-y: auto;');
    expect(skillsSection).toContain('min-height: 40vh;');
  });

  it('adds local skill batch deletion with confirmation and partial feedback', () => {
    expect(skillsSection).toContain('startBatchSelection');
    expect(skillsSection).toContain('deleteSelectedSkills');
    expect(skillsSection).toContain('skillApi.delete(name)');
    expect(skillsSection).toContain("tm('skills.batchDeletePartial'");
    expect(skillsSection).toContain('mdi-select-multiple');
    expect(skillsSection).toContain(':clickable="!batchSelectionEnabled"');
  });
});

describe('SkillsSection batch delete behavior', () => {
  let currentSkills: Array<Record<string, unknown>>;

  beforeEach(() => {
    vi.clearAllMocks();
    currentSkills = [...localSkills, ...readOnlySkills];
    api.list.mockImplementation(async () => ok(currentSkills));
    api.getConfig.mockResolvedValue(
      ok({ config: { provider_settings: { computer_use_runtime: 'local' } } }),
    );
    api.delete.mockImplementation(async (name: string) => {
      if (name === 'local-two') {
        return { data: { status: 'error', message: 'still in use' } };
      }
      currentSkills = currentSkills.filter((skill) => skill.name !== name);
      return ok({});
    });
  });

  it('selects only deletable skills and keeps failed names after a partial batch delete', async () => {
    const wrapper = mountWithVuetify(SkillsSection, {
      global: {
        stubs: { VueMonacoEditor: { template: '<div />' } },
      },
    });
    await flushPromises();

    await findButton(wrapper, 'Select').trigger('click');
    await flushPromises();

    expect(
      wrapper.find('[aria-label="Select Skill builtin-skill"]').exists(),
    ).toBe(false);
    expect(
      wrapper.find('[aria-label="Select Skill plugin-skill"]').exists(),
    ).toBe(false);

    const localOne = wrapper.get('[aria-label="Select Skill local-one"]');
    const localTwo = wrapper.get('[aria-label="Select Skill local-two"]');
    await localOne.trigger('click');
    await localTwo.trigger('click');
    await flushPromises();

    await findButton(wrapper, 'Delete selected (2)').trigger('click');
    await flushPromises();

    const dialogTargets = Array.from(
      document.body.querySelectorAll('.batch-delete-target'),
    ).map((item) => item.textContent?.replace(/\s+/g, ' ').trim());
    expect(dialogTargets).toEqual(['local-one', 'local-two']);

    const confirmDelete = Array.from(
      document.body.querySelectorAll('button'),
    ).find(
      (item) => item.textContent?.replace(/\s+/g, ' ').trim() === 'Delete 2',
    );
    expect(confirmDelete).toBeTruthy();
    confirmDelete?.click();
    await flushPromises();

    expect(api.delete.mock.calls.map((call) => call[0])).toEqual([
      'local-one',
      'local-two',
    ]);
    expect(document.body.textContent).toContain(
      'Deleted 1; failed to delete 1',
    );
    const leftover = wrapper.get('[aria-label="Select Skill local-two"]');
    const leftoverInput = leftover.element.matches('input')
      ? leftover.element
      : leftover.get('input').element;
    expect((leftoverInput as HTMLInputElement).checked).toBe(true);
    expect(wrapper.find('[aria-label="Select Skill local-one"]').exists()).toBe(
      false,
    );

    wrapper.unmount();
  });
});
