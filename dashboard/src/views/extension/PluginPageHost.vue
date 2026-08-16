<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue';
import { isAxiosError } from 'axios';
import { storeToRefs } from 'pinia';
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router';
import { useTheme } from 'vuetify';

import {
  PLUGIN_DASHBOARD_LIFECYCLE_EVENT,
  type PluginDashboardAction,
  type PluginDashboardCatalog,
  type PluginDashboardLifecycleDetail,
  type PluginDashboardPage,
  type PluginDashboardSession,
  pluginDashboardApi,
} from '@/api/v1';
import { useI18n, useModuleI18n } from '@/i18n/composables';
import { useCustomizerStore } from '@/stores/customizer';

import {
  PluginPageHostChannel,
  PLUGIN_PAGE_PROTOCOL_VERSION,
  type PluginPageContext,
  type PluginPageDisposeReason,
  type PluginPageRequest,
  createPluginPageConnectMessage,
  parsePluginPageReadyMessage,
} from './pluginPageProtocol';

const route = useRoute();
const router = useRouter();
const theme = useTheme();
const customizer = useCustomizerStore();
const { isDark } = storeToRefs(customizer);
const { locale } = useI18n();
const { tm } = useModuleI18n('features.extension');

const extensionId = computed(() => String(route.params.extensionId || ''));
const pageId = computed(() => String(route.params.pageId || ''));
const iframe = ref<HTMLIFrameElement | null>(null);
const catalog = ref<PluginDashboardCatalog | null>(null);
const page = ref<PluginDashboardPage | null>(null);
const session = ref<PluginDashboardSession | null>(null);
const iframeSource = ref('');
const loading = ref(true);
const errorMessage = ref('');
const connected = ref(false);

let channel: PluginPageHostChannel | null = null;
let loadCount = 0;
let handshakeComplete = false;
let disposed = false;
let expiryTimer: number | null = null;
let generationPollTimer: number | null = null;
let generationPollController: AbortController | null = null;

class HostRequestError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly retryable = false,
  ) {
    super(message);
    this.name = 'HostRequestError';
  }
}

const title = computed(() => page.value?.title || tm('pageHost.title'));
const actionsById = computed(
  () =>
    new Map(
      (catalog.value?.actions || []).map((action) => [action.id, action]),
    ),
);

function publicError(
  code: string,
  message: string,
  retryable = false,
): HostRequestError {
  return new HostRequestError(code, message, retryable);
}

function requestFailure(error: unknown): HostRequestError {
  if (!isAxiosError(error)) {
    return publicError('request_failed', 'Plugin request failed');
  }
  const status = error.response?.status;
  if (status === 401) {
    queueMicrotask(() => {
      disposeInstance('logout', tm('pageHost.sessionExpired'));
    });
    return publicError('session_expired', 'Dashboard session expired');
  }
  if (status === 409) {
    queueMicrotask(() => {
      disposeInstance('plugin_changed', tm('pageHost.pluginChanged'));
    });
    return publicError('plugin_changed', 'Plugin Page changed');
  }
  if (status === 503) {
    queueMicrotask(() => {
      disposeInstance('plugin_changed', tm('pageHost.pluginUnavailable'));
    });
    return publicError('plugin_unavailable', 'Plugin Page unavailable', true);
  }
  if (status === 429)
    return publicError('rate_limited', 'Too many requests', true);
  if (status === 413)
    return publicError('request_too_large', 'Plugin request is too large');
  if (status === 422)
    return publicError('invalid_request', 'Plugin request is invalid');
  if (status === 403)
    return publicError('forbidden', 'Plugin request is forbidden');
  if (status === 404)
    return publicError('not_found', 'Plugin Action was not found');
  if (status === 504)
    return publicError('timeout', 'Plugin request timed out', true);
  return publicError('request_failed', 'Plugin request failed');
}

function currentContext(): PluginPageContext {
  const currentCatalog = catalog.value;
  const currentPage = page.value;
  const currentSession = session.value;
  if (!currentCatalog || !currentPage || !currentSession) {
    throw new Error('Plugin Page is not initialized');
  }
  const colors = theme.global.current.value.colors;
  const pageActions = new Set(currentPage.actions);
  const availableActions = currentCatalog.actions.filter((action) =>
    pageActions.has(action.id),
  );
  return {
    protocol_version: 1,
    extension_id: currentCatalog.extension_id,
    plugin_name: currentCatalog.plugin_name,
    page_id: currentPage.id,
    instance_id: currentSession.instance_id,
    plugin_generation: currentCatalog.plugin_generation,
    expires_at: currentSession.expires_at,
    locale: locale.value,
    theme: {
      mode: isDark.value ? 'dark' : 'light',
      is_dark: isDark.value,
      primary: String(colors.primary),
      secondary: String(colors.secondary),
    },
    capabilities: {
      actions: availableActions.map((action) => action.id),
      upload: availableActions.some((action) => action.kind === 'upload'),
      file: availableActions.some((action) => action.kind === 'file'),
    },
  };
}

function requireAction(request: PluginPageRequest): PluginDashboardAction {
  const currentPage = page.value;
  const action = actionsById.value.get(request.action_id);
  if (!currentPage?.actions.includes(request.action_id) || !action) {
    throw publicError('unknown_action', 'Plugin Action is not available');
  }
  if (action.kind !== request.action_kind) {
    throw publicError(
      'action_kind_mismatch',
      'Plugin Action kind does not match',
    );
  }
  return action;
}

function validateUpload(action: PluginDashboardAction, file: File): void {
  const filenameBytes = new TextEncoder().encode(file.name).length;
  const maxBytes = Math.min(
    action.max_file_bytes ?? 16 * 1024 * 1024,
    16 * 1024 * 1024,
  );
  if (
    !file.name ||
    filenameBytes > 255 ||
    file.size <= 0 ||
    file.size > maxBytes
  ) {
    throw publicError('invalid_upload', 'Plugin upload was rejected');
  }
  if (
    action.allowed_content_types?.length &&
    !action.allowed_content_types.includes(file.type)
  ) {
    throw publicError('invalid_upload_type', 'Plugin upload type was rejected');
  }
  if (action.allowed_extensions?.length) {
    const dot = file.name.lastIndexOf('.');
    const extension = dot < 0 ? '' : file.name.slice(dot).toLowerCase();
    const allowed = action.allowed_extensions.map((item) =>
      item.startsWith('.') ? item.toLowerCase() : `.${item.toLowerCase()}`,
    );
    if (!allowed.includes(extension)) {
      throw publicError(
        'invalid_upload_extension',
        'Plugin upload extension was rejected',
      );
    }
  }
}

function validateTicketUrl(ticketUrl: string): string {
  const parsed = new URL(ticketUrl, window.location.origin);
  if (
    parsed.origin !== window.location.origin ||
    !parsed.pathname.startsWith('/api/plugin-files/v1/') ||
    parsed.search ||
    parsed.hash
  ) {
    throw publicError('invalid_file_ticket', 'Plugin file ticket was rejected');
  }
  return parsed.href;
}

async function handleRequest(request: PluginPageRequest, signal: AbortSignal) {
  const currentCatalog = catalog.value;
  const currentSession = session.value;
  if (!currentCatalog || !currentSession || disposed) {
    throw publicError('disposed', 'Plugin Page is no longer available');
  }
  const action = requireAction(request);
  try {
    if (request.action_kind === 'json') {
      const response = await pluginDashboardApi.invoke(
        extensionId.value,
        action.id,
        currentSession.instance_id,
        currentCatalog.plugin_generation,
        request.payload,
        { signal },
      );
      return { data: response.data.data };
    }
    if (request.action_kind === 'upload') {
      validateUpload(action, request.file);
      const response = await pluginDashboardApi.upload(
        extensionId.value,
        action.id,
        currentSession.instance_id,
        currentCatalog.plugin_generation,
        request.file,
        request.fields,
        { signal },
      );
      return { data: response.data.data };
    }

    const disposition =
      request.file_operation === 'read' ? 'inline' : 'attachment';
    if (action.disposition !== disposition) {
      throw publicError(
        'file_intent_mismatch',
        'Plugin file intent does not match',
      );
    }
    const response = await pluginDashboardApi.createFileTicket(
      extensionId.value,
      action.id,
      currentSession.instance_id,
      currentCatalog.plugin_generation,
      disposition,
      request.payload,
      { signal },
    );
    const ticket = response.data.data;
    validateTicketUrl(ticket.ticket_url);
    if (ticket.disposition !== disposition) {
      throw publicError(
        'invalid_file_ticket',
        'Plugin file ticket was rejected',
      );
    }
    if (request.file_operation === 'download') {
      const anchor = document.createElement('a');
      anchor.href = validateTicketUrl(ticket.ticket_url);
      anchor.download = ticket.filename;
      anchor.hidden = true;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      return { data: undefined };
    }
    const bytes = await pluginDashboardApi.readInlineTicket(ticket, signal);
    return {
      data: {
        bytes,
        filename: ticket.filename,
        contentType: ticket.content_type,
        size: ticket.size,
        disposition: 'inline',
      },
      transfer: [bytes],
    };
  } catch (error) {
    if (error instanceof HostRequestError) {
      throw error;
    }
    throw requestFailure(error);
  }
}

function clearTimers(): void {
  if (expiryTimer !== null) window.clearTimeout(expiryTimer);
  if (generationPollTimer !== null) window.clearTimeout(generationPollTimer);
  generationPollController?.abort();
  expiryTimer = null;
  generationPollTimer = null;
  generationPollController = null;
}

function disposeInstance(
  reason: PluginPageDisposeReason,
  message = '',
  notifyPage = true,
): void {
  if (disposed) return;
  disposed = true;
  clearTimers();
  channel?.dispose(reason, notifyPage);
  channel = null;
  connected.value = false;
  iframeSource.value = '';
  if (message) errorMessage.value = message;
}

function failProtocol(): void {
  disposeInstance('protocol_error', tm('pageHost.protocolError'));
}

function onPageDispose(): void {
  disposeInstance('host_navigation', tm('pageHost.closed'), false);
}

function handleWindowMessage(event: MessageEvent<unknown>): void {
  const currentSession = session.value;
  const frameWindow = iframe.value?.contentWindow;
  if (!currentSession || !frameWindow || event.source !== frameWindow) return;
  const ready = parsePluginPageReadyMessage(
    event.data,
    currentSession.instance_id,
    currentSession.handshake_nonce,
  );
  if (!ready) return;
  if (handshakeComplete || event.ports.length !== 0) {
    failProtocol();
    return;
  }
  handshakeComplete = true;
  const messageChannel = new MessageChannel();
  channel = new PluginPageHostChannel(
    messageChannel.port1,
    currentSession.instance_id,
    currentSession.plugin_generation,
    handleRequest,
    onPageDispose,
    failProtocol,
  );
  try {
    frameWindow.postMessage(
      createPluginPageConnectMessage(
        currentSession.instance_id,
        currentSession.handshake_nonce,
      ),
      '*',
      [messageChannel.port2],
    );
    channel.sendContext(currentContext());
    connected.value = true;
  } catch {
    failProtocol();
  }
}

function handleIframeLoad(): void {
  loadCount += 1;
  if (loadCount > 1) {
    disposeInstance('protocol_error', tm('pageHost.navigationBlocked'));
  }
}

function scheduleExpiry(): void {
  const expiresAt = Date.parse(session.value?.expires_at || '');
  const remaining = expiresAt - Date.now();
  if (!Number.isFinite(remaining) || remaining <= 0) {
    disposeInstance('expired', tm('pageHost.sessionExpired'));
    return;
  }
  expiryTimer = window.setTimeout(
    () => {
      disposeInstance('expired', tm('pageHost.sessionExpired'));
    },
    Math.min(remaining, 2_147_000_000),
  );
}

function scheduleGenerationPoll(): void {
  if (disposed) return;
  const jitterMs = 27_000 + Math.floor(Math.random() * 6_001);
  generationPollTimer = window.setTimeout(async () => {
    if (disposed) return;
    if (document.visibilityState !== 'visible') {
      scheduleGenerationPoll();
      return;
    }
    generationPollController = new AbortController();
    try {
      const response = await pluginDashboardApi.catalog(extensionId.value, {
        signal: generationPollController.signal,
      });
      if (
        response.data.data.plugin_generation !==
        catalog.value?.plugin_generation
      ) {
        disposeInstance('plugin_changed', tm('pageHost.pluginChanged'));
        return;
      }
    } catch (error) {
      if (!generationPollController.signal.aborted) requestFailure(error);
    } finally {
      generationPollController = null;
    }
    scheduleGenerationPoll();
  }, jitterMs);
}

function handleLifecycleEvent(event: Event): void {
  const detail = (event as CustomEvent<PluginDashboardLifecycleDetail>).detail;
  if (detail.reason === 'logout') {
    disposeInstance('logout', tm('pageHost.sessionExpired'));
    return;
  }
  if (
    !detail.plugin_name ||
    detail.plugin_name === catalog.value?.plugin_name
  ) {
    disposeInstance('plugin_changed', tm('pageHost.pluginChanged'));
  }
}

async function initialize(): Promise<void> {
  loading.value = true;
  errorMessage.value = '';
  disposed = false;
  try {
    const catalogResponse = await pluginDashboardApi.catalog(extensionId.value);
    const loadedCatalog = catalogResponse.data.data;
    if (loadedCatalog.protocol_version !== PLUGIN_PAGE_PROTOCOL_VERSION) {
      throw new Error('Plugin UI protocol mismatch');
    }
    const loadedPage = loadedCatalog.pages.find(
      (candidate) => candidate.id === pageId.value,
    );
    if (!loadedPage) {
      errorMessage.value = tm('messages.pluginPageNotFound');
      return;
    }
    catalog.value = loadedCatalog;
    page.value = loadedPage;
    const sessionResponse = await pluginDashboardApi.createSession(
      extensionId.value,
      pageId.value,
      loadedCatalog.plugin_generation,
    );
    session.value = sessionResponse.data.data;
    if (
      session.value.protocol_version !== PLUGIN_PAGE_PROTOCOL_VERSION ||
      session.value.plugin_generation !== loadedCatalog.plugin_generation
    ) {
      throw new Error('Plugin UI protocol mismatch');
    }
    const shell = new URL(session.value.iframe_url, window.location.origin);
    if (
      shell.origin !== window.location.origin ||
      !shell.pathname.startsWith('/api/plugin-pages/v1/sessions/') ||
      shell.search ||
      shell.hash
    ) {
      throw new Error('Invalid Plugin Page session URL');
    }
    shell.hash = new URLSearchParams({
      instance: session.value.instance_id,
      channel: session.value.handshake_nonce,
    }).toString();
    window.addEventListener('message', handleWindowMessage);
    window.addEventListener(
      PLUGIN_DASHBOARD_LIFECYCLE_EVENT,
      handleLifecycleEvent,
    );
    iframeSource.value = shell.href;
    scheduleExpiry();
    scheduleGenerationPoll();
    await nextTick();
  } catch (error) {
    errorMessage.value = isAxiosError(error)
      ? tm('messages.pluginPageLoadFailed')
      : tm('pageHost.protocolError');
  } finally {
    loading.value = false;
  }
}

watch(
  [
    locale,
    isDark,
    () => theme.global.current.value.colors.primary,
    () => theme.global.current.value.colors.secondary,
  ],
  () => {
    if (channel && !disposed) channel.sendContext(currentContext());
  },
);

function cleanup(reason: PluginPageDisposeReason): void {
  window.removeEventListener('message', handleWindowMessage);
  window.removeEventListener(
    PLUGIN_DASHBOARD_LIFECYCLE_EVENT,
    handleLifecycleEvent,
  );
  disposeInstance(reason);
}

onBeforeRouteLeave(() => {
  cleanup('host_navigation');
});
onBeforeUnmount(() => {
  cleanup('host_navigation');
});
void initialize();
</script>

<template>
  <main class="plugin-page-host" data-testid="plugin-page-host">
    <header class="plugin-page-host__header">
      <v-btn
        variant="text"
        prepend-icon="mdi-arrow-left"
        data-testid="plugin-page-back"
        @click="router.push(`/extension/${catalog?.plugin_name || ''}`)"
      >
        {{ tm('buttons.back') }}
      </v-btn>
      <div>
        <h1>{{ title }}</h1>
        <p v-if="catalog">{{ catalog.plugin_name }}</p>
      </div>
      <v-chip v-if="connected" color="success" size="small" variant="tonal">
        {{ tm('pageHost.connected') }}
      </v-chip>
    </header>

    <div
      v-if="loading"
      class="plugin-page-host__state"
      data-testid="plugin-page-loading"
    >
      <v-progress-circular color="primary" indeterminate />
      <span>{{ tm('status.loading') }}</span>
    </div>
    <v-alert
      v-else-if="errorMessage"
      type="error"
      variant="tonal"
      data-testid="plugin-page-error"
    >
      {{ errorMessage }}
    </v-alert>
    <iframe
      v-else-if="iframeSource"
      ref="iframe"
      :src="iframeSource"
      :title="title"
      sandbox="allow-scripts"
      referrerpolicy="no-referrer"
      allow=""
      class="plugin-page-host__frame"
      data-testid="plugin-page-frame"
      @load="handleIframeLoad"
    />
  </main>
</template>

<style scoped>
.plugin-page-host {
  display: flex;
  min-height: calc(100vh - 96px);
  flex-direction: column;
  gap: 16px;
}

.plugin-page-host__header {
  display: flex;
  align-items: center;
  gap: 16px;
}

.plugin-page-host__header h1,
.plugin-page-host__header p {
  margin: 0;
}

.plugin-page-host__header p {
  color: rgb(var(--v-theme-on-surface-variant));
  font-size: 0.875rem;
}

.plugin-page-host__header .v-chip {
  margin-left: auto;
}

.plugin-page-host__state {
  display: flex;
  min-height: 320px;
  align-items: center;
  justify-content: center;
  gap: 12px;
}

.plugin-page-host__frame {
  width: 100%;
  min-height: 720px;
  flex: 1;
  border: 1px solid rgb(var(--v-theme-border));
  border-radius: 12px;
  background: rgb(var(--v-theme-surface));
}
</style>
