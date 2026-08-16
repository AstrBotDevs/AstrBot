import { afterEach, describe, expect, it, vi } from 'vitest';
import { flushPromises } from '@vue/test-utils';
import TemplateListEditor from '@/components/shared/TemplateListEditor.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

vi.mock('@/utils/monacoLoader', () => ({}));

vi.mock('@guolao/vue-monaco-editor', () => ({
  VueMonacoEditor: {
    name: 'VueMonacoEditor',
    template: '<div class="monaco-editor-stub"></div>',
  },
}));

vi.mock('axios', () => ({
  default: {
    defaults: {
      headers: {},
    },
    get: vi.fn(),
    create: vi.fn(() => ({
      defaults: {
        headers: {},
      },
      interceptors: {
        request: { use: vi.fn() },
        response: { use: vi.fn() },
      },
    })),
  },
}));

vi.mock('@/api/v1', () => ({
  pluginApi: {
    listConfigFiles: vi.fn(async () => ({
      data: { data: [] },
    })),
    deleteConfigFile: vi.fn(async () => ({
      data: { status: 'ok' },
    })),
    uploadConfigFile: vi.fn(async () => ({
      data: { status: 'ok', data: { file_path: 'uploaded.txt' } },
    })),
  },
  providerApi: {
    embeddingDimension: vi.fn(async () => ({
      data: { status: 'ok', data: { embedding_dimensions: 1024 } },
    })),
  },
}));

describe('TemplateListEditor smoke', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('expands nested template entries without transition or attr warnings', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    const wrapper = mountWithVuetify(TemplateListEditor, {
      props: {
        configPath: 'provider.tools',
        templates: {
          assistant: {
            name: 'Assistant Template',
            hint: 'Reusable assistant configuration',
            display_item: 'name',
            items: {
              name: {
                type: 'string',
                description: 'Template Name',
                hint: 'Visible label',
              },
              advanced: {
                type: 'object',
                items: {
                  enabled: {
                    type: 'bool',
                    description: 'Enabled',
                    hint: 'Toggle this feature',
                  },
                },
              },
            },
          },
        },
        modelValue: [
          {
            __template_key: 'assistant',
            name: 'Agent Alpha',
            advanced: {
              enabled: true,
            },
          },
        ],
      },
    });

    await flushPromises();

    expect(wrapper.text()).toContain('Assistant Template');
    expect(wrapper.text()).toContain('Template Name: Agent Alpha');

    await wrapper.find('.entry-header').trigger('click');
    await flushPromises();

    expect(wrapper.text()).toContain('Template Name');
    expect(wrapper.text()).toContain('Enabled');
    expect(wrapper.find('.v-switch').exists()).toBe(true);

    const warningTexts = warnSpy.mock.calls.flatMap((args) =>
      args.map((arg) => String(arg)),
    );
    expect(
      warningTexts.some(
        (text) =>
          text.includes('Extraneous non-props attributes') ||
          text.includes(
            'Component inside <Transition> renders non-element root node',
          ),
      ),
    ).toBe(false);
  });
});
