import { nextTick } from 'vue';
import { describe, expect, it } from 'vitest';
import DashboardStepUpDialog from '@/components/shared/DashboardStepUpDialog.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

describe('DashboardStepUpDialog', () => {
  it('emits credentials without retaining them after submission', async () => {
    const wrapper = mountWithVuetify(DashboardStepUpDialog, {
      props: { modelValue: true },
    });

    const inputs = document.body.querySelectorAll('input');
    const passwordInput = inputs[0] as HTMLInputElement;
    const codeInput = inputs[1] as HTMLInputElement;
    passwordInput.value = 'dashboard-password';
    passwordInput.dispatchEvent(new Event('input', { bubbles: true }));
    codeInput.value = '123456';
    codeInput.dispatchEvent(new Event('input', { bubbles: true }));
    await nextTick();
    const buttons = document.body.querySelectorAll('button');
    (buttons[buttons.length - 1] as HTMLButtonElement).click();
    await nextTick();

    expect(wrapper.emitted('confirm')).toEqual([
      [{ password: 'dashboard-password', code: '123456' }],
    ]);
    expect(passwordInput.value).toBe('');
    expect(codeInput.value).toBe('');

    wrapper.unmount();
  });

  it('requires a credential before confirming', async () => {
    const wrapper = mountWithVuetify(DashboardStepUpDialog, {
      props: { modelValue: true },
    });

    const buttons = document.body.querySelectorAll('button');
    (buttons[buttons.length - 1] as HTMLButtonElement).click();

    expect(wrapper.emitted('confirm')).toBeUndefined();
    wrapper.unmount();
  });
});
