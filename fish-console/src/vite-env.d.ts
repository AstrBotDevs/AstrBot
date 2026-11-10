/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_BRAND_NAME: string;
  readonly VITE_DOCS_URL?: string;
  readonly VITE_SUPPORT_EMAIL: string;
  readonly VITE_MIN_TOPUP_YUAN?: string;
  readonly VITE_FEED_PLAN_YUAN_1?: string;
  readonly VITE_FEED_PLAN_YUAN_2?: string;
  readonly VITE_FEED_PLAN_YUAN_3?: string;
  readonly VITE_FEED_PLAN_NAME_1?: string;
  readonly VITE_FEED_PLAN_NAME_2?: string;
  readonly VITE_FEED_PLAN_NAME_3?: string;
  readonly VITE_ALIPAY_QR_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
