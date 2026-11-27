<template>
  <v-dialog :model-value="modelValue" max-width="540" scrollable :persistent="loading"
    @update:model-value="emit('update:modelValue', $event)">
    <v-card>
      <v-card-title class="text-h3 pa-4 pb-0 pl-6">
        {{ field(server ? 'editTitle' : 'title') }}
      </v-card-title>
      <v-card-text class="px-6 pt-5">
        <v-form id="mcp-server-form" ref="form" @submit.prevent="submit('save')">
          <v-text-field v-model="name" :label="field('fields.name')" variant="outlined"
            :rules="[required('nameRequired')]" />
          <v-select v-model="transport" :label="field('fields.transport')" :items="transports"
            variant="outlined" />
          <template v-if="transport === 'stdio'">
            <v-text-field v-model="command" :label="field('fields.command')" placeholder="uvx" variant="outlined"
              :rules="[required('commandRequired')]" />
            <div v-if="args.length" class="text-body-2 mb-2">{{ field('fields.args') }}</div>
            <div v-for="(_, index) in args" :key="index" class="d-flex align-center ga-2 mb-2">
              <v-text-field v-model="args[index]" :label="field('fields.argument', { index: index + 1 })"
                variant="outlined" density="compact" hide-details />
              <v-btn icon="mdi-close" variant="text" size="small" :ripple="false"
                :aria-label="field('buttons.removeArgument')"
                @click="args.splice(index, 1)" />
            </div>
            <v-btn variant="text" color="primary" prepend-icon="mdi-plus" class="mb-3" :ripple="false"
              @click="args.push('')">
              {{ field('buttons.addArgument') }}
            </v-btn>
            <v-textarea v-model="env" :label="field('fields.env')" placeholder="KEY=value" variant="outlined"
              rows="2" auto-grow :rules="[keyValueRule]" :hint="field('tips.keyValue')" persistent-hint />
          </template>
          <template v-else>
            <v-text-field v-model="url" :label="field('fields.url')" placeholder="https://example.com/mcp"
              variant="outlined" :rules="[required('urlRequired'), urlRule]" />
            <v-select v-model="auth" :label="field('fields.authentication')" :items="authOptions" variant="outlined" />
            <v-text-field v-if="auth === 'bearer'" v-model="token" :label="field('fields.bearerToken')"
              type="password" autocomplete="off" variant="outlined" :rules="[required('tokenRequired')]" />
          </template>
          <button type="button" class="mcp-advanced-toggle"
            :aria-expanded="showAdvanced" aria-controls="mcp-advanced-settings" @click="showAdvanced = !showAdvanced">
            <span>{{ field('fields.advanced') }}</span>
            <v-icon :icon="showAdvanced ? 'mdi-chevron-up' : 'mdi-chevron-down'" size="16" aria-hidden="true" />
          </button>
          <div v-show="showAdvanced" id="mcp-advanced-settings" class="pt-3">
            <v-text-field v-if="transport === 'stdio'" v-model="cwd" :label="field('fields.cwd')" variant="outlined" />
            <v-textarea v-else v-model="headers" name="mcp-headers" :label="field('fields.headers')"
              placeholder="X-API-Key=value" variant="outlined" rows="2" auto-grow :rules="[keyValueRule]"
              :hint="field('tips.keyValue')" persistent-hint />
            <v-text-field v-model="timeout" name="mcp-timeout" :label="field('fields.timeout')" type="number"
              variant="outlined" :rules="[timeoutRule]" />
            <v-text-field v-if="transport !== 'stdio'" v-model="readTimeout" name="mcp-read-timeout"
              :label="field('fields.readTimeout')" type="number" variant="outlined" :rules="[timeoutRule]" />
            <v-btn v-if="!showImport" variant="text" size="small" class="px-0" :ripple="false"
              @click="showImport = true">
              {{ field('buttons.importJson') }}
            </v-btn>
            <template v-else>
              <v-textarea v-model="importText" :label="field('fields.config')" variant="outlined"
                rows="3" :error-messages="importError" />
              <v-btn variant="tonal" :ripple="false" @click="importConfig">{{ field('buttons.importJson') }}</v-btn>
            </template>
          </div>
        </v-form>
        <v-alert type="warning" variant="tonal" density="compact" class="mt-4">
          <span class="on-surface">{{ field('tips.connectionRisk') }}</span>
        </v-alert>
        <v-alert v-if="testMessage" :type="testMessage.type" variant="tonal" density="compact" class="mt-4"
          role="status">
          {{ testMessage.text }}
        </v-alert>
      </v-card-text>
      <v-card-actions class="px-6 pb-4 flex-wrap ga-2">
        <v-btn variant="text" :ripple="false" :disabled="loading" @click="submit('test')">
          {{ field('buttons.testConnection') }}
        </v-btn>
        <v-spacer />
        <v-btn variant="text" :ripple="false" :disabled="loading" @click="emit('update:modelValue', false)">
          {{ field('buttons.cancel') }}
        </v-btn>
        <v-btn type="submit" form="mcp-server-form" color="primary" variant="tonal" :ripple="false" :loading="loading">
          {{ field('buttons.save') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue';
import { useModuleI18n } from '@/i18n/composables';

const props = defineProps({
  modelValue: Boolean,
  server: { type: Object, default: null },
  loading: Boolean,
  testMessage: { type: Object, default: null }
});
const emit = defineEmits(['update:modelValue', 'save', 'test']);
const { tm } = useModuleI18n('features/tooluse');
const field = (key, params) => tm(`dialogs.addServer.${key}`, params);
const transports = [
  { title: 'HTTP / SSE', value: 'http' },
  { title: 'stdio', value: 'stdio' }
];
const authOptions = computed(() => [
  { title: field('fields.authNone'), value: 'none' },
  { title: field('fields.bearerToken'), value: 'bearer' }
]);

const form = ref();
const name = ref('');
const transport = ref('http');
const command = ref('');
const args = ref([]);
const env = ref('');
const cwd = ref('');
const url = ref('');
const auth = ref('none');
const token = ref('');
const headers = ref('');
const timeout = ref('');
const readTimeout = ref('');
const showAdvanced = ref(false);
const showImport = ref(false);
const importText = ref('');
const importError = ref('');
let extraConfig = {};
let configuredHttpTransport;

const required = key => value => !!value?.trim() || field(`fields.${key}`);
const keyValueRule = value => value.split(/\r?\n/).every(line => !line.trim() || line.indexOf('=') > 0
  && !!line.slice(0, line.indexOf('=')).trim()) || field('errors.keyValue');
const timeoutRule = value => value === '' || Number(value) > 0 || field('errors.timeout');
const urlRule = value => {
  try {
    return ['http:', 'https:'].includes(new URL(value).protocol) || field('errors.url');
  } catch {
    return field('errors.url');
  }
};
const keyValueText = values => Object.entries(values || {}).map(([key, value]) => `${key}=${value}`).join('\n');
const parseKeyValues = text => Object.fromEntries(text.split(/\r?\n/).filter(line => line.trim()).map(line => {
  const separator = line.indexOf('=');
  return [line.slice(0, separator).trim(), line.slice(separator + 1)];
}));

function loadConfig(config) {
  const { transport: protocol, type, command: executable, args: argumentsList, env: environment,
    cwd: directory, url: endpoint, headers: requestHeaders, timeout: requestTimeout,
    sse_read_timeout: eventTimeout, name: _name, active: _active, connected: _connected,
    tools: _tools, errlogs: _errlogs, oldName: _oldName, ...extra } = config;
  extraConfig = extra;
  transport.value = !endpoint && executable ? 'stdio' : 'http';
  const configuredProtocol = protocol || type;
  configuredHttpTransport = ['streamable_http', 'sse'].includes(configuredProtocol) ? configuredProtocol : undefined;
  command.value = executable || '';
  args.value = Array.isArray(argumentsList) ? [...argumentsList] : [];
  env.value = keyValueText(environment);
  cwd.value = directory || '';
  url.value = endpoint || '';
  const bearer = Object.entries(requestHeaders || {}).find(([key, value]) =>
    key.toLowerCase() === 'authorization' && /^Bearer\s+/i.test(value));
  auth.value = bearer ? 'bearer' : 'none';
  token.value = bearer ? bearer[1].replace(/^Bearer\s+/i, '') : '';
  headers.value = keyValueText(Object.fromEntries(Object.entries(requestHeaders || {}).filter(([key]) => key !== bearer?.[0])));
  timeout.value = requestTimeout == null ? '' : String(requestTimeout);
  readTimeout.value = eventTimeout == null ? '' : String(eventTimeout);
}

watch(() => props.modelValue, open => {
  if (!open) {
    token.value = '';
    importText.value = '';
    return;
  }
  name.value = props.server?.name || '';
  showAdvanced.value = false;
  showImport.value = false;
  importError.value = '';
  loadConfig(props.server || {});
});

function importConfig() {
  try {
    let config = JSON.parse(importText.value);
    let importedName = '';
    if (config?.mcpServers) {
      [[importedName, config] = []] = Object.entries(config.mcpServers);
    }
    if (!config || typeof config !== 'object' || Array.isArray(config)
      || !(typeof config.command === 'string' || typeof config.url === 'string')) {
      throw new Error(field('errors.configEmpty'));
    }
    if (!name.value) name.value = importedName;
    loadConfig(config);
    showImport.value = false;
    importText.value = '';
    importError.value = '';
  } catch (error) {
    importError.value = field('errors.jsonFormat', { error: error.message });
  }
}

async function submit(action) {
  if (props.loading) return;
  const { valid, errors } = await form.value.validate();
  if (!valid) {
    if (errors.some(({ id }) => ['mcp-headers', 'mcp-timeout', 'mcp-read-timeout'].includes(id))) {
      showAdvanced.value = true;
    }
    return;
  }
  const config = { ...extraConfig };
  if (timeout.value !== '') config.timeout = Number(timeout.value);
  if (transport.value === 'stdio') {
    config.command = command.value.trim();
    config.args = [...args.value];
    config.env = parseKeyValues(env.value);
    if (cwd.value) config.cwd = cwd.value;
  } else {
    config.url = url.value.trim();
    if (configuredHttpTransport) config.transport = configuredHttpTransport;
    config.headers = parseKeyValues(headers.value);
    if (auth.value === 'bearer') {
      for (const key of Object.keys(config.headers)) {
        if (key.toLowerCase() === 'authorization') delete config.headers[key];
      }
      config.headers.Authorization = `Bearer ${token.value.trim()}`;
    }
    if (readTimeout.value !== '') config.sse_read_timeout = Number(readTimeout.value);
  }
  emit(action, name.value.trim(), config);
}
</script>

<style scoped>
.mcp-advanced-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 32px;
  padding: 0;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  font-size: 0.875rem;
}

.mcp-advanced-toggle:hover,
.mcp-advanced-toggle:focus-visible {
  color: rgba(var(--v-theme-on-surface), var(--v-high-emphasis-opacity));
}
</style>
