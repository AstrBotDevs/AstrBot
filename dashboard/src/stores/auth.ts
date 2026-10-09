import { defineStore } from 'pinia';
import { router } from '@/router';
import {
  authApi,
  UPGRADE_RECOVERY_EVENT,
  UPGRADE_RECOVERY_TOKEN_KEY,
  type ApiEnvelope,
  type VersionData,
} from '@/api/v1';
import { httpClient } from '@/api/http';

export const useAuthStore = defineStore("auth", {
  state: () => ({
    // @ts-ignore
    username: '',
    returnUrl: null,
  }),
  actions: {
    async finishAuthenticatedSession(data: any, continueSetup = false): Promise<void> {
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

      this.returnUrl = null;
      if (passwordWarning) {
        router.push('/auth/setup');
        return;
      }
      if (continueSetup && data?.onboarding_required === true) {
        router.replace('/auth/onboarding');
      } else {
        router.push('/dashboard/default');
      }
    },
    async login(
      username: string,
      password: string,
      code?: string,
      trustDeviceToken = false,
    ): Promise<'totp_required' | 'upgrade_recovery_required' | void> {
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

        const legacyToken = String(res.data.data?.token || '');
        if (res.legacyFallback && legacyToken) {
          const versionRes = await httpClient.get<ApiEnvelope<VersionData>>(
            '/api/stat/version',
            {
              headers: {
                Authorization: `Bearer ${legacyToken}`,
              },
              validateStatus: () => true,
            },
          );
          const versionData = versionRes.data?.data || {};
          const coreVersion = String(versionData.version || '')
            .trim()
            .replace(/^v/i, '');
          const dashboardVersion = String(versionData.dashboard_version || '')
            .trim()
            .replace(/^v/i, '');
          if (
            versionRes.status < 400 &&
            coreVersion &&
            dashboardVersion &&
            coreVersion !== dashboardVersion
          ) {
            sessionStorage.setItem(UPGRADE_RECOVERY_TOKEN_KEY, legacyToken);
            window.dispatchEvent(
              new CustomEvent(UPGRADE_RECOVERY_EVENT, {
                detail: {
                  version: versionData.version,
                  dashboard_version: versionData.dashboard_version,
                  blocking: true,
                },
              }),
            );
            return 'upgrade_recovery_required';
          }
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

        await this.finishAuthenticatedSession(res.data.data, true);
      } catch (error) {
        return Promise.reject(error);
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
