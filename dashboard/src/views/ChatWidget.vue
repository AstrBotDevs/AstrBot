<script setup lang="ts">
import {
  onBeforeMount,
  ref,
} from "vue";
import {useRoute} from 'vue-router';
import standaloneChat from '@/components/chat/StandaloneChat.vue';
import {useCustomizerStore} from '@/stores/customizer';

const customizer = useCustomizerStore();
const route = useRoute();

const api_package = ref({} as Record<string, string>);
let api_decode_data = ref({} as Record<string, any>);
const attachmentEnabled = ref(true); // 是否明确开启文件功能
const apiStatusError = ref(false);
const apiErrorMsg = ref("");

onBeforeMount(() => {
  try {
    api_package.value = {
      appid: route.query?.appid as string ?? '',
      data: route.query?.data as string ?? '',
      noise: route.query?.noise as string ?? '',
      expiry_date: route.query?.expiry_date as string ?? '',
      signature: route.query?.signature as string ?? '',
    };
    api_decode_data.value = JSON.parse(
      new TextDecoder().decode(
        Uint8Array.from(
          atob(api_package.value.data as string),
          c => c.charCodeAt(0)
        )
      )
    );
    if (!api_decode_data.value?.session_id) throw new Error('args `session_id` is miss')
    if (!api_decode_data.value?.username) throw new Error('args `username` is miss')
    if (!api_decode_data.value?.config_id) throw new Error('args `config_id` is miss')
    if (!api_decode_data.value?.selected_provider) throw new Error('args `selected_provider` is miss')
    attachmentEnabled.value = api_decode_data.value?.file_upload === true;
  } catch (err) {
    apiErrorMsg.value = err instanceof Error ? err.message : String(err);
    apiStatusError.value = true;
    console.error(err);
  }
});

</script>

<style scoped>
.msg-box {
  height: 100%;
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
</style>

<template>
  <v-app :theme="customizer.uiTheme" style="height: 100%; width: 100%;">
    <div v-if="apiStatusError" class="api-error">{{ apiErrorMsg }}</div>
    <div v-else class="msg-box">
      <div style="width: 100%; height: 100%;">
        <standalone-chat
          :config-id="api_decode_data.config_id"
          :widget-model="true"
          :api-package="api_package"
          :api-package-data="api_decode_data"
          :attachment-enabled="attachmentEnabled"
        />
      </div>
    </div>
  </v-app>
</template>
