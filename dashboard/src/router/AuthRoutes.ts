import type { RouteLocationNormalized } from 'vue-router';

const AuthRoutes = {
  path: '/auth',
  component: () => import('@/layouts/blank/BlankLayout.vue'),
  meta: {
    requiresAuth: false
  },
  children: [
    {
      name: 'Login',
      path: '/auth/login',
      component: () => import('@/views/authentication/auth/LoginPage.vue')
    },
    {
      name: 'Setup',
      path: '/auth/setup',
      component: () => import('@/views/authentication/auth/SetupPage.vue')
    },
    {
      name: 'Onboarding',
      path: '/auth/onboarding',
      meta: { requiresAuth: true },
      redirect: (to: RouteLocationNormalized) => ({
        path: '/chat/onboarding',
        query: to.query
      })
    }
  ]
};

export default AuthRoutes;
