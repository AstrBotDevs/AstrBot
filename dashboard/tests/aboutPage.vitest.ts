import { describe, expect, it, vi } from 'vitest';
import AboutPage from '@/views/AboutPage.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

describe('AboutPage', () => {
  it('opens the repository link from the hero action', async () => {
    const open = vi.spyOn(window, 'open').mockImplementation(() => null);
    const wrapper = mountWithVuetify(AboutPage);
    const buttons = wrapper.findAll('button');
    expect(buttons.length).toBe(1);
    await buttons[0].trigger('click');
    expect(open).toHaveBeenCalledWith(
      'https://github.com/Xero-Team/AstrBot',
      '_blank',
    );
    open.mockRestore();
  });
});
