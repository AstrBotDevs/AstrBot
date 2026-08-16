import {
  isDashboardStepUpRequired,
  type DashboardStepUpTarget,
} from '@/composables/useDashboardStepUp';

export type RequestDashboardStepUp = (
  target: DashboardStepUpTarget,
) => Promise<string | null>;

export async function runBotMutationWithStepUp<T>(
  operation: (stepUp?: string) => Promise<T>,
  resourceId: string,
  requestStepUp?: RequestDashboardStepUp,
): Promise<T | null> {
  try {
    return await operation();
  } catch (error: unknown) {
    if (!isDashboardStepUpRequired(error) || !requestStepUp) {
      throw error;
    }

    const stepUp = await requestStepUp({
      action: 'platform.manage',
      resourceType: 'bot',
      resourceId,
    });
    if (!stepUp) {
      return null;
    }
    return operation(stepUp);
  }
}
