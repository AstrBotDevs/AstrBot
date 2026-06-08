import { defineStore } from 'pinia';
import { router } from '@/router';
import { authApi, providerApi, systemConfigApi } from '@/api/v1';

export const useAuthStore = defineStore("auth", {
  state: () => ({
    // @ts-ignore
    username: '',
    returnUrl: null,
  }),
  actions: {
    async finishAuthenticatedSession(data: any): Promise<void> {
      this.username = data.username;
      localStorage.setItem('user', this.username);
      localStorage.setItem('token', data.token);
      const passwordUpgradeRequired = !!data?.password_upgrade_required;
      const md5PwdHint = !!data?.md5_pwd_hint;
      const passwordWarning =
        !!data?.change_pwd_hint ||
        (md5PwdHint && !passwordUpgradeRequired);
      if (passwordWarning) {
        localStorage.setItem('change_pwd_hint', 'true');
        if (md5PwdHint && !passwordUpgradeRequired) {
          localStorage.setItem('md5_pwd_hint', 'true');
        } else {
          localStorage.removeItem('md5_pwd_hint');
        }
      } else {
        localStorage.removeItem('change_pwd_hint');
        localStorage.removeItem('md5_pwd_hint');
      }
      if (passwordUpgradeRequired) {
        localStorage.setItem('password_upgrade_required', 'true');
      } else {
        localStorage.removeItem('password_upgrade_required');
      }

      const onboardingCompleted = await this.checkOnboardingCompleted();
      this.returnUrl = null;
      if (passwordWarning) {
        router.push('/auth/setup');
        return;
      }
      if (onboardingCompleted) {
        router.push('/dashboard/default');
      } else {
        router.push('/welcome');
      }
    },
    async login(
      username: string,
      password: string,
      code?: string,
      trustDeviceToken = false,
    ): Promise<'totp_required' | void> {
      try {
        const res = await authApi.login({
          username,
          password,
          code,
          trust_device_flag: trustDeviceToken,
        });

        if (res.data.status === 'error') {
          return Promise.reject(res.data.message);
        }

        await this.finishAuthenticatedSession(res.data.data);
      } catch (error: any) {
        if (error?.response?.status === 401 && error.response?.data?.data?.totp_required) {
          return 'totp_required';
        }
        return Promise.reject(error?.response?.data?.message || error);
      }
    },
    async setup(
      username: string,
      password: string,
      confirmPassword: string,
    ): Promise<void> {
      try {
        const res = await authApi.setup({
          username,
          password,
          confirm_password: confirmPassword,
        });

        if (res.data.status === 'error') {
          return Promise.reject(res.data.message);
        }

        await this.finishAuthenticatedSession(res.data.data);
      } catch (error) {
        return Promise.reject(error);
      }
    },
    async checkOnboardingCompleted(): Promise<boolean> {
      try {
        // 1. 检查平台配置
        const platformRes = await systemConfigApi.get();
        const systemConfig = (platformRes.data.data as any).config || {};
        const hasPlatform = (systemConfig.platform || []).length > 0;
        if (!hasPlatform) return false;

        // 2. 检查提供者配置
        const providerRes = await providerApi.schema();
        const providers = providerRes.data.data?.providers || [];
        const sources = providerRes.data.data?.provider_sources || [];
        const sourceMap = new Map();
        sources.forEach((s: any) => sourceMap.set(s.id, s.provider_type));
        
        const hasProvider = providers.some((provider: any) => {
          if (provider.provider_type) return provider.provider_type === 'chat_completion';
          if (provider.provider_source_id) {
            const type = sourceMap.get(provider.provider_source_id);
            if (type === 'chat_completion') return true;
          }
          return String(provider.type || '').includes('chat_completion');
        });

        return hasProvider;
      } catch (e) {
        console.error('Failed to check onboarding status:', e);
        return false;
      }
    },
    logout() {
      this.username = '';
      localStorage.removeItem('user');
      localStorage.removeItem('token');
      localStorage.removeItem('change_pwd_hint');
      localStorage.removeItem('md5_pwd_hint');
      localStorage.removeItem('password_upgrade_required');
      void authApi.logout().catch(() => undefined);
      router.push('/auth/login');
    },
    has_token(): boolean {
      return !!localStorage.getItem('token');
    }
  }
});
