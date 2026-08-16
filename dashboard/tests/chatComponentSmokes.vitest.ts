import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises } from '@vue/test-utils';
import ChatInput from '@/components/chat/ChatInput.vue';
import LiveOrb from '@/components/chat/LiveOrb.vue';
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
          wake_prefix: ['/'],
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
          is_group: false,
        },
      },
    });

    await flushPromises();

    expect(wrapper.find('.reply-preview').exists()).toBe(true);
    expect(wrapper.find('.attachments-preview').exists()).toBe(true);
    expect(wrapper.find('.input-container').attributes('style')).toBeUndefined();
    expect(wrapper.text()).toContain('quoted message');
    expect(
      warnSpy.mock.calls.some((args) =>
        args.some((arg) =>
          String(arg).includes('Component inside <Transition>'),
        ),
      ),
    ).toBe(false);
  });

  it('does not oscillate between single-line and multiline input layouts', async () => {
    vi.spyOn(Element.prototype, 'clientWidth', 'get').mockImplementation(
      function (this: Element) {
        return this instanceof HTMLInputElement ? 40 : 100;
      },
    );
    vi.spyOn(Element.prototype, 'scrollWidth', 'get').mockImplementation(
      function (this: Element) {
        return this instanceof HTMLInputElement ? 80 : 100;
      },
    );

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
    expect(wrapper.find('.chat-text-input').exists()).toBe(true);
    expect(wrapper.find('.chat-textarea').exists()).toBe(false);

    await wrapper.setProps({ prompt: 'content that overflows' });
    await flushPromises();
    expect(wrapper.find('.chat-text-input').exists()).toBe(false);
    expect(wrapper.find('.chat-textarea').exists()).toBe(true);

    await wrapper.setProps({ prompt: 'short' });
    await flushPromises();
    expect(wrapper.find('.chat-textarea').exists()).toBe(true);

    await wrapper.setProps({ prompt: '' });
    await flushPromises();
    expect(wrapper.find('.chat-text-input').exists()).toBe(true);
    expect(wrapper.find('.chat-textarea').exists()).toBe(false);
  });

  it('renders ReasoningBlock streaming preview and expands inline timeline', async () => {
    const wrapper = mountWithVuetify(ReasoningBlock, {
      props: {
        parts: [{ type: 'think', think: 'First line\nSecond line' }],
        isStreaming: true,
        openInSidebar: false,
      },
    });

    await vi.advanceTimersByTimeAsync(2100);
    await flushPromises();

    expect(wrapper.find('.reasoning-preview').exists()).toBe(true);

    await wrapper.find('.reasoning-header').trigger('click');
    await flushPromises();

    expect(wrapper.find('.reasoning-content').exists()).toBe(true);
    expect(wrapper.find('.reasoning-timeline-stub').text()).toBe('1|');
  });

  it('renders LiveOrb in code mode without crashing', async () => {
    const wrapper = mountWithVuetify(LiveOrb, {
      props: {
        energy: 0.6,
        mode: 'processing',
        codeMode: true,
        nervousMode: false,
      },
    });

    await flushPromises();

    expect(wrapper.findAll('.eye')).toHaveLength(2);
    expect(wrapper.findAll('.code-rain-container')).toHaveLength(2);
    expect(wrapper.findAll('.code-column').length).toBeGreaterThan(0);
  });
});
