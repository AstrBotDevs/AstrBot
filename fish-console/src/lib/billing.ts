export type FeedPlan = {
  id: string;
  yuan: number;
  name: string;
  blurb: string;
};

export type PaymentPublicConfig = {
  alipay_qr_url: string;
  pay_hint: string;
};

export type BillingPublicConfig = {
  min_yuan: number;
  rice_grams_per_yuan: number;
  feed_plans: FeedPlan[];
  payment?: PaymentPublicConfig;
};

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

/** Resolve static Alipay QR image (API env → Vite env → repo default). */
export function resolveAlipayQrUrl(fromApi?: string): string {
  const api = fromApi?.trim();
  if (api) return api;
  const env = import.meta.env.VITE_ALIPAY_QR_URL?.trim();
  if (env) return env;
  return "/收款码.jpg";
}

const TIER_DEFAULTS: { yuan: number; name: string; blurb: string }[] = [
  { yuan: 2, name: "唔饿啦", blurb: "先垫一口，我醒醒神" },
  { yuan: 5, name: "贴贴罐", blurb: "日常饭量，够吃好几天" },
  { yuan: 20, name: "饱饱桶", blurb: "吃饱了才有力气干活（真的）" },
];

function tierYuanEnv(tier: 1 | 2 | 3): string | undefined {
  const key = `VITE_FEED_PLAN_YUAN_${tier}` as keyof ImportMetaEnv;
  return import.meta.env[key]?.trim();
}

function tierNameEnv(tier: 1 | 2 | 3): string | undefined {
  const key = `VITE_FEED_PLAN_NAME_${tier}` as keyof ImportMetaEnv;
  return import.meta.env[key]?.trim();
}

function fallbackFeedPlans(): FeedPlan[] {
  return ([1, 2, 3] as const).map((tier) => {
    const d = TIER_DEFAULTS[tier - 1];
    const yuan = Number(tierYuanEnv(tier)) || d.yuan;
    const name = tierNameEnv(tier) || d.name;
    return {
      id: `feed-${tier}-${yuan}`,
      yuan,
      name,
      blurb: d.blurb,
    };
  });
}

const FALLBACK: BillingPublicConfig = {
  min_yuan: Number(import.meta.env.VITE_MIN_TOPUP_YUAN) || 1,
  rice_grams_per_yuan: 500,
  payment: {
    alipay_qr_url: resolveAlipayQrUrl(),
    pay_hint: "转账金额须与本次添饭一致，备注请原样填写下方备注码。",
  },
  feed_plans: fallbackFeedPlans(),
};

export async function fetchBillingPublicConfig(): Promise<BillingPublicConfig> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/billing/public-config`);
    if (!res.ok) return FALLBACK;
    return (await res.json()) as BillingPublicConfig;
  } catch {
    return FALLBACK;
  }
}
