<script setup lang="ts">
import AuthLogin from '../authForms/AuthLogin.vue';
</script>

<template>
  <div style="display: flex; justify-content: center; flex-direction: column; align-items: center; height: 100vh; background-color: aliceblue;">
    <v-card variant="outlined" style="max-width: 500px; box-shadow: 0 0 3px rgba(0, 0, 0, 0.1);">
      <v-card-text class="pa-9">
        <div class="text-center">
          <Logo />
          <h2 class="text-secondary text-h2 mt-4">AstrBot 仪表盘</h2>
          <h4 class="text-disabled text-h4 mt-3">登录以继续</h4>
        </div>
        <AuthLogin />
      </v-card-text>
    </v-card>
  </div>

</template>
<style lang="scss">
.loginBox {
  max-width: 475px;
  margin: 0 auto;
}
</style>
