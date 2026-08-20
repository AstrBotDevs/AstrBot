import { describe, expect, it, vi } from 'vitest';
import AboutPage from '@/views/AboutPage.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

describe('AboutPage', () => {
  it('opens repository and issue links from the hero actions', async () => {
    const open = vi.spyOn(window, 'open').mockImplementation(() => null);
    const wrapper = mountWithVuetify(AboutPage);
    const buttons = wrapper.findAll('button');
    expect(buttons.length).toBeGreaterThanOrEqual(2);
    await buttons[0].trigger('click');
    await buttons[1].trigger('click');
    expect(open).toHaveBeenCalled();
    open.mockRestore();
  });
});
