<script setup lang="ts">
import {ref, useCssModule} from 'vue';
import { useAuthStore } from '@/stores/auth';
import { Form } from 'vee-validate';
import md5 from 'js-md5';
import {useCustomizerStore} from "@/stores/customizer";

const valid = ref(false);
const show1 = ref(false);
const password = ref('');
const username = ref('');
const loading = ref(false);

/* eslint-disable @typescript-eslint/no-explicit-any */
async function validate(values: any, { setErrors }: any) {
  loading.value = true;
  
  // md5加密
  let password_ = password.value;
  if (password.value != '') {
    // @ts-ignore
    password_ = md5(password.value);
  }

  const authStore = useAuthStore();
  // @ts-ignore
  authStore.returnUrl = new URLSearchParams(window.location.search).get('redirect');
  return authStore.login(username.value, password_).then((res) => {
    console.log(res);
    loading.value = false;
  }).catch((err) => {
    setErrors({ apiError: err });
    loading.value = false;
  });
}

</script>

<template>
  <Form @submit="validate" class="mt-4 login-form" v-slot="{ errors, isSubmitting }">
    <v-text-field 
      v-model="username" 
      label="用户名" 
      class="mb-6 input-field" 
      required 
      density="comfortable"
      hide-details="auto" 
      variant="outlined"
      :style="{color: useCustomizerStore().uiTheme === 'PurpleTheme' ? '#000000dd' : '#ffffff'}"
      prepend-inner-icon="mdi-account"
      :disabled="loading"
    ></v-text-field>
    
    <v-text-field 
      v-model="password" 
      label="密码" 
      required 
      density="comfortable" 
      variant="outlined"
      :style="{color: useCustomizerStore().uiTheme === 'PurpleTheme' ? '#000000dd' : '#ffffff'}"
      hide-details="auto" 
      :append-icon="show1 ? 'mdi-eye' : 'mdi-eye-off'"
      :type="show1 ? 'text' : 'password'" 
      @click:append="show1 = !show1" 
      class="pwd-input"
      prepend-inner-icon="mdi-lock"
      :disabled="loading"
    ></v-text-field>
    
    <v-btn 
      color="secondary" 
      :loading="isSubmitting || loading" 
      block 
      class="login-btn mt-8" 
      variant="flat" 
      size="large" 
      :disabled="valid"
      type="submit"
      elevation="2"

    >
      <span class="login-btn-text">登录</span>
    </v-btn>
    
    <div v-if="errors.apiError" class="mt-4 error-container">
      <v-alert 
        color="error" 
        variant="tonal" 
        density="comfortable"
        icon="mdi-alert-circle"
        border="start"
      >
        {{ errors.apiError }}
      </v-alert>
    </div>
  </Form>
</template>

<style lang="scss">
.login-form {
  .v-text-field .v-field--active input {
    font-weight: 500;
  }

  .input-field, .pwd-input {
    .v-field__field {
      padding-top: 5px;
      padding-bottom: 5px;
    }
    
    .v-field__outline {
      opacity: 0.7;
    }
    
    &:hover .v-field__outline {
      opacity: 0.9;
    }
    
    .v-field--focused .v-field__outline {
      opacity: 1;
    }
    
    .v-field__prepend-inner {
      padding-right: 8px;
      opacity: 0.7;
    }
  }

  .pwd-input {
    position: relative;

    .v-input__append {
      position: absolute;
      right: 10px;
      top: 50%;
      transform: translateY(-50%);
      opacity: 0.7;
      
      &:hover {
        opacity: 1;
      }
    }
  }
  
  .login-btn {
    margin-top: 12px;
    height: 48px;
    transition: all 0.3s ease;
    letter-spacing: 0.5px;
    border-radius: 8px !important;
    
    &:hover {
      transform: translateY(-2px);
      box-shadow: 0 5px 15px rgba(94, 53, 177, 0.2) !important;
    }
    
    .login-btn-text {
      font-size: 1.05rem;
      font-weight: 500;
    }
  }
  
  .hint-text {
    color: var(--v-theme-secondaryText);
    padding-left: 5px;
  }
  
  .error-container {
    .v-alert {
      border-left-width: 4px !important;
    }
  }
}

.custom-divider {
  border-color: rgba(0, 0, 0, 0.08) !important;
}
</style>
