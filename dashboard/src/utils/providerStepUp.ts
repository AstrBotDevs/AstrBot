import {
  isDashboardStepUpRequired,
  type DashboardStepUpTarget,
} from '@/composables/useDashboardStepUp';

export type RequestDashboardStepUp = (
  target: DashboardStepUpTarget,
) => Promise<string | null>;

export async function runProviderMutationWithStepUp<T>(
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
      action: 'provider.credentials.write',
      resourceType: 'provider',
      resourceId,
      configId: 'default',
    });
    if (!stepUp) {
      return null;
    }
    return operation(stepUp);
  }
}
