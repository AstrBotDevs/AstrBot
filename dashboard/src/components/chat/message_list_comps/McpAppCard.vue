<template>
  <div class="mcp-app-card">
    <v-btn v-if="!opened" variant="tonal" size="small" :loading="loading" :disabled="disabled" @click="openApp">
      {{ tm('mcpApp.open') }}
    </v-btn>
    <template v-else>
      <div class="d-flex justify-space-between align-center mb-2">
        <span>{{ tm('mcpApp.title') }}</span>
        <v-btn variant="text" size="small" @click="closeApp">{{ tm('mcpApp.close') }}</v-btn>
      </div>
      <iframe ref="frame" :title="tm('mcpApp.title')" sandbox="allow-scripts" referrerpolicy="no-referrer"
        :style="{ height: `${height}px` }" />
      <div v-if="proposal" class="mt-2">
        <p class="mb-2">{{ tm('mcpApp.review') }}</p>
        <pre class="mcp-app-proposal">{{ proposal }}</pre>
        <v-btn variant="tonal" :disabled="disabled" @click="accept">{{ tm('mcpApp.use') }}</v-btn>
        <v-btn variant="text" @click="decline">{{ tm('mcpApp.decline') }}</v-btn>
      </div>
    </template>
    <p v-if="error" role="alert">{{ error }}</p>
  </div>
</template>

<script setup>
import { nextTick, onBeforeUnmount, ref } from 'vue';
import { apiV1Client } from '@/api/http';
import { useModuleI18n } from '@/i18n/composables';
import { appDocument, createAppHost } from '@/utils/mcpAppHost.mjs';

const props = defineProps({ sessionId: String, messageId: [String, Number], toolCall: Object, disabled: Boolean, isDark: Boolean });
const emit = defineEmits(['draft']);
const { tm } = useModuleI18n('features/chat');
const frame = ref(null);
const opened = ref(false);
const loading = ref(false);
const error = ref('');
const proposal = ref('');
const height = ref(320);
let host;
let disposed = false;

async function openApp() {
  loading.value = true;
  error.value = '';
  try {
    const path = [props.sessionId, props.messageId, props.toolCall.id].map(v => encodeURIComponent(String(v)));
    const response = await apiV1Client.get(`/chat/sessions/${path[0]}/messages/${path[1]}/mcp-app/${path[2]}`);
    if (response.data.status !== 'ok') throw new Error('Resource unavailable');
    if (disposed) return;
    const data = response.data.data;
    opened.value = true;
    await nextTick();
    if (disposed || !frame.value) return;
    host = createAppHost({
      source: () => frame.value?.contentWindow,
      send: data => frame.value?.contentWindow?.postMessage(data, '*'),
      arguments: data.arguments,
      result: data.result,
      theme: props.isDark ? 'dark' : 'light',
      propose: text => { proposal.value = text; },
      resize: value => { height.value = value; },
    });
    window.addEventListener('message', host.receive);
    frame.value.srcdoc = appDocument(data.html);
  } catch {
    error.value = tm('mcpApp.error');
    closeApp();
  } finally {
    loading.value = false;
  }
}

function accept() {
  emit('draft', proposal.value);
  host?.settle(true);
  proposal.value = '';
}
function decline() {
  host?.settle(false);
  proposal.value = '';
}
function closeApp() {
  decline();
  if (host) window.removeEventListener('message', host.receive);
  host = undefined;
  opened.value = false;
}
onBeforeUnmount(() => { disposed = true; closeApp(); });
</script>

<style scoped>
.mcp-app-card { margin: 10px 0; }
iframe { width: 100%; border: 1px solid rgba(var(--v-theme-on-surface), .15); border-radius: 8px; background: white; }
.mcp-app-proposal { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 200px; overflow: auto; margin-bottom: 8px; }
</style>
