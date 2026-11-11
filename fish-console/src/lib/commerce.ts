import { getAccessToken } from "./token";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

function authHeaders(): HeadersInit {
  const token = getAccessToken();
  if (!token) throw new Error("Not authenticated");
  return {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };
}

async function parseError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
  } catch {
    // ignore
  }
  return res.statusText || "请求失败";
}

export type WalletMe = {
  balance_yuan: string | number;
  balance_rice_g: number;
  arrears_yuan: string | number;
  arrears_rice_g: number;
  status: string;
  can_bind: boolean;
};

export type Order = {
  id: string;
  amount_yuan: string | number;
  status: string;
  pay_channel: string;
  memo_code: string;
  plan_id: string | null;
  created_at: string;
};

export type AdminOrder = Order & {
  user_email: string;
  credit_yuan: string | number;
};

export type BindChannel = "qq" | "weixin";

export type Binding = {
  id: string;
  channel: BindChannel | string;
  qq_appid: string | null;
  adapter_id: string;
  umo_prefix: string;
  bind_status: string;
};

export type BindMeta = {
  qq_egress_ip: string;
  astrbot_ready: boolean;
  channels: BindChannel[];
};

export type QrStart = {
  session_id: string;
  channel: BindChannel | string;
  qrcode: string;
  interval: number;
  expires_in: number;
};

export type QrPoll = {
  status: string;
  message: string | null;
  binding: Binding | null;
};

export type UsageSummary = {
  days: number;
  rows: { date: string; model: string; rice_g: number; calls: number }[];
  total_rice_g: number;
  bound: boolean;
};

export type Profile = {
  email: string;
  paid: boolean;
  wallet: WalletMe;
  binding: Binding | null;
};

export type Ticket = {
  id: string;
  subject: string;
  body: string;
  status: string;
  created_at: string;
};

export async function fetchWalletMe(): Promise<WalletMe> {
  const res = await fetch(`${API_BASE}/api/v1/wallet/me`, { headers: authHeaders() });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function createOrder(amount_yuan: number, plan_id?: string): Promise<Order> {
  const res = await fetch(`${API_BASE}/api/v1/orders`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ amount_yuan, plan_id: plan_id ?? null }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function markOrderPaid(orderId: string): Promise<Order> {
  const res = await fetch(`${API_BASE}/api/v1/orders/${orderId}/mark-paid`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function fetchOrders(): Promise<Order[]> {
  const res = await fetch(`${API_BASE}/api/v1/orders/me`, { headers: authHeaders() });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function fetchBinding(): Promise<Binding | null> {
  const res = await fetch(`${API_BASE}/api/v1/bot/binding`, { headers: authHeaders() });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(await parseError(res));
  const text = await res.text();
  return text ? JSON.parse(text) : null;
}

export async function fetchBindMeta(): Promise<BindMeta> {
  const res = await fetch(`${API_BASE}/api/v1/bot/bind/meta`, { headers: authHeaders() });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function startBindQr(channel: BindChannel): Promise<QrStart> {
  const res = await fetch(`${API_BASE}/api/v1/bot/bind/qr/start`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ channel }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function pollBindQr(session_id: string): Promise<QrPoll> {
  const res = await fetch(`${API_BASE}/api/v1/bot/bind/qr/poll`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ session_id }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function manualBind(payload: {
  qq_appid: string;
  app_secret: string;
}): Promise<Binding> {
  const res = await fetch(`${API_BASE}/api/v1/bot/bind/manual`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function fetchUsage(days = 7): Promise<UsageSummary> {
  const res = await fetch(`${API_BASE}/api/v1/usage/me?days=${days}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function fetchProfile(): Promise<Profile> {
  const res = await fetch(`${API_BASE}/api/v1/profile/me`, { headers: authHeaders() });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function fetchTickets(): Promise<Ticket[]> {
  const res = await fetch(`${API_BASE}/api/v1/tickets/me`, { headers: authHeaders() });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function fetchAdminOrders(status?: string): Promise<AdminOrder[]> {
  const q = status ? `?status=${encodeURIComponent(status)}` : "";
  const res = await fetch(`${API_BASE}/api/v1/admin/orders${q}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function adminConfirmOrder(orderId: string): Promise<Order> {
  const res = await fetch(`${API_BASE}/api/v1/admin/orders/${orderId}/confirm`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function createTicket(subject: string, body: string): Promise<Ticket> {
  const res = await fetch(`${API_BASE}/api/v1/tickets`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ subject, body }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}
