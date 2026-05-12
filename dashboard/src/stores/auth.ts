import { defineStore } from 'pinia';
import { router } from '@/router';
import axios from 'axios';

export const useAuthStore = defineStore("auth", {
  state: () => ({
    // @ts-ignore
    username: '',
    returnUrl: null
  }),
  actions: {
    async finishAuthenticatedSession(data: any): Promise<void> {
      this.username = data.username;
      localStorage.setItem('user', this.username);
      localStorage.setItem('token', data.token);
      const passwordUpgradeRequired = !!data?.password_upgrade_required;
      const passwordWarning =
        !!data?.change_pwd_hint ||
        (!!data?.legacy_pwd_hint && !passwordUpgradeRequired);
      if (passwordWarning) {
        localStorage.setItem('change_pwd_hint', 'true');
        if (data?.legacy_pwd_hint && !passwordUpgradeRequired) {
          localStorage.setItem('legacy_pwd_hint', 'true');
        } else {
          localStorage.removeItem('legacy_pwd_hint');
        }
      } else {
        localStorage.removeItem('change_pwd_hint');
        localStorage.removeItem('legacy_pwd_hint');
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
    async login(username: string, password: string): Promise<void> {
      try {
        const res = await axios.post('/api/auth/login', {
          username: username,
          password: password
        });
    
        if (res.data.status === 'error') {
          return Promise.reject(res.data.message);
        }

        await this.finishAuthenticatedSession(res.data.data);
      } catch (error) {
        return Promise.reject(error);
      }
    },
    async setup(username: string, password: string, confirmPassword: string): Promise<void> {
      try {
        const setupEndpoint = this.has_token() ? '/api/auth/setup-authenticated' : '/api/auth/setup';
        const res = await axios.post(setupEndpoint, {
          username: username,
          password: password,
          confirm_password: confirmPassword
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
        const platformRes = await axios.get('/api/config/get');
        const hasPlatform = (platformRes.data.data.config.platform || []).length > 0;
        if (!hasPlatform) return false;

        // 2. 检查提供者配置
        const providerRes = await axios.get('/api/config/provider/template');
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
      localStorage.removeItem('legacy_pwd_hint');
      localStorage.removeItem('password_upgrade_required');
      void axios.post('/api/auth/logout').catch(() => undefined);
      router.push('/auth/login');
    },
    has_token(): boolean {
      return !!localStorage.getItem('token');
    }
  }
});
