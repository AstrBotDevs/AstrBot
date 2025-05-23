import { createRouter, createWebHistory } from 'vue-router';
import MainRoutes from './MainRoutes';
import AuthRoutes from './AuthRoutes';
import { useAuthStore } from '@/stores/auth';

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    MainRoutes,
    AuthRoutes
  ]
});

interface AuthStore {
  username: string;
  returnUrl: string | null;
  login(username: string, password: string): Promise<void>;
  logout(): void;
  has_token(): boolean;
}

router.beforeEach(async (to, from, next) => {
  const publicPages = ['/auth/login'];
  const authRequired = !publicPages.includes(to.path);
  const auth: AuthStore = useAuthStore();

  // 如果用户已登录且试图访问登录页面，则重定向到首页或之前尝试访问的页面
  if (to.path === '/auth/login' && auth.has_token()) {
    return next(auth.returnUrl || '/');
  }

  if (to.matched.some((record) => record.meta.requiresAuth)) {
    if (authRequired && !auth.has_token()) {
      auth.returnUrl = to.fullPath;
      return next('/auth/login');
    } else next();
  } else {
    next();
  }
});
