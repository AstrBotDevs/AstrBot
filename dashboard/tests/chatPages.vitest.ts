import { beforeEach, describe, expect, it, vi } from 'vitest';
import ChatBoxPage from '@/views/ChatBoxPage.vue';
import ChatPage from '@/views/ChatPage.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

const customizer = vi.hoisted(() => ({
  uiTheme: 'AstrBotDark',
}));

vi.mock('@/stores/customizer', () => ({
  useCustomizerStore: () => customizer,
}));

vi.mock('@/components/chat/Chat.vue', () => ({
  default: {
    props: ['chatboxMode'],
    template:
      '<div data-testid="chat-stub">{{ chatboxMode ? "chatbox" : "page" }}</div>',
  },
}));

describe('Chat pages', () => {
  beforeEach(() => {
    customizer.uiTheme = 'AstrBotDark';
  });

  it('mounts ChatPage with the session Chat surface', () => {
    const wrapper = mountWithVuetify(ChatPage);
    expect(wrapper.get('[data-testid="chat-stub"]').text()).toBe('page');
  });

  it('mounts ChatBoxPage in chatbox mode under the customizer theme', () => {
    const wrapper = mountWithVuetify(ChatBoxPage);
    expect(wrapper.get('[data-testid="chat-stub"]').text()).toBe('chatbox');
    expect(wrapper.get('.chatbox-app').exists()).toBe(true);
  });
});
