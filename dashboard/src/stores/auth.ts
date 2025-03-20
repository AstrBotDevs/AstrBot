import { defineStore } from 'pinia';
import { router } from '@/router';
import axios from 'axios';

export const useAuthStore = defineStore({
  id: 'auth',
  state: () => ({
    // @ts-ignore
    username: '',
    returnUrl: null
  }),
  actions: {
    async login(username: string, password: string): Promise<void> {
      try {
        const res = await axios.post('/api/auth/login', {
          username: username,
          password: password
        });
    
        if (res.data.status === 'error') {
          return Promise.reject(res.data.message);
        }
    
        this.username = res.data.data.username
        localStorage.setItem('user', this.username);
        localStorage.setItem('token', res.data.data.token);
        localStorage.setItem('change_pwd_hint', res.data.data?.change_pwd_hint);
        router.push(this.returnUrl || '/dashboard/default');
      } catch (error) {
        return Promise.reject(error);
      }
    },
    logout() {
      this.username = '';
      localStorage.removeItem('username');
      localStorage.removeItem('token');
      router.push('/auth/login');
    },
    has_token(): boolean {
      return !!localStorage.getItem('token');
    }
  }
});
