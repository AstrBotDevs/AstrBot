import { authorizationApi } from '@/api/v1/authorization';

type StepUpTarget = {
  action: string;
  resourceType: string;
  resourceId: string;
  prompt?: string;
};

/** Request a one-time credential for one exact high-risk Dashboard action. */
export async function requestDashboardStepUp({
  action,
  resourceType,
  resourceId,
  prompt = 'Enter your Dashboard password to continue.',
}: StepUpTarget): Promise<string> {
  const password = window.prompt(prompt);
  if (!password) {
    throw new Error('Reauthentication cancelled.');
  }

  const response = await authorizationApi.stepUp({
    action,
    resource_type: resourceType,
    resource_id: resourceId,
    password,
  });
  const token = response.data?.data?.token;
  if (typeof token !== 'string' || !token) {
    throw new Error('Unable to issue a reauthentication credential.');
  }
  return token;
}

/** Build the header accepted by Dashboard high-risk endpoints. */
export function stepUpHeaders(token: string): Record<string, string> {
  return { 'X-AstrBot-Step-Up': token };
}
