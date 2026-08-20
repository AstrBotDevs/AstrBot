import { flushPromises } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import AuthorizationPage from '@/views/AuthorizationPage.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

const api = vi.hoisted(() => ({
  bindings: vi.fn(),
  audit: vi.fn(),
  accounts: vi.fn(),
  stepUp: vi.fn(),
  issueBatchRevokeStepUp: vi.fn(),
  revokeBatch: vi.fn(),
  createAccount: vi.fn(),
  updateAccount: vi.fn(),
}));

const toast = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
}));

vi.mock('@/api/v1/authorization', () => ({
  authorizationApi: api,
}));

vi.mock('@/utils/toast', () => ({
  useToast: () => toast,
}));

vi.mock('@/components/shared/DashboardStepUpDialog.vue', () => ({
  default: {
    name: 'DashboardStepUpDialog',
    props: ['modelValue', 'loading', 'errorMessage'],
    emits: ['confirm', 'cancel', 'update:modelValue'],
    template: `
      <div v-if="modelValue" data-testid="step-up-dialog">
        <button data-testid="confirm-step-up" @click="$emit('confirm', { password: 'not-a-real-password' })">confirm</button>
      </div>
    `,
  },
}));

function apiResponse(data: unknown) {
  return { data: { status: 'ok', data } };
}

const bindings = [
  {
    binding_id: 'bind-user',
    subject_id: 'user:alice',
    role: 'session_admin',
    scope_type: 'session',
    scope_id: 'session-1',
    config_id: 'default',
    source: 'dashboard',
    expires_at: null,
  },
  {
    binding_id: 'bind-adapter',
    subject_id: 'platform:qq',
    role: 'member',
    scope_type: 'session',
    scope_id: 'session-2',
    config_id: 'default',
    source: 'adapter',
    expires_at: null,
  },
];

describe('AuthorizationPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.bindings.mockResolvedValue(apiResponse(bindings));
    api.audit.mockResolvedValue(apiResponse([]));
    api.accounts.mockResolvedValue(
      apiResponse([
        {
          account_id: 'acct-1',
          username: 'astrbot',
          is_active: true,
          last_login_at: null,
        },
      ]),
    );
  });

  it('loads bindings and keeps adapter facts read-only', async () => {
    const wrapper = mountWithVuetify(AuthorizationPage);
    await flushPromises();

    expect(wrapper.text()).toContain('user:alice');
    expect(wrapper.text()).toContain('platform:qq');
    expect(wrapper.findAll('input[type="checkbox"]')).toHaveLength(1);
    expect(wrapper.find('.mdi-lock-outline').exists()).toBe(true);
  });

  it('filters bindings by the search query', async () => {
    const wrapper = mountWithVuetify(AuthorizationPage);
    await flushPromises();

    const field = wrapper.get('input[type="text"]');
    await field.setValue('alice');
    await flushPromises();

    expect(wrapper.text()).toContain('user:alice');
    expect(wrapper.text()).not.toContain('platform:qq');
  });

  it('issues a batch step-up token before revoking selected bindings', async () => {
    api.issueBatchRevokeStepUp.mockResolvedValue(
      apiResponse({ token: 'step-up-token' }),
    );
    api.revokeBatch.mockResolvedValue(apiResponse({}));
    api.bindings
      .mockResolvedValueOnce(apiResponse(bindings))
      .mockResolvedValueOnce(apiResponse([bindings[1]]));

    const wrapper = mountWithVuetify(AuthorizationPage, {
      global: {
        stubs: {
          VDialog: {
            props: ['modelValue'],
            template: '<div><slot /></div>',
          },
        },
      },
    });
    await flushPromises();

    await wrapper.get('input[type="checkbox"]').setValue(true);
    const revokeButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('Revoke selected'));
    expect(revokeButton).toBeDefined();
    await revokeButton!.trigger('click');
    await flushPromises();

    const revokeCard = wrapper
      .findAll('.v-card')
      .find((card) => card.text().includes('Revoke selected bindings?'));
    expect(revokeCard).toBeDefined();
    const confirmRevoke = revokeCard!
      .findAll('button')
      .find((button) => button.text().trim() === 'Continue');
    expect(confirmRevoke).toBeDefined();
    await confirmRevoke!.trigger('click');
    await flushPromises();

    await wrapper.get('[data-testid="confirm-step-up"]').trigger('click');
    await flushPromises();

    expect(api.issueBatchRevokeStepUp).toHaveBeenCalledWith({
      binding_ids: ['bind-user'],
      password: 'not-a-real-password',
      code: undefined,
    });
    expect(api.revokeBatch).toHaveBeenCalledWith(
      ['bind-user'],
      'step-up-token',
    );
  });
});
