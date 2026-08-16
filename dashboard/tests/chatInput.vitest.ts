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

vi.mock('@/api/v1', () => ({
  commandApi: {
    list: vi.fn().mockResolvedValue({
      data: { status: 'ok', data: { items: [], wake_prefix: ['/'] } },
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

    expect(wrapper.get('input.chat-text-input').attributes('placeholder')).toBe(
      'Default prompt',
    );
  });

  it('uses custom placeholders, including an intentional empty string', async () => {
    const wrapper = mountWithVuetify(ChatInput, {
      props: { ...baseProps, placeholder: 'Project prompt' },
    });
    await flushPromises();
    expect(wrapper.get('input.chat-text-input').attributes('placeholder')).toBe(
      'Project prompt',
    );

    await wrapper.setProps({ placeholder: '' });
    expect(wrapper.get('input.chat-text-input').attributes('placeholder')).toBe(
      '',
    );
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
