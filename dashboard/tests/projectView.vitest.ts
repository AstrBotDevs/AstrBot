import { describe, expect, it } from 'vitest';
import ProjectView from '@/components/chat/ProjectView.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

describe('ProjectView layout', () => {
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
});
