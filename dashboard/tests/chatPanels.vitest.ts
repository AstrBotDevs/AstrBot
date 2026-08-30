/* eslint-disable vue/one-component-per-file */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, nextTick } from 'vue';
import { flushPromises } from '@vue/test-utils';
import ReasoningSidebar from '@/components/chat/ReasoningSidebar.vue';
import ThreadPanel from '@/components/chat/ThreadPanel.vue';
import RefsSidebar from '@/components/chat/message_list_comps/RefsSidebar.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

const testState = vi.hoisted(() => ({
  getThreadMock: vi.fn(),
  fetchWithAuthMock: vi.fn(),
  chatMessageListStub: {
    props: ['messages'],
    template:
      '<div class="chat-message-list-stub">{{ messages[1]?.content?.message?.[0]?.text || messages.length }}</div>',
  },
  reasoningTimelineStub: {
    props: ['parts', 'reasoning'],
    template:
      '<div class="reasoning-timeline-stub">{{ parts.length }}-{{ reasoning || "" }}</div>',
  },
}));

vi.mock('@/api/v1', () => ({
  chatApi: {
    getThread: testState.getThreadMock,
    sendThreadMessageUrl: (threadId: string) => `/threads/${threadId}/messages`,
  },
}));

vi.mock('@/api/http', () => ({
  fetchWithAuth: testState.fetchWithAuthMock,
}));

vi.mock('@/components/chat/ChatMessageList.vue', () => ({
  default: testState.chatMessageListStub,
}));

vi.mock('@/components/chat/message_list_comps/ReasoningTimeline.vue', () => ({
  default: testState.reasoningTimelineStub,
}));

function hasNonElementRootWarning(calls: unknown[][]) {
  return calls.some((args) =>
    args.some((arg) =>
      String(arg).includes(
        'Component inside <Transition> renders non-element root node',
      ),
    ),
  );
}

describe('chat side panels', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders ReasoningSidebar inside a parent Transition without root warnings', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const Host = defineComponent({
      components: { ReasoningSidebar },
      data: () => ({ open: true }),
      template:
        '<Transition name="host-fade"><ReasoningSidebar v-if="open" v-model="open" :parts="[]" reasoning="step 1" /></Transition>',
    });

    const wrapper = mountWithVuetify(Host);
    await flushPromises();

    expect(wrapper.find('.reasoning-timeline-stub').text()).toBe('0-step 1');
    expect(
      wrapper.find('.reasoning-sidebar [aria-label="Close"]').exists(),
    ).toBe(true);
    expect(hasNonElementRootWarning(warnSpy.mock.calls)).toBe(false);
  });

  it('renders RefsSidebar inside a parent Transition without root warnings', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const Host = defineComponent({
      components: { RefsSidebar },
      data: () => ({
        open: true,
        refs: [
          {
            title: 'AstrBot Docs',
            url: 'https://example.com/docs',
          },
        ],
      }),
      template:
        '<Transition name="host-fade"><RefsSidebar v-if="open" v-model="open" :refs="refs" /></Transition>',
    });

    const wrapper = mountWithVuetify(Host);
    await flushPromises();

    expect(wrapper.text()).toContain('AstrBot Docs');
    expect(hasNonElementRootWarning(warnSpy.mock.calls)).toBe(false);
  });

  it('renders ThreadPanel inside a parent Transition without root warnings', async () => {
    testState.getThreadMock.mockResolvedValue({
      data: {
        data: {
          history: [],
        },
      },
    });
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const Host = defineComponent({
      components: { ThreadPanel },
      data: () => ({
        open: true,
        thread: {
          thread_id: 'thread-1',
          selected_text: 'Selected thread excerpt',
        },
      }),
      template:
        '<Transition name="host-fade"><ThreadPanel v-if="open" v-model="open" :thread="thread" :is-dark="false" /></Transition>',
    });

    const wrapper = mountWithVuetify(Host);
    await flushPromises();
    await nextTick();

    expect(testState.getThreadMock).toHaveBeenCalledWith('thread-1');
    expect(wrapper.text()).toContain('Selected thread excerpt');
    expect(wrapper.find('.chat-message-list-stub').exists()).toBe(true);
    expect(hasNonElementRootWarning(warnSpy.mock.calls)).toBe(false);
  });

  it('restores a missing final SSE suffix in thread responses', async () => {
    testState.getThreadMock.mockResolvedValue({
      data: {
        data: {
          history: [],
        },
      },
    });
    const streamData = [
      {
        ct: 'chat',
        type: 'plain',
        data: 'partial',
        streaming: true,
      },
      {
        ct: 'chat',
        type: 'complete',
        data: 'partial response',
      },
    ]
      .map((payload) => `data: ${JSON.stringify(payload)}\n\n`)
      .join('');
    testState.fetchWithAuthMock.mockResolvedValue({
      ok: true,
      body: new ReadableStream<Uint8Array>({
        start(controller) {
          controller.enqueue(new TextEncoder().encode(streamData));
          controller.close();
        },
      }),
    });

    const wrapper = mountWithVuetify(ThreadPanel, {
      props: {
        modelValue: true,
        thread: {
          thread_id: 'thread-1',
          selected_text: 'Selected thread excerpt',
        },
        isDark: false,
      },
    });
    await flushPromises();
    await wrapper.find('.thread-input').setValue('Question');
    await wrapper.find('.thread-composer').trigger('submit');
    await flushPromises();

    expect(testState.fetchWithAuthMock).toHaveBeenCalledWith(
      '/threads/thread-1/messages',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(wrapper.find('.chat-message-list-stub').text()).toContain(
      'partial response',
    );
  });
});
