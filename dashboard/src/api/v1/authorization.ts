import { httpClient } from './shared';
import type { V1Response } from './shared';

export type AuthorizationBinding = {
  binding_id: string;
  subject_id: string;
  role: string;
  scope_type: string;
  scope_id: string;
  config_id?: string | null;
  source: string;
  expires_at?: string | null;
};

export const authorizationApi = {
  bindings: (): V1Response<AuthorizationBinding[]> =>
    httpClient.get('/api/v1/authorization/role-bindings'),
  audit: (): V1Response<Record<string, unknown>[]> =>
    httpClient.get('/api/v1/authorization/audit'),
  grant: (payload: Record<string, unknown>) =>
    httpClient.post('/api/v1/authorization/role-bindings', payload),
  revoke: (bindingId: string, stepUp?: string) =>
    httpClient.post(
      `/api/v1/authorization/role-bindings/${encodeURIComponent(bindingId)}/revoke`,
      undefined,
      { headers: stepUp ? { 'X-AstrBot-Step-Up': stepUp } : undefined },
    ),
  stepUp: (payload: Record<string, unknown>) =>
    httpClient.post('/api/v1/authorization/step-up', payload),
  accounts: (): V1Response<Record<string, unknown>[]> =>
    httpClient.get('/api/v1/authorization/accounts'),
  createAccount: (payload: Record<string, unknown>, stepUp?: string) =>
    httpClient.post('/api/v1/authorization/accounts', payload, {
      headers: stepUp ? { 'X-AstrBot-Step-Up': stepUp } : undefined,
    }),
  updateAccount: (
    accountId: string,
    payload: Record<string, unknown>,
    stepUp?: string,
  ) =>
    httpClient.patch(
      `/api/v1/authorization/accounts/${encodeURIComponent(accountId)}`,
      payload,
      { headers: stepUp ? { 'X-AstrBot-Step-Up': stepUp } : undefined },
    ),
};
