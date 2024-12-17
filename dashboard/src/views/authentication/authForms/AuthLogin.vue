<script setup lang="ts">
import { ref } from 'vue';
import { useAuthStore } from '@/stores/auth';
import { Form } from 'vee-validate';
import md5 from 'js-md5';

const valid = ref(false);
const show1 = ref(false);
const password = ref('');
const username = ref('');

/* eslint-disable @typescript-eslint/no-explicit-any */
async function validate(values: any, { setErrors }: any) {
  // md5加密
  let password_ = password.value;
  if (password.value != '') {
    // @ts-ignore
    password_ = md5(password.value);
  }

  const authStore = useAuthStore();
  return authStore.login(username.value, password_).then((res) => {
    console.log(res);
  }).catch((err) => {
    setErrors({ apiError: err });
  });
}

</script>

<template>
  <Form @submit="validate" class="mt-7 loginForm" v-slot="{ errors, isSubmitting }">
    <v-text-field v-model="username" label="用户名" class="mt-4 mb-8" required density="comfortable"
      hide-details="auto" variant="outlined" color="primary"></v-text-field>
    <v-text-field v-model="password" label="密码" required density="comfortable" variant="outlined"
      color="primary" hide-details="auto" :append-icon="show1 ? 'mdi-eye' : 'mdi-eye-off'"
      :type="show1 ? 'text' : 'password'" @click:append="show1 = !show1" class="pwdInput"></v-text-field>

    <small>默认用户名和密码为 astrbot。</small>
    <v-btn color="secondary" :loading="isSubmitting" block class="mt-8" variant="flat" size="large" :disabled="valid"
      type="submit">
      登录</v-btn>
    <div v-if="errors.apiError" class="mt-2">
      <v-alert color="error">{{ errors.apiError }}</v-alert>
    </div>
  </Form>

</template>

<style lang="scss">
.custom-devider {
  border-color: rgba(0, 0, 0, 0.08) !important;
}

.googleBtn {
  border-color: rgba(0, 0, 0, 0.08);
  margin: 30px 0 20px 0;
}

.outlinedInput .v-field {
  border: 1px solid rgba(0, 0, 0, 0.08);
  box-shadow: none;
}

.orbtn {
  padding: 2px 40px;
  border-color: rgba(0, 0, 0, 0.08);
  margin: 20px 15px;
}

.pwdInput {
  position: relative;

  .v-input__append {
    position: absolute;
    right: 10px;
    top: 50%;
    transform: translateY(-50%);
  }
}

.loginForm {
  .v-text-field .v-field--active input {
    font-weight: 500;
  }
}
</style>
