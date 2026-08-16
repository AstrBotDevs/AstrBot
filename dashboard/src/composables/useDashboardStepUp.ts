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

  let resolvePending: ((token: string | null) => void) | null = null;

  function finish(token: string | null) {
    const resolve = resolvePending;
    resolvePending = null;
    target.value = null;
    dialogOpen.value = false;
    loading.value = false;
    errorMessage.value = '';
    resolve?.(token);
  }

  function requestStepUp(
    nextTarget: DashboardStepUpTarget,
  ): Promise<string | null> {
    if (resolvePending) {
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

  onBeforeUnmount(cancelStepUp);

  return {
    dialogOpen,
    loading,
    errorMessage,
    target,
    requestStepUp,
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
