import { afterEach, describe, expect, it, vi } from 'vitest';
import { flushPromises } from '@vue/test-utils';
import ChatMessageList from '@/components/chat/ChatMessageList.vue';
import ProjectList from '@/components/chat/ProjectList.vue';
import ToolCallItem from '@/components/chat/message_list_comps/ToolCallItem.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

const testState = vi.hoisted(() => ({
  copyToClipboard: vi.fn(),
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
}));

vi.mock('markstream-vue', () => ({
  setCustomComponents: vi.fn(),
}));

vi.mock('@/api/v1', () => ({
  fileApi: {
    contentUrl: (id: string) => `/attachments/${id}`,
    byNameUrl: (name: string) => `/files/${name}`,
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

describe('chat interaction smokes', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('expands ProjectList and emits actions without transition warnings', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const confirmSpy = vi.fn(async () => true);

    const wrapper = mountWithVuetify(ProjectList, {
      props: {
        initialExpanded: false,
        selectedProjectId: 'project-1',
        projects: [
          {
            project_id: 'project-1',
            title: 'Inbox',
            emoji: '📁',
            created_at: '2026-06-30T00:00:00Z',
            updated_at: '2026-06-30T00:00:00Z',
          },
        ],
      },
      global: {
        provide: {
          $confirm: confirmSpy,
        },
      },
    });

    await flushPromises();

    expect(wrapper.find('.project-list-wrap').isVisible()).toBe(false);

    await wrapper.find('.project-btn').trigger('click');
    await flushPromises();

    expect(wrapper.find('.project-list-wrap').isVisible()).toBe(true);
    expect(wrapper.text()).toContain('Inbox');

    await wrapper.find('.create-project-item').trigger('click');
    expect(wrapper.emitted('createProject')).toHaveLength(1);

    await wrapper.find('.project-item').trigger('click');
    expect(wrapper.emitted('selectProject')?.[0]).toEqual(['project-1']);

    await wrapper.find('.edit-project-btn').trigger('click');
    expect(wrapper.emitted('editProject')).toHaveLength(1);

    await wrapper.find('.delete-project-btn').trigger('click');
    await flushPromises();
    expect(confirmSpy).toHaveBeenCalledTimes(1);
    expect(wrapper.emitted('deleteProject')?.[0]).toEqual(['project-1']);

    expect(
      warnSpy.mock.calls.some((args) =>
        args.some((arg) =>
          String(arg).includes(
            'Component inside <Transition> renders non-element root node',
          ),
        ),
      ),
    ).toBe(false);
  });

  it('toggles ToolCallItem inline details without transition warnings', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    const wrapper = mountWithVuetify(ToolCallItem, {
      props: {
        isDark: true,
      },
      slots: {
        label: '<span class="tool-call-label">Run tool</span>',
        details: '<div class="tool-call-details-content">Tool output</div>',
      },
    });

    await flushPromises();

    expect(wrapper.find('.tool-call-details-content').exists()).toBe(false);

    await wrapper.find('.tool-call-line').trigger('click');
    await flushPromises();

    expect(wrapper.find('.tool-call-details-content').text()).toBe(
      'Tool output',
    );
    expect(wrapper.find('.tool-call-inline-details').classes()).toContain(
      'is-dark',
    );

    await wrapper.find('.tool-call-line').trigger('keydown.space');
    await flushPromises();
    expect(wrapper.find('.tool-call-details-content').exists()).toBe(false);

    expect(
      warnSpy.mock.calls.some((args) =>
        args.some((arg) =>
          String(arg).includes(
            'Component inside <Transition> renders non-element root node',
          ),
        ),
      ),
    ).toBe(false);
  });

  it('toasts copied messages and hides actions until hover on non-touch', async () => {
    testState.copyToClipboard.mockResolvedValue(true);
    const wrapper = mountWithVuetify(ChatMessageList, {
      props: {
        messages: [
          {
            id: 'user-1',
            created_at: '2026-06-29T12:00:00Z',
            content: {
              type: 'user',
              message: [{ type: 'plain', text: 'hello' }],
            },
          },
        ],
        isTouchDevice: false,
      },
    });
    await flushPromises();

    expect(wrapper.find('.chat-message-list').classes()).not.toContain(
      'is-touch',
    );
    expect(wrapper.find('.message-meta-actions').exists()).toBe(true);

    await wrapper.find('.message-copy-btn').trigger('click');
    await flushPromises();
    expect(testState.copyToClipboard).toHaveBeenCalledWith(
      'hello',
      expect.any(Object),
    );
    expect(testState.toastSuccess).toHaveBeenCalledWith('Copied');
  });
});
