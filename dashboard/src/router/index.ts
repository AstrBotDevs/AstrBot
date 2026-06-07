import { createRouter, createWebHashHistory } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { useRouterLoadingStore } from "@/stores/routerLoading";
import AuthRoutes from "./AuthRoutes";
import ChatBoxRoutes from "./ChatBoxRoutes";
import MainRoutes from "./MainRoutes";

export const router = createRouter({
  history: createWebHashHistory(import.meta.env.BASE_URL),
  routes: [MainRoutes, AuthRoutes, ChatBoxRoutes],
});

interface AuthStore {
  username: string;
  returnUrl: string | null;
  login(
    username: string,
    password: string,
    code?: string,
    trustDeviceToken?: boolean,
  ): Promise<undefined | "totp_required">;
  logout(): void;
  has_token(): boolean;
}

router.beforeEach(async (to, from) => {
  if (from.name && from.path !== to.path) {
    const loadingStore = useRouterLoadingStore();
    loadingStore.start();
  }

  const publicPages = ["/auth/login", "/auth/setup"];

  const authRequired = !publicPages.includes(to.path);
  const auth: AuthStore = useAuthStore();

  // 如果用户已登录且试图访问登录页面，则重定向到首页
  if (to.path === "/auth/login" && auth.has_token()) {
    return auth.returnUrl || "/";
  }

  if (to.matched.some((record) => record.meta.requiresAuth)) {
    if (authRequired && !auth.has_token()) {
      auth.returnUrl = to.fullPath;
      return "/auth/login";
    }
  }

  return true;
});

router.afterEach(() => {
  const loadingStore = useRouterLoadingStore();
  loadingStore.finish();
});
