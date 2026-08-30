import { afterEach, describe, expect, it, vi } from 'vitest';
import { flushPromises } from '@vue/test-utils';
import ChatMessageList from '@/components/chat/ChatMessageList.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

const testState = vi.hoisted(() => ({
  copyToClipboard: vi.fn(),
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
}));

vi.mock('axios', () => ({
  default: {
    get: vi.fn(),
    create: vi.fn(() => ({
      interceptors: {
        request: { use: vi.fn() },
        response: { use: vi.fn() },
      },
    })),
  },
}));

vi.mock('@/api/v1', () => ({
  fileApi: {
    contentUrl: (id: string) => `/attachments/${id}`,
    byNameUrl: (name: string) => `/files/${name}`,
  },
}));

vi.mock('markstream-vue', () => ({
  setCustomComponents: vi.fn(),
}));

vi.mock('@/components/chat/RegenerateMenu.vue', () => ({
  default: {
    template: '<div class="regenerate-menu-stub"></div>',
  },
}));

vi.mock('@/components/chat/ThreadedMarkdownMessagePart.vue', () => ({
  default: {
    props: ['text', 'threads'],
    emits: ['open-thread'],
    template:
      '<button class="threaded-markdown-stub" @click="$emit(\'open-thread\', threads[0])">{{ text }}</button>',
  },
}));

vi.mock('@/components/chat/MarkdownMessagePart.vue', () => ({
  default: {
    props: ['content'],
    template: '<div class="markdown-message-part-stub">{{ content }}</div>',
  },
}));

vi.mock('@/utils/clipboard', () => ({
  copyToClipboard: (...args: unknown[]) => testState.copyToClipboard(...args),
}));

vi.mock('@/utils/toast', () => ({
  useToast: () => ({
    success: testState.toastSuccess,
    error: testState.toastError,
  }),
}));

vi.mock('@/components/chat/message_list_comps/ReasoningBlock.vue', () => ({
  default: {
    props: ['parts', 'showSidebarAction', 'sidebarActive'],
    emits: ['open'],
    template:
      '<div class="reasoning-block-stub"><button class="reasoning-header-stub" type="button">{{ parts.length }}|{{ showSidebarAction }}</button><button v-if="showSidebarAction" class="reasoning-sidebar-btn-stub" type="button" @click="$emit(\'open\')">open sidebar</button></div>',
  },
}));

vi.mock('@/components/chat/message_list_comps/ToolCallCard.vue', () => ({
  default: {
    props: ['toolCall'],
    template:
      '<div class="tool-call-card-stub">{{ toolCall.name || "tool" }}</div>',
  },
}));

vi.mock('@/components/chat/message_list_comps/ToolCallItem.vue', () => ({
  default: {
    template:
      '<div class="tool-call-item-stub"><slot name="label" /><slot name="details" /></div>',
  },
}));

vi.mock('@/components/chat/message_list_comps/IPythonToolBlock.vue', () => ({
  default: {
    props: ['toolCall'],
    template:
      '<div class="ipython-tool-block-stub">{{ toolCall.name || "python" }}</div>',
  },
}));

vi.mock('@/components/chat/message_list_comps/ActionRef.vue', () => ({
  default: {
    props: ['refs'],
    emits: ['open-refs'],
    template:
      '<button class="action-ref-stub" @click="$emit(\'open-refs\', refs)">refs</button>',
  },
}));

vi.mock('@/components/shared/ThemeAwareMarkdownCodeBlock.vue', () => ({
  default: {
    template: '<div class="code-block-stub"></div>',
  },
}));

vi.mock('@/components/shared/StyledMenu.vue', () => ({
  default: {
    template:
      '<div class="styled-menu-stub"><slot name="activator" :props="{}" /><slot /></div>',
  },
}));

vi.mock('@/components/chat/message_list_comps/RefNode.vue', () => ({
  default: {
    template: '<span class="ref-node-stub"></span>',
  },
}));

vi.mock('@/components/chat/message_list_comps/ThreadNode.vue', () => ({
  default: {
    template: '<span class="thread-node-stub"></span>',
  },
}));

const botMessage = {
  id: 'bot-1',
  created_at: '2026-06-29T12:00:00Z',
  threads: [
    {
      thread_id: 'thread-1',
      parent_session_id: 'session-1',
      parent_message_id: 1,
      base_checkpoint_id: 'cp-1',
      selected_text: 'Investigate provider issue',
    },
  ],
  content: {
    type: 'bot',
    refs: {
      used: [
        {
          title: 'AstrBot Docs',
          url: 'https://example.com/docs',
        },
      ],
    },
    agentStats: {
      token_usage: { input_other: 12, output: 34 },
      duration: 1.2,
    },
    message: [
      {
        type: 'think',
        think: 'Step one',
      },
      {
        type: 'plain',
        text: 'Final answer',
      },
      {
        type: 'tool_call',
        tool_calls: [
          {
            id: 'tool-1',
            name: 'search_web',
            arguments: { query: 'astrbot' },
            finished_ts: 1,
          },
          {
            id: 'tool-2',
            name: 'python_exec',
            arguments: { code: 'print(1)' },
          },
        ],
      },
    ],
  },
};

const userMessage = {
  id: 'user-1',
  created_at: '2026-06-29T11:59:00Z',
  content: {
    type: 'user',
    message: [{ type: 'plain', text: 'Please investigate' }],
  },
};

describe('ChatMessageList smoke', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    testState.copyToClipboard.mockReset();
    testState.toastSuccess.mockReset();
    testState.toastError.mockReset();
  });

  it('renders mixed bot content and emits thread / refs actions without warnings', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    const wrapper = mountWithVuetify(ChatMessageList, {
      props: {
        messages: [
          {
            id: 'bot-1',
            created_at: '2026-06-29T12:00:00Z',
            threads: [
              {
                thread_id: 'thread-1',
                parent_session_id: 'session-1',
                parent_message_id: 1,
                base_checkpoint_id: 'cp-1',
                selected_text: 'Investigate provider issue',
              },
            ],
            content: {
              type: 'bot',
              refs: {
                used: [
                  {
                    title: 'AstrBot Docs',
                    url: 'https://example.com/docs',
                  },
                ],
              },
              agentStats: {
                token_usage: { input_other: 12, output: 34 },
                duration: 1.2,
              },
              message: [
                {
                  type: 'think',
                  think: 'Step one',
                },
                {
                  type: 'plain',
                  text: 'Final answer',
                },
                {
                  type: 'tool_call',
                  tool_calls: [
                    {
                      id: 'tool-1',
                      name: 'search_web',
                      arguments: { query: 'astrbot' },
                      finished_ts: 1,
                    },
                    {
                      id: 'tool-2',
                      name: 'python_exec',
                      arguments: { code: 'print(1)' },
                    },
                  ],
                },
              ],
            },
          },
        ],
        isDark: false,
        isStreaming: false,
        enableRegenerate: true,
        enableThreadSelection: true,
        manageRefsSidebar: false,
      },
    });

    await flushPromises();
    expect(wrapper.findAll('.reasoning-block-stub')).toHaveLength(2);
    expect(
      wrapper.findAll('.reasoning-header-stub').map((node) => node.text()),
    ).toEqual(['1|true', '1|true']);
    expect(wrapper.findAll('.reasoning-sidebar-btn-stub')).toHaveLength(2);
    expect(wrapper.find('.chat-message-list').classes()).not.toContain(
      'is-touch',
    );
    expect(wrapper.find('.message-meta-actions').exists()).toBe(true);
    expect(wrapper.find('.threaded-markdown-stub').text()).toBe('Final answer');
    expect(wrapper.find('.tool-call-card-stub').exists()).toBe(false);
    expect(wrapper.find('.ipython-tool-block-stub').exists()).toBe(false);

    await wrapper.find('.threaded-markdown-stub').trigger('click');
    expect(wrapper.emitted('openThread')?.[0]?.[0]).toMatchObject({
      thread_id: 'thread-1',
    });

    await wrapper.find('.action-ref-stub').trigger('click');
    expect(wrapper.emitted('openRefs')?.[0]?.[0]).toMatchObject({
      used: [{ title: 'AstrBot Docs', url: 'https://example.com/docs' }],
    });

    expect(
      warnSpy.mock.calls.some((args) =>
        args.some(
          (arg) =>
            String(arg).includes('Extraneous non-props attributes') ||
            String(arg).includes(
              'Component inside <Transition> renders non-element root node',
            ),
        ),
      ),
    ).toBe(false);
  });

  it('opens the reasoning sidebar from the dedicated button only', async () => {
    const wrapper = mountWithVuetify(ChatMessageList, {
      props: {
        messages: [botMessage],
      },
    });
    await flushPromises();

    await wrapper.find('.reasoning-header-stub').trigger('click');
    expect(wrapper.emitted('openReasoning')).toBeUndefined();

    await wrapper.find('.reasoning-sidebar-btn-stub').trigger('click');
    expect(wrapper.emitted('openReasoning')?.[0]?.[0]).toMatchObject({
      message: { id: 'bot-1' },
      blockIndex: 0,
    });
  });

  it('does not offer a sidebar action in the thread variant', async () => {
    const wrapper = mountWithVuetify(ChatMessageList, {
      props: {
        messages: [botMessage],
        variant: 'thread',
      },
    });
    await flushPromises();

    expect(wrapper.find('.reasoning-sidebar-btn-stub').exists()).toBe(false);
  });

  it('copies user and bot messages with a toast', async () => {
    testState.copyToClipboard.mockResolvedValue(true);
    const wrapper = mountWithVuetify(ChatMessageList, {
      props: {
        messages: [userMessage, botMessage],
      },
    });
    await flushPromises();

    const copyButtons = wrapper.findAll('.message-copy-btn');
    expect(copyButtons.length).toBeGreaterThanOrEqual(2);

    await copyButtons[0].trigger('click');
    await flushPromises();
    expect(testState.copyToClipboard).toHaveBeenCalled();
    expect(testState.toastSuccess).toHaveBeenCalledWith('Copied');
  });
});
