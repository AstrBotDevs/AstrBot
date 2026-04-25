import { defineStore } from 'pinia';
import { router } from '@/router';
import axios from 'axios';

function readJsonStorage(key: string, fallback: any) {
  try {
    const value = localStorage.getItem(key);
    return value ? JSON.parse(value) : fallback;
  } catch {
    return fallback;
  }
}

export const useAuthStore = defineStore("auth", {
  state: () => ({
    // @ts-ignore
    username: '',
    role: localStorage.getItem('webui_role') || 'admin',
    scopes: readJsonStorage('webui_scopes', ['*']),
    permissions: readJsonStorage('webui_permissions', {}),
    returnUrl: null
  }),
  actions: {
    persistProfile(profile: any) {
      this.username = profile?.username || '';
      this.role = profile?.role || 'admin';
      this.scopes = profile?.scopes || ['*'];
      this.permissions = profile?.permissions || {};
      localStorage.setItem('user', this.username);
      localStorage.setItem('webui_role', this.role);
      localStorage.setItem('webui_scopes', JSON.stringify(this.scopes));
      localStorage.setItem('webui_permissions', JSON.stringify(this.permissions));
    },
    isChatUIScoped(): boolean {
      return this.role === 'webui_user'
        && Array.isArray(this.scopes)
        && this.scopes.length === 1
        && this.scopes[0] === 'chatui';
    },
    canManageProviders(): boolean {
      if (this.role === 'admin') return true;
      return Boolean(this.permissions?.allow_provider_management);
    },
    async loadProfile(): Promise<any> {
      const res = await axios.get('/api/auth/profile');
      if (res.data.status === 'ok') {
        this.persistProfile(res.data.data);
        return res.data.data;
      }
      return Promise.reject(res.data.message);
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
    
        this.persistProfile({
          username: res.data.data.username,
          role: res.data.data.role || 'admin',
          scopes: res.data.data.scopes || ['*'],
          permissions: res.data.data.permissions || {}
        });
        localStorage.setItem('token', res.data.data.token);
        localStorage.setItem('change_pwd_hint', res.data.data?.change_pwd_hint);

        if (this.isChatUIScoped()) {
          this.returnUrl = null;
          router.push('/chat');
          return;
        }
        
        const onboardingCompleted = await this.checkOnboardingCompleted();
        this.returnUrl = null;
        if (onboardingCompleted) {
          router.push('/dashboard/default');
        } else {
          router.push('/welcome');
        }
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
    clearSession() {
      this.username = '';
      this.role = 'admin';
      this.scopes = ['*'];
      this.permissions = {};
      localStorage.removeItem('user');
      localStorage.removeItem('token');
      localStorage.removeItem('webui_role');
      localStorage.removeItem('webui_scopes');
      localStorage.removeItem('webui_permissions');
    },
    logout() {
      this.clearSession();
      router.push('/auth/login');
    },
    has_token(): boolean {
      return !!localStorage.getItem('token');
    }
  }
});
