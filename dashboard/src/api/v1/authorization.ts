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

export type AuthorizationBindingRequest = {
  subject_id: string;
  role:
    | 'root'
    | 'operator'
    | 'instance_operator'
    | 'session_owner'
    | 'session_admin'
    | 'member';
  scope_type: 'global' | 'instance' | 'session' | 'resource';
  scope_id: string;
  config_id?: string | null;
  expires_at?: string | null;
};

export type AuthorizationStepUpRequest = {
  action: string;
  resource_type: string;
  resource_id: string;
  config_id?: string | null;
  password?: string;
  code?: string;
};

export type WebChatStepUpRequest = {
  session_id: string;
  password?: string;
  code?: string;
};

export type AuthorizationBatchRevokeRequest = {
  binding_ids: string[];
  password?: string;
  code?: string;
};

export const authorizationApi = {
  bindings: (): V1Response<AuthorizationBinding[]> =>
    httpClient.get('/api/v1/authorization/role-bindings'),
  audit: (): V1Response<Record<string, unknown>[]> =>
    httpClient.get('/api/v1/authorization/audit'),
  grant: (payload: AuthorizationBindingRequest, stepUp?: string) =>
    httpClient.post('/api/v1/authorization/role-bindings', payload, {
      headers: stepUp ? { 'X-AstrBot-Step-Up': stepUp } : undefined,
    }),
  revoke: (bindingId: string, stepUp?: string) =>
    httpClient.post(
      `/api/v1/authorization/role-bindings/${encodeURIComponent(bindingId)}/revoke`,
      undefined,
      { headers: stepUp ? { 'X-AstrBot-Step-Up': stepUp } : undefined },
    ),
  stepUp: (payload: AuthorizationStepUpRequest) =>
    httpClient.post('/api/v1/authorization/step-up', payload),
  webChatStepUp: (payload: WebChatStepUpRequest) =>
    httpClient.post('/api/v1/authorization/webchat-step-up', payload),
  issueBatchRevokeStepUp: (payload: AuthorizationBatchRevokeRequest) =>
    httpClient.post(
      '/api/v1/authorization/role-bindings/batch-revoke/step-up',
      payload,
    ),
  revokeBatch: (bindingIds: string[], stepUp: string) =>
    httpClient.post(
      '/api/v1/authorization/role-bindings/batch-revoke',
      { binding_ids: bindingIds },
      { headers: { 'X-AstrBot-Step-Up': stepUp } },
    ),
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
