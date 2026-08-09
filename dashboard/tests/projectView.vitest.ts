import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises } from '@vue/test-utils';
import ProjectView from '@/components/chat/ProjectView.vue';
import { initI18n } from '@/i18n/composables';
import { mountWithVuetify } from './utils/mountWithVuetify';

vi.mock('@/api/v1/chat', () => ({
  chatApi: {
    listProjectWorkspaceFiles: vi.fn(async () => ({
      data: { status: 'ok', data: { entries: [] } },
    })),
    previewProjectWorkspaceFile: vi.fn(),
  },
}));

describe('ProjectView layout', () => {
  beforeEach(async () => {
    await initI18n('zh-CN');
  });

  afterEach(async () => {
    await initI18n('en-US');
  });

  it('keeps a large session list scrollable above the composer slot', () => {
    const sessions = Array.from({ length: 120 }, (_, index) => ({
      session_id: `session-${index}`,
      display_name: `Session ${index}`,
      updated_at: '2026-08-04T12:00:00Z',
    }));
    const wrapper = mountWithVuetify(ProjectView, {
      props: {
        project: { project_id: 'project-1', title: 'Planning', emoji: 'P' },
        sessions,
      },
      slots: { default: '<div data-testid="project-composer">composer</div>' },
    });

    const list = wrapper.get('.project-sessions-list');
    const composer = wrapper.get('[data-testid="project-composer"]');
    expect(list.findAll('.project-session-item')).toHaveLength(120);
    expect(
      list.element.compareDocumentPosition(composer.element) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).not.toBe(0);
  });

  it('localizes the empty workspace state', async () => {
    const wrapper = mountWithVuetify(ProjectView, {
      props: {
        project: { project_id: 'project-1', title: 'Planning', emoji: 'P' },
        sessions: [],
      },
    });

    await flushPromises();

    expect(wrapper.find('.workspace-title').text()).toBe('工作区');
    expect(wrapper.text()).toContain('工作区暂无文件');
    expect(wrapper.text()).not.toContain('No workspace files');
  });
});
