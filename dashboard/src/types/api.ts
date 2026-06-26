// API Key related types
export interface ApiKey {
  key_id: string;
  name: string;
  key_prefix: string;
  scopes: string[];
  is_revoked: boolean;
  is_expired: boolean;
  last_used_at: string | null;
  created_at: string;
  expires_at: string | null;
}

export type ApiKeyExpiresDays = 1 | 7 | 30 | 90 | "permanent";

export interface ApiKeyCreatePayload {
  name: string;
  scopes: string[];
  expires_in_days?: number;
}

export interface ApiKeyListResponse {
  status: "ok" | "error";
  data: ApiKey[];
  message?: string;
}

export interface ApiKeyCreateResponse {
  status: "ok" | "error";
  data?: ApiKey & { api_key: string }; // Include the full API key in the response
  message?: string;
}

export interface ApiKeyActionResponse {
  status: "ok" | "error";
  message?: string;
}
