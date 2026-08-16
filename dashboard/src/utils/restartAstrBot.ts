import { statsApi } from '@/api/v1';
import { getDesktopRuntimeInfo } from '@/utils/desktopRuntime';
import { stepUpHeaders } from '@/utils/stepUp';
import type { DashboardStepUpTarget } from '@/composables/useDashboardStepUp';

type WaitingForRestartRef = {
  check: (initialStartTime?: number | null) => void | Promise<void>;
  stop?: () => void;
};

async function triggerWaiting(
  waitingRef?: WaitingForRestartRef | null,
  initialStartTime?: number | null,
) {
  if (!waitingRef) return;
  await waitingRef.check(initialStartTime);
}

async function fetchCurrentStartTime(): Promise<number | null> {
  try {
    const response = await statsApi.startTime();
    const rawStartTime = response?.data?.data?.start_time;
    const numericStartTime = Number(rawStartTime);
    return Number.isFinite(numericStartTime) ? numericStartTime : null;
  } catch (_error) {
    return null;
  }
}

export async function restartAstrBot(
  waitingRef?: WaitingForRestartRef | null,
  requestStepUp?: (target: DashboardStepUpTarget) => Promise<string | null>,
): Promise<void> {
  const {
    bridge: desktopBridge,
    hasDesktopRestartCapability,
    isDesktopRuntime,
  } = await getDesktopRuntimeInfo();

  if (!requestStepUp) {
    throw new Error('Reauthentication is required to restart AstrBot.');
  }
  const stepUp = await requestStepUp({
    action: 'system.restart',
    resourceType: 'system',
    resourceId: 'restart',
  });
  if (!stepUp) return;

  if (desktopBridge && hasDesktopRestartCapability && isDesktopRuntime) {
    const authToken = localStorage.getItem('token');
    const initialStartTime = await fetchCurrentStartTime();
    try {
      const restartPromise = desktopBridge.restartBackend(authToken);
      await triggerWaiting(waitingRef, initialStartTime);
      const result = await restartPromise;
      if (!result.ok) {
        waitingRef?.stop?.();
        throw new Error(result.reason || 'Failed to restart backend.');
      }
    } catch (error) {
      waitingRef?.stop?.();
      throw error;
    }
    return;
  }

  await statsApi.restart({ headers: stepUpHeaders(stepUp) });
  await triggerWaiting(waitingRef);
}
