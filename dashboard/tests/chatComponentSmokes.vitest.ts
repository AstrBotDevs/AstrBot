import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises } from '@vue/test-utils';
import ChatInput from '@/components/chat/ChatInput.vue';
import ReasoningBlock from '@/components/chat/message_list_comps/ReasoningBlock.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

const testState = vi.hoisted(() => ({
  commandListMock: vi.fn(),
  customizer: {
    uiTheme: 'AstrBotLight',
  },
}));

vi.mock('@/api/v1', () => ({
  commandApi: {
    list: testState.commandListMock,
  },
}));

vi.mock('@/stores/customizer', () => ({
  useCustomizerStore: () => testState.customizer,
}));

vi.mock('@/components/chat/ConfigSelector.vue', () => ({
  default: {
    template: '<div class="config-selector-stub"></div>',
  },
}));

vi.mock('@/components/chat/ProviderModelMenu.vue', () => ({
  default: {
    template: '<div class="provider-model-menu-stub"></div>',
    setup(_, { expose }) {
      expose({
        getCurrentSelection: () => ({
          providerId: 'provider-1',
          modelName: 'gpt-4.1-mini',
        }),
      });
      return {};
    },
  },
}));

vi.mock('@/components/shared/StyledMenu.vue', () => ({
  default: {
    template:
      '<div class="styled-menu-stub"><slot name="activator" :props="{}" /><slot /></div>',
  },
}));

vi.mock('@/components/chat/CommandSuggestion.vue', () => ({
  default: {
    template: '<div class="command-suggestion-stub"></div>',
  },
}));

vi.mock('@/components/chat/message_list_comps/ReasoningTimeline.vue', () => ({
  default: {
    props: ['parts', 'reasoning'],
    template:
      '<div class="reasoning-timeline-stub">{{ parts?.length || 0 }}|{{ reasoning || "" }}</div>',
  },
}));

describe('chat component smokes', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    testState.commandListMock.mockResolvedValue({
      data: {
        status: 'ok',
        data: {
          items: [],
          command_prefixes: ['/'],
          llm_access: { prefixes: ['/'] },
        },
      },
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('renders ChatInput reply and attachment previews without runtime warnings', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    const wrapper = mountWithVuetify(ChatInput, {
      props: {
        prompt: '',
        stagedImagesUrl: ['https://example.com/image.png'],
        stagedAudioUrl: 'blob:audio-preview',
        stagedFiles: [
          {
            attachment_id: 'file-1',
            filename: 'notes.md',
            original_name: 'notes.md',
            url: 'https://example.com/notes.md',
            type: 'file',
          },
        ],
        disabled: false,
        enableStreaming: true,
        isRecording: false,
        isRunning: false,
        replyTo: {
          messageId: 'reply-1',
          selectedText: 'quoted message',
        },
        currentSession: {
          platform_id: 'webchat',
        },
      },
    });

    await flushPromises();

    expect(wrapper.find('.reply-preview').exists()).toBe(true);
    expect(wrapper.find('.attachments-preview').exists()).toBe(true);
    expect(
      wrapper.find('.input-container').attributes('style'),
    ).toBeUndefined();
    expect(wrapper.text()).toContain('quoted message');
    expect(
      warnSpy.mock.calls.some((args) =>
        args.some((arg) =>
          String(arg).includes('Component inside <Transition>'),
        ),
      ),
    ).toBe(false);
  });

  it('keeps a textarea and only expands the composer for multiline prompts', async () => {
    vi.spyOn(
      HTMLTextAreaElement.prototype,
      'scrollHeight',
      'get',
    ).mockImplementation(function (this: HTMLTextAreaElement) {
      return this.value.includes('\n') ? 96 : 52;
    });

    const wrapper = mountWithVuetify(ChatInput, {
      props: {
        prompt: '',
        stagedImagesUrl: [],
        stagedAudioUrl: '',
        disabled: false,
        enableStreaming: true,
        isRecording: false,
        isRunning: false,
      },
    });

    await flushPromises();
    expect(wrapper.find('.chat-textarea').exists()).toBe(true);
    expect(wrapper.find('.chat-text-input').exists()).toBe(false);
    expect(wrapper.find('.input-container').classes()).not.toContain(
      'is-multiline',
    );

    await wrapper.setProps({ prompt: 'first line\nsecond line' });
    await flushPromises();
    expect(wrapper.find('.chat-textarea').exists()).toBe(true);
    expect(wrapper.find('.input-container').classes()).toContain(
      'is-multiline',
    );

    await wrapper.setProps({ prompt: 'short' });
    await flushPromises();
    expect(wrapper.find('.chat-textarea').exists()).toBe(true);
    expect(wrapper.find('.input-container').classes()).toContain(
      'is-multiline',
    );

    await wrapper.setProps({ prompt: '' });
    await flushPromises();
    expect(wrapper.find('.chat-textarea').exists()).toBe(true);
    expect(wrapper.find('.input-container').classes()).not.toContain(
      'is-multiline',
    );
  });

  it('renders ReasoningBlock streaming preview and expands inline timeline', async () => {
    const wrapper = mountWithVuetify(ReasoningBlock, {
      props: {
        parts: [{ type: 'think', think: 'First line\nSecond line' }],
        isStreaming: true,
      },
    });

    await vi.advanceTimersByTimeAsync(2100);
    await flushPromises();

    expect(wrapper.find('.reasoning-preview').exists()).toBe(true);

    await wrapper.find('.reasoning-header').trigger('click');
    await flushPromises();

    expect(wrapper.find('.reasoning-content').exists()).toBe(true);
    expect(wrapper.find('.reasoning-timeline-stub').text()).toBe('1|');
    expect(wrapper.emitted('open')).toBeUndefined();
  });

  it('opens the sidebar from the dedicated button and hides inline content', async () => {
    const wrapper = mountWithVuetify(ReasoningBlock, {
      props: {
        parts: [{ type: 'think', think: 'First line\nSecond line' }],
        showSidebarAction: true,
      },
    });

    await wrapper.find('.reasoning-header').trigger('click');
    await flushPromises();
    expect(wrapper.find('.reasoning-content').exists()).toBe(true);
    expect(wrapper.emitted('open')).toBeUndefined();

    await wrapper.find('.reasoning-sidebar-btn').trigger('click');
    await flushPromises();
    expect(wrapper.emitted('open')).toHaveLength(1);
    expect(wrapper.find('.reasoning-content').exists()).toBe(false);

    await wrapper.setProps({ sidebarActive: true });
    await wrapper.find('.reasoning-header').trigger('click');
    await flushPromises();
    expect(
      wrapper.find('.reasoning-header').attributes('disabled'),
    ).toBeDefined();
    expect(wrapper.find('.reasoning-content').exists()).toBe(false);
  });
});
