import { flushPromises } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import LoginPage from '@/views/authentication/auth/LoginPage.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

const state = vi.hoisted(() => ({
  hasToken: vi.fn(),
  checkOnboardingCompleted: vi.fn(),
  routerPush: vi.fn(),
  setupStatus: vi.fn(),
  versions: vi.fn(),
}));

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    has_token: state.hasToken,
    checkOnboardingCompleted: state.checkOnboardingCompleted,
  }),
}));

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: state.routerPush }),
}));

vi.mock('@/stores/customizer', () => ({
  useCustomizerStore: () => ({
    themeMode: 'light',
    SET_THEME_MODE: vi.fn(),
  }),
}));

vi.mock('@/api/v1', () => ({
  authApi: { setupStatus: state.setupStatus },
  publicApi: { versions: state.versions },
}));

vi.mock('@/views/authentication/authForms/AuthLogin.vue', () => ({
  default: {
    setup(_, { expose }: { expose: (value: { stage: string }) => void }) {
      expose({ stage: 'account' });
    },
    template: '<div class="auth-login-stub"></div>',
  },
}));

vi.mock('@/components/shared/LanguageSwitcher.vue', () => ({
  default: { template: '<div class="language-switcher-stub"></div>' },
}));

describe('LoginPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    state.hasToken.mockReturnValue(false);
    state.checkOnboardingCompleted.mockResolvedValue(false);
    state.setupStatus.mockResolvedValue({
      data: { data: { setup_required: false } },
    });
    state.versions.mockResolvedValue({ data: { data: {} } });
  });

  it('cancels its delayed initialization reveal on unmount', async () => {
    const setTimeoutSpy = vi.spyOn(window, 'setTimeout');
    const clearTimeoutSpy = vi.spyOn(window, 'clearTimeout');
    const wrapper = mountWithVuetify(LoginPage);
    await flushPromises();

    const revealTimer = setTimeoutSpy.mock.results.find(
      (_result, index) => setTimeoutSpy.mock.calls[index]?.[1] === 100,
    )?.value;
    expect(revealTimer).toBeDefined();

    wrapper.unmount();

    expect(clearTimeoutSpy).toHaveBeenCalledWith(revealTimer);
  });

  it('uses the current favicon on the login page', async () => {
    const wrapper = mountWithVuetify(LoginPage);
    await flushPromises();

    const logo = wrapper.get('[data-testid="login-logo"]');
    expect(logo.attributes('src')).toBe('/favicon.svg');

    wrapper.unmount();
  });

  it('does not log sensitive public-version transport failures during initialization', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    state.versions.mockRejectedValue(
      new Error('Bearer login-secret at http://internal.example/version'),
    );
    const wrapper = mountWithVuetify(LoginPage);
    await flushPromises();

    expect(warnSpy.mock.calls.flat().join(' ')).not.toContain('login-secret');
    expect(warnSpy.mock.calls.flat().join(' ')).not.toContain(
      'internal.example',
    );

    wrapper.unmount();
  });
});
