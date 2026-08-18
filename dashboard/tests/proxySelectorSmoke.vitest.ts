import { describe, expect, it, vi } from 'vitest';
import ProxySelector from '@/components/shared/ProxySelector.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

describe('ProxySelector smoke', () => {
  it('does not offer custom GitHub mirrors', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const wrapper = mountWithVuetify(ProxySelector);
    expect(wrapper.text()).toContain('GitHub');
    expect(wrapper.find('input').exists()).toBe(false);
    expect(
      warn.mock.calls.flatMap((args) => args.map((arg) => String(arg))).some(
        (text) => text.includes('Translation key not found'),
      ),
    ).toBe(false);
    wrapper.unmount();
    warn.mockRestore();
  });
});
