import { describe, expect, it } from 'vitest';
import AlkaidPage from '@/views/AlkaidPage.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

describe('AlkaidPage', () => {
  it('renders a router outlet for nested Alkaid views', () => {
    const wrapper = mountWithVuetify(AlkaidPage, {
      global: {
        stubs: {
          'router-view': {
            template: '<div data-testid="alkaid-outlet"></div>',
          },
        },
      },
    });

    expect(wrapper.get('.alkaid-page').exists()).toBe(true);
    expect(wrapper.get('[data-testid="alkaid-outlet"]').exists()).toBe(true);
  });
});
