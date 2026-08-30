import { flushPromises } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ChatInput from '@/components/chat/ChatInput.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

vi.mock('@/i18n/composables', () => ({
  useModuleI18n: () => ({
    tm: (key: string) => (key === 'input.placeholder' ? 'Default prompt' : key),
  }),
}));

vi.mock('@/stores/customizer', () => ({
  useCustomizerStore: () => ({ uiTheme: 'AstrBotLight' }),
}));

vi.mock('@/components/chat/ConfigSelector.vue', () => ({
  default: {
    template: '<div class="config-selector-stub"></div>',
  },
}));

vi.mock('@/components/shared/StyledMenu.vue', () => ({
  default: {
    template:
      '<div class="styled-menu-stub"><slot name="activator" :props="{}" /><slot /></div>',
  },
}));

vi.mock('@/api/v1', () => ({
  commandApi: {
    list: vi.fn().mockResolvedValue({
      data: {
        status: 'ok',
        data: {
          items: [],
          command_prefixes: ['/'],
          llm_access: { prefixes: ['/'] },
        },
      },
    }),
  },
}));

const baseProps = {
  prompt: '',
  stagedImagesUrl: [],
  stagedAudioUrl: '',
  disabled: false,
  enableStreaming: true,
  isRecording: false,
  isRunning: false,
};

describe('ChatInput placeholders', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('uses the default placeholder for a single-line input', async () => {
    const wrapper = mountWithVuetify(ChatInput, { props: baseProps });
    await flushPromises();

    expect(
      wrapper.get('textarea.chat-textarea').attributes('placeholder'),
    ).toBe('Default prompt');
  });

  it('uses custom placeholders, including an intentional empty string', async () => {
    const wrapper = mountWithVuetify(ChatInput, {
      props: { ...baseProps, placeholder: 'Project prompt' },
    });
    await flushPromises();
    expect(
      wrapper.get('textarea.chat-textarea').attributes('placeholder'),
    ).toBe('Project prompt');

    await wrapper.setProps({ placeholder: '' });
    expect(
      wrapper.get('textarea.chat-textarea').attributes('placeholder'),
    ).toBe('');
  });

  it('uses custom placeholders after expanding to a textarea', async () => {
    const wrapper = mountWithVuetify(ChatInput, {
      props: {
        ...baseProps,
        prompt: 'first line\nsecond line',
        placeholder: 'Project prompt',
      },
    });
    await flushPromises();

    expect(
      wrapper.get('textarea.chat-textarea').attributes('placeholder'),
    ).toBe('Project prompt');
  });
});

describe('ChatInput stop and send controls', () => {
  it('shows only stop while running with a non-empty prompt', async () => {
    const wrapper = mountWithVuetify(ChatInput, {
      props: { ...baseProps, prompt: 'follow up', isRunning: true },
    });
    await flushPromises();

    expect(wrapper.find('[aria-label="input.stopGenerating"]').exists()).toBe(
      true,
    );
    expect(wrapper.find('[aria-label="input.send"]').exists()).toBe(false);
  });
});

describe('ChatInput high-risk tools control', () => {
  it('renders the high-risk tools control in the plus menu', async () => {
    const wrapper = mountWithVuetify(ChatInput, {
      props: { ...baseProps, webChatToolsEnabled: false },
    });

    await flushPromises();

    expect(wrapper.find('[aria-label="input.moreOptions"]').exists()).toBe(
      true,
    );
    expect(
      wrapper.find('.input-right-actions .high-risk-tools-btn').exists(),
    ).toBe(false);

    const control = wrapper.get('.high-risk-tools-btn');
    expect(control.find('.v-icon').classes()).toContain(
      'mdi-shield-key-outline',
    );
    expect(control.text()).toContain('input.enableHighRiskTools');

    await control.trigger('click');
    expect(wrapper.emitted('toggleWebChatTools')).toHaveLength(1);
  });
});
