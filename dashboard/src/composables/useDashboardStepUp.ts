import { onBeforeUnmount, ref } from 'vue';
import { authorizationApi } from '@/api/v1/authorization';
import { resolveErrorMessage } from '@/utils/errorUtils';

export interface DashboardStepUpTarget {
  action: string;
  resourceType: string;
  resourceId: string;
  configId?: string;
}

interface StepUpCredentials {
  password?: string;
  code?: string;
}

interface StepUpErrorLike {
  response?: {
    data?: unknown;
  };
}

/** Manage one exact, short-lived Dashboard step-up credential request. */
export function useDashboardStepUp() {
  const dialogOpen = ref(false);
  const loading = ref(false);
  const errorMessage = ref('');
  const target = ref<DashboardStepUpTarget | null>(null);
  const webChatExpiresAt = ref<number | null>(null);

  let resolvePending: ((token: string | null) => void) | null = null;
  let resolveWebChatPending:
    ((tokens: Record<string, string> | null) => void) | null = null;
  let webChatSessionId: string | null = null;
  let webChatExpiryTimer: number | undefined;

  function clearWebChatExpiry() {
    if (webChatExpiryTimer !== undefined) {
      window.clearTimeout(webChatExpiryTimer);
      webChatExpiryTimer = undefined;
    }
    webChatExpiresAt.value = null;
  }

  function finish(token: string | null) {
    const resolve = resolvePending;
    resolvePending = null;
    const resolveWebChat = resolveWebChatPending;
    resolveWebChatPending = null;
    webChatSessionId = null;
    clearWebChatExpiry();
    target.value = null;
    dialogOpen.value = false;
    loading.value = false;
    errorMessage.value = '';
    resolve?.(token);
    resolveWebChat?.(null);
  }

  function requestStepUp(
    nextTarget: DashboardStepUpTarget,
  ): Promise<string | null> {
    if (resolvePending || resolveWebChatPending) {
      return Promise.resolve(null);
    }

    target.value = nextTarget;
    errorMessage.value = '';
    dialogOpen.value = true;
    return new Promise((resolve) => {
      resolvePending = resolve;
    });
  }

  async function submitStepUp(credentials: StepUpCredentials) {
    const currentTarget = target.value;
    if (!currentTarget || loading.value) return;

    loading.value = true;
    errorMessage.value = '';
    try {
      if (webChatSessionId) {
        const response = await authorizationApi.webChatStepUp({
          session_id: webChatSessionId,
          password: credentials.password,
          code: credentials.code,
        });
        const tokens = response.data?.data?.tokens;
        if (!tokens || typeof tokens !== 'object') {
          throw new Error('Unable to issue a reauthentication credential.');
        }
        const normalized = Object.fromEntries(
          Object.entries(tokens).filter(
            ([action, token]) =>
              typeof action === 'string' && typeof token === 'string' && token,
          ),
        );
        if (!Object.keys(normalized).length) {
          throw new Error('Unable to issue a reauthentication credential.');
        }
        const expiresIn = Number(response.data?.data?.expires_in);
        const ttlSeconds =
          Number.isFinite(expiresIn) && expiresIn > 0 ? expiresIn : 300;
        clearWebChatExpiry();
        const expiresAt = Date.now() + ttlSeconds * 1000;
        webChatExpiresAt.value = expiresAt;
        webChatExpiryTimer = window.setTimeout(() => {
          if (webChatExpiresAt.value === expiresAt) {
            webChatExpiresAt.value = null;
            webChatExpiryTimer = undefined;
          }
        }, ttlSeconds * 1000);
        const resolve = resolveWebChatPending;
        resolveWebChatPending = null;
        webChatSessionId = null;
        target.value = null;
        dialogOpen.value = false;
        loading.value = false;
        errorMessage.value = '';
        resolve?.(normalized as Record<string, string>);
        return;
      }
      const response = await authorizationApi.stepUp({
        action: currentTarget.action,
        resource_type: currentTarget.resourceType,
        resource_id: currentTarget.resourceId,
        config_id: currentTarget.configId,
        password: credentials.password,
        code: credentials.code,
      });
      const token = response.data?.data?.token;
      if (typeof token !== 'string' || !token) {
        throw new Error('Unable to issue a reauthentication credential.');
      }
      finish(token);
    } catch (error: unknown) {
      errorMessage.value = resolveErrorMessage(
        error,
        'Unable to verify your identity for this operation.',
      );
      loading.value = false;
    }
  }

  function cancelStepUp() {
    finish(null);
  }

  function requestWebChatStepUp(
    sessionId: string,
  ): Promise<Record<string, string> | null> {
    if (resolvePending || resolveWebChatPending) return Promise.resolve(null);
    webChatSessionId = sessionId;
    target.value = {
      action: 'webchat.tool_run',
      resourceType: 'session',
      resourceId: sessionId,
    };
    errorMessage.value = '';
    dialogOpen.value = true;
    return new Promise((resolve) => {
      resolveWebChatPending = resolve;
    });
  }

  onBeforeUnmount(cancelStepUp);

  return {
    dialogOpen,
    loading,
    errorMessage,
    target,
    webChatExpiresAt,
    requestStepUp,
    requestWebChatStepUp,
    submitStepUp,
    cancelStepUp,
  };
}

/** Detect the structured response used by protected Dashboard mutations. */
export function isDashboardStepUpRequired(error: unknown): boolean {
  const response = (error as StepUpErrorLike | null | undefined)?.response;
  if (!response?.data || typeof response.data !== 'object') {
    return false;
  }
  const data = response.data as Record<string, unknown>;
  return (
    data.data !== null &&
    typeof data.data === 'object' &&
    (data.data as Record<string, unknown>).requires_step_up === true
  );
}
