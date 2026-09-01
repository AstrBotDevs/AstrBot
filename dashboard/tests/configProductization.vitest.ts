import { describe, expect, it } from 'vitest';
import ConfigProfileMenu from '@/components/config/ConfigProfileMenu.vue';
import ProviderSelectMenu from '@/components/shared/ProviderSelectMenu.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

describe('configuration productization controls', () => {
  it('shows the configured profile name and emits profile selection', async () => {
    const wrapper = mountWithVuetify(ConfigProfileMenu, {
      props: {
        modelValue: 'profile-1',
        items: [
          { id: 'default', name: 'Default' },
          { id: 'profile-1', name: 'Production' },
        ],
      },
    });

    expect(wrapper.find('.config-profile-trigger__title').text()).toBe(
      'Production',
    );

    await wrapper.find('.config-profile-trigger').trigger('click');
    const profileItems = document.body.querySelectorAll(
      '.config-profile-menu__item',
    );
    expect(profileItems).toHaveLength(2);
    await (profileItems[0] as HTMLElement).click();

    expect(wrapper.emitted('select')?.[0]).toEqual(['default']);
  });

  it('uses the stored model name for the chat input trigger', () => {
    const wrapper = mountWithVuetify(ProviderSelectMenu, {
      props: {
        modelValue: 'provider-1',
        fallbackModel: 'gpt-4o',
        variant: 'input',
      },
    });

    expect(wrapper.find('.provider-trigger-title').text()).toBe('gpt-4o');
  });

  it('honors a custom trigger label for config selectors', () => {
    const wrapper = mountWithVuetify(ProviderSelectMenu, {
      props: {
        variant: 'config',
        buttonText: 'Select provider pool',
      },
    });

    expect(wrapper.find('.provider-trigger-title').text()).toBe(
      'Select provider pool',
    );
  });
});
