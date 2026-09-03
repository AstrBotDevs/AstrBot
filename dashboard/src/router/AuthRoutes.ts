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
    }
  ]
};

export default AuthRoutes;
