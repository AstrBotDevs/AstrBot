import { getAccessToken } from "./token";

export type UserPublic = {
  id: string;
  email: string;
  paid: boolean;
  role: string;
};

export type AuthResponse = {
  access_token: string;
  token_type: string;
  user: UserPublic;
};

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

const ERROR_ZH: Record<string, string> = {
  "Incorrect email or password": "邮箱或通行证不对哦",
  "Email already registered": "这个邮箱已经有鱼片在用啦",
  "Admin only": "需要鱼咖管理员账号",
};

async function parseError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") {
      return ERROR_ZH[body.detail] ?? body.detail;
    }
    if (Array.isArray(body?.detail)) {
      return body.detail.map((item: { msg?: string }) => item.msg ?? "").join("; ");
    }
  } catch {
    // ignore
  }
  return res.statusText || "Request failed";
}

export async function apiRegister(
  email: string,
  password: string,
): Promise<AuthResponse> {
  const res = await fetch(`${API_BASE}/api/v1/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function apiLogin(email: string, password: string): Promise<AuthResponse> {
  const res = await fetch(`${API_BASE}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function apiMe(): Promise<UserPublic> {
  const token = getAccessToken();
  if (!token) throw new Error("Not authenticated");
  const res = await fetch(`${API_BASE}/api/v1/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}
