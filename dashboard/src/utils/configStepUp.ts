import {
  isDashboardStepUpRequired,
  type DashboardStepUpTarget,
} from '@/composables/useDashboardStepUp';

export type RequestDashboardStepUp = (
  target: DashboardStepUpTarget,
) => Promise<string | null>;

export async function runConfigMutationWithStepUp<T>(
  operation: (stepUp?: string) => Promise<T>,
  configId: string,
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
      resourceType: 'instance',
      resourceId: configId,
      configId,
    });
    if (!stepUp) {
      return null;
    }
    return operation(stepUp);
  }
}
