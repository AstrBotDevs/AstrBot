export const siteConfig = {
  brandName: import.meta.env.VITE_BRAND_NAME || "大肥鱼",
  docsUrl: import.meta.env.VITE_DOCS_URL?.trim() || "",
  supportEmail: import.meta.env.VITE_SUPPORT_EMAIL || "support@example.com",
  consoleVersion: "v0.1.0",
  businessHours: {
    title: "营业时间",
    hours: "早上 9 点 – 晚上 11 点",
    hint: "非 24 小时 · 工作时间偶尔摸鱼",
    quotaNote: "关店不影响你碗里的白饭，额度一直留着。",
  },
};
