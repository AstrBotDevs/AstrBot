import { afterEach, describe, expect, it, vi } from 'vitest';
import { nextTick } from 'vue';
import AstrBotCoreConfigWrapper from '@/components/config/AstrBotCoreConfigWrapper.vue';
import AstrBotConfigV4 from '@/components/shared/AstrBotConfigV4.vue';
import { initI18n } from '@/i18n/composables';
import { mountWithVuetify } from './utils/mountWithVuetify';

vi.mock('@/utils/monacoLoader', () => ({}));

vi.mock('@guolao/vue-monaco-editor', () => ({
  VueMonacoEditor: {
    name: 'VueMonacoEditor',
    template: '<div class="monaco-editor-stub"></div>',
  },
}));

describe('config docs links', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('hides the tab footer when the current group has no docs', () => {
    const wrapper = mountWithVuetify(AstrBotCoreConfigWrapper, {
      props: {
        metadata: {
          other_group: {
            name: 'Other',
            metadata: {
              foo: {
                description: 'Foo',
                type: 'object',
                items: {
                  bar: { description: 'Bar', type: 'string' },
                },
              },
            },
          },
        },
        configData: { bar: '' },
      },
      global: {
        stubs: {
          AstrBotConfigV4: { template: '<div class="v4-stub" />' },
        },
      },
    });

    expect(wrapper.find('.config-tabs-help').exists()).toBe(false);
  });

  it('points the tab footer at the current group docs path', async () => {
    await initI18n('en-US');

    const wrapper = mountWithVuetify(AstrBotCoreConfigWrapper, {
      props: {
        metadata: {
          ai_group: {
            name: 'AI',
            docs: 'use/webui.html',
            metadata: {
              runner: {
                description: 'Runner',
                type: 'object',
                items: {
                  enable: { description: 'Enable', type: 'bool' },
                },
              },
            },
          },
          other_group: {
            name: 'Other',
            metadata: {
              foo: {
                description: 'Foo',
                type: 'object',
                items: {
                  bar: { description: 'Bar', type: 'string' },
                },
              },
            },
          },
        },
        configData: { enable: true, bar: '' },
      },
      global: {
        stubs: {
          AstrBotConfigV4: { template: '<div class="v4-stub" />' },
        },
      },
    });

    const footerLink = wrapper.get('.config-tabs-help a');
    expect(footerLink.attributes('href')).toBe('/help/en/use/webui.html');
    expect(footerLink.attributes('target')).toBe('_blank');
    expect(footerLink.attributes('rel')).toBe('noopener noreferrer');

    const tabs = wrapper.findAll('.config-tab');
    await tabs[1]?.trigger('click');
    await nextTick();

    expect(wrapper.find('.config-tabs-help').exists()).toBe(false);
  });

  it('renders section and field help icons from relative docs paths', async () => {
    await initI18n('en-US');

    const wrapper = mountWithVuetify(AstrBotConfigV4, {
      props: {
        metadata: {
          proactive_capability: {
            description: 'Proactive Agent',
            hint: 'Wake later',
            docs: 'use/proactive-agent.html',
            type: 'object',
            items: {
              'provider_settings.proactive_capability.add_cron_tools': {
                description: 'Enable',
                type: 'bool',
                hint: 'Pass tools to the agent',
                docs: 'use/proactive-agent.html',
              },
            },
          },
        },
        iterable: {
          provider_settings: {
            enable: true,
            agent_runner_type: 'local',
            proactive_capability: { add_cron_tools: false },
          },
        },
        metadataKey: 'proactive_capability',
      },
    });

    const links = wrapper.findAll('.config-docs-link');
    expect(links).toHaveLength(2);
    expect(links[0]?.attributes('href')).toBe(
      '/help/en/use/proactive-agent.html',
    );
    expect(links[1]?.attributes('href')).toBe(
      '/help/en/use/proactive-agent.html',
    );
    expect(links[0]?.attributes('target')).toBe('_blank');
    expect(links[0]?.attributes('rel')).toBe('noopener noreferrer');
    expect(wrapper.find('.config-hint').text()).not.toContain('/help/');
  });
});
