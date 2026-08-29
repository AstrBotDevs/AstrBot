import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import { defineComponent } from 'vue';
import VerticalSidebar from '@/layouts/full/vertical-sidebar/VerticalSidebar.vue';
import { useCustomizerStore } from '@/stores/customizer';
import { mountWithVuetify } from './utils/mountWithVuetify';

vi.mock('@/layouts/full/vertical-sidebar/sidebarItem', () => ({
  default: [
    {
      title: 'core.navigation.data',
      icon: 'mdi-view-dashboard-outline',
      to: '/dashboard',
    },
  ],
}));

vi.mock('@/layouts/full/vertical-sidebar/NavItem.vue', () => ({
  default: {
    props: ['item', 'rail'],
    template: '<div class="nav-item-stub">{{ item.title }}</div>',
  },
}));

vi.mock('@/utils/sidebarCustomization', () => ({
  applySidebarCustomization: (items: unknown) => items,
}));

const VerticalSidebarHost = defineComponent({
  name: 'VerticalSidebarHost',
  components: {
    VerticalSidebar,
  },
  template: `
    <v-app>
      <v-layout>
        <VerticalSidebar />
      </v-layout>
    </v-app>
  `,
});

describe('VerticalSidebar smoke', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network')));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('keeps the GitHub shortcut usable when the star count request fails', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const debugSpy = vi.spyOn(console, 'debug').mockImplementation(() => {});

    const wrapper = mountWithVuetify(VerticalSidebarHost, {
      global: {
        stubs: {
          ChangelogDialog: {
            template: '<div class="changelog-dialog-stub"></div>',
          },
        },
      },
    });

    const customizer = useCustomizerStore();
    customizer.mini_sidebar = false;
    customizer.Sidebar_drawer = true;

    await flushPromises();

    expect(fetch).toHaveBeenCalledWith(
      'https://api.github.com/repos/Xero-Team/AstrBot',
      expect.objectContaining({
        headers: expect.objectContaining({
          Accept: 'application/vnd.github+json',
        }),
      }),
    );
    expect(wrapper.text()).toContain('GitHub');
    expect(
      warnSpy.mock.calls.some((args) =>
        args.some((arg) => String(arg).includes('star count')),
      ),
    ).toBe(false);
    expect(
      errorSpy.mock.calls.some((args) =>
        args.some((arg) => String(arg).includes('star count')),
      ),
    ).toBe(false);
    expect(
      debugSpy.mock.calls.some((args) =>
        args.some((arg) => String(arg).includes('star count')),
      ),
    ).toBe(false);

    wrapper.unmount();
  });
});
