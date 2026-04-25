import { createRouter, createWebHashHistory } from 'vue-router';
import MainRoutes from './MainRoutes';
import AuthRoutes from './AuthRoutes';
import ChatBoxRoutes from './ChatBoxRoutes';
import { useAuthStore } from '@/stores/auth';
import { useRouterLoadingStore } from '@/stores/routerLoading';

export const router = createRouter({
  history: createWebHashHistory(import.meta.env.BASE_URL),
  routes: [
    MainRoutes,
    AuthRoutes,
    ChatBoxRoutes
  ]
});

interface AuthStore {
  username: string;
  returnUrl: string | null;
  login(username: string, password: string): Promise<void>;
  logout(): void;
  has_token(): boolean;
  loadProfile(): Promise<any>;
  isChatUIScoped(): boolean;
  clearSession(): void;
}

router.beforeEach(async (to, from, next) => {
  if (from.name && from.path !== to.path) {
    const loadingStore = useRouterLoadingStore();
    loadingStore.start();
  }

  const publicPages = ['/auth/login'];
  const authRequired = !publicPages.includes(to.path);
  const auth: AuthStore = useAuthStore();

  // 如果用户已登录且试图访问登录页面，则重定向到首页
  if (to.path === '/auth/login' && auth.has_token()) {
    try {
      await auth.loadProfile();
      return next(auth.isChatUIScoped() ? '/chat' : '/welcome');
    } catch {
      auth.clearSession();
      return next('/auth/login');
    }
  }

  if (to.matched.some((record) => record.meta.requiresAuth)) {
    if (authRequired && !auth.has_token()) {
      auth.returnUrl = to.fullPath;
      return next('/auth/login');
    }
    try {
      await auth.loadProfile();
      if (auth.isChatUIScoped() && !(to.path === '/chat' || to.path.startsWith('/chat/'))) {
        return next('/chat');
      }
      next();
    } catch {
      auth.clearSession();
      return next('/auth/login');
    }
  } else {
    next();
  }
});

router.afterEach(() => {
  const loadingStore = useRouterLoadingStore();
  loadingStore.finish();
});
