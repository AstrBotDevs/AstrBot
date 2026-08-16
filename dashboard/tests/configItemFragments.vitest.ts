import { afterEach, describe, expect, it, vi } from 'vitest';
import { flushPromises } from '@vue/test-utils';
import AstrBotConfig from '@/components/shared/AstrBotConfig.vue';
import ListConfigItem from '@/components/shared/ListConfigItem.vue';
import ObjectEditor from '@/components/shared/ObjectEditor.vue';
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
  providerApi: {
    embeddingDimension: vi.fn(async () => ({
      data: { status: 'ok', data: { embedding_dimensions: 1024 } },
    })),
  },
}));

describe('shared config editors', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('allows class attrs on ListConfigItem without fragment warnings', () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    const wrapper = mountWithVuetify(ListConfigItem, {
      attrs: {
        class: 'config-field',
      },
      props: {
        modelValue: ['alpha'],
      },
      global: {
        stubs: {
          VDialog: {
            props: ['modelValue'],
            template: '<div v-if="modelValue"><slot /></div>',
          },
        },
      },
    });

    expect(wrapper.classes()).toContain('config-field');
    expect(
      warnSpy.mock.calls.some((args) =>
        String(args[0]).includes('Extraneous non-props attributes'),
      ),
    ).toBe(false);
  });

  it('allows class attrs on ObjectEditor without fragment warnings', () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    const wrapper = mountWithVuetify(ObjectEditor, {
      attrs: {
        class: 'config-field',
      },
      props: {
        modelValue: { foo: 'bar' },
        itemMeta: {},
      },
      global: {
        stubs: {
          VDialog: {
            props: ['modelValue'],
            template: '<div v-if="modelValue"><slot /></div>',
          },
        },
      },
    });

    expect(wrapper.classes()).toContain('config-field');
    expect(
      warnSpy.mock.calls.some((args) =>
        String(args[0]).includes('Extraneous non-props attributes'),
      ),
    ).toBe(false);
  });

  it('renders AstrBotConfig dict fields through ObjectEditor without attr warnings', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    const wrapper = mountWithVuetify(AstrBotConfig, {
      props: {
        metadata: {
          provider: {
            type: 'object',
            items: {
              custom_extra_body: {
                type: 'dict',
                items: {},
                template_schema: {
                  temperature: {
                    type: 'float',
                    default: 0.6,
                    slider: { min: 0, max: 2, step: 0.1 },
                    description: 'Temperature',
                    hint: 'Sampling temperature',
                  },
                },
                description: 'Custom Extra Body',
                hint: 'Extra request payload fields',
              },
            },
          },
        },
        iterable: {
          custom_extra_body: {},
        },
        metadataKey: 'provider',
      },
      global: {
        stubs: {
          VDialog: {
            props: ['modelValue'],
            template: '<div v-if="modelValue"><slot /></div>',
          },
        },
      },
    });

    await flushPromises();

    expect(wrapper.text()).toContain('Custom Extra Body');
    expect(wrapper.find('.object-editor').exists()).toBe(true);
    expect(
      warnSpy.mock.calls.some((args) =>
        args.some((arg) =>
          String(arg).includes('Extraneous non-props attributes'),
        ),
      ),
    ).toBe(false);
  });
});
