import { docsHref } from '@/utils/docsHref';

const PLATFORM_ICON_URLS: Record<string, string> = {
  aiocqhttp: new URL(
    '@/assets/images/platform_logos/onebot.png',
    import.meta.url,
  ).href,
  napcat: new URL('@/assets/images/platform_logos/napcat.png', import.meta.url)
    .href,
  qq_official: new URL('@/assets/images/platform_logos/qq.png', import.meta.url)
    .href,
  qq_official_webhook: new URL(
    '@/assets/images/platform_logos/qq.png',
    import.meta.url,
  ).href,
  weixin_oc: new URL(
    '@/assets/images/platform_logos/wechat.png',
    import.meta.url,
  ).href,
  wecom: new URL('@/assets/images/platform_logos/wecom.png', import.meta.url)
    .href,
  wecom_ai_bot: new URL(
    '@/assets/images/platform_logos/wecom.png',
    import.meta.url,
  ).href,
  weixin_official_account: new URL(
    '@/assets/images/platform_logos/wechat.png',
    import.meta.url,
  ).href,
  lark: new URL('@/assets/images/platform_logos/lark.png', import.meta.url)
    .href,
  dingtalk: new URL(
    '@/assets/images/platform_logos/dingtalk.svg',
    import.meta.url,
  ).href,
  telegram: new URL(
    '@/assets/images/platform_logos/telegram.svg',
    import.meta.url,
  ).href,
  discord: new URL(
    '@/assets/images/platform_logos/discord.svg',
    import.meta.url,
  ).href,
  slack: new URL('@/assets/images/platform_logos/slack.svg', import.meta.url)
    .href,
  kook: new URL('@/assets/images/platform_logos/kook.png', import.meta.url)
    .href,
  satori: new URL('@/assets/images/platform_logos/satori.png', import.meta.url)
    .href,
  Satori: new URL('@/assets/images/platform_logos/satori.png', import.meta.url)
    .href,
  misskey: new URL(
    '@/assets/images/platform_logos/misskey.png',
    import.meta.url,
  ).href,
  line: new URL('@/assets/images/platform_logos/line.png', import.meta.url)
    .href,
  matrix: new URL('@/assets/images/platform_logos/matrix.svg', import.meta.url)
    .href,
  mattermost: new URL(
    '@/assets/images/platform_logos/mattermost.svg',
    import.meta.url,
  ).href,
};

const TUTORIAL_PATHS: Record<string, string> = {
  qq_official_webhook: 'platform/qqofficial/webhook.html',
  qq_official: 'platform/qqofficial/websockets.html',
  aiocqhttp: 'platform/aiocqhttp.html',
  napcat: 'platform/napcat.html',
  wecom: 'platform/wecom.html',
  weixin_oc: 'platform/weixin_oc.html',
  wecom_ai_bot: 'platform/wecom_ai_bot.html',
  lark: 'platform/lark.html',
  telegram: 'platform/telegram.html',
  dingtalk: 'platform/dingtalk.html',
  weixin_official_account: 'platform/weixin-official-account.html',
  discord: 'platform/discord.html',
  slack: 'platform/slack.html',
  kook: 'platform/kook.html',
  vocechat: 'platform/vocechat.html',
  satori: 'platform/satori/guide.html',
  misskey: 'platform/misskey.html',
  line: 'platform/line.html',
  matrix: 'platform/matrix.html',
  mattermost: 'platform/mattermost.html',
};

const PLATFORM_DISPLAY_NAMES: Record<string, string> = {
  aiocqhttp: 'aiocqhttp (OneBot v11)',
  napcat: 'napcat (NapCat WebSocket)',
  qq_official: 'qq_official (QQ 官方机器人平台)',
  weixin_official_account: 'weixin_official_account (微信公众号)',
  wecom: 'wecom (企业微信应用)',
  wecom_ai_bot: 'wecom_ai_bot (企业微信智能机器人)',
  lark: 'lark (飞书)',
  dingtalk: 'dingtalk (钉钉)',
  telegram: 'telegram (Telegram)',
  discord: 'discord (Discord)',
  misskey: 'misskey (Misskey)',
  slack: 'slack (Slack)',
  kook: 'kook (KOOK)',
  vocechat: 'vocechat (VoceChat)',
  satori: 'satori (Satori)',
  line: 'line (LINE)',
  matrix: 'matrix (Matrix)',
};

const PLATFORM_COLORS: Record<string, string> = {
  aiocqhttp: 'blue',
  napcat: 'blue',
  qq_official: 'purple',
  telegram: 'light-blue',
  discord: 'indigo',
  webchat: 'orange',
};

interface PlatformTemplate {
  [key: string]: unknown;
}

export function getPlatformIcon(name: string): string | undefined {
  return PLATFORM_ICON_URLS[name];
}

export function getTutorialLink(platformType: string, locale?: string): string {
  const path = TUTORIAL_PATHS[platformType];
  return docsHref(path || '', locale);
}

export function getPlatformDescription(
  _template: PlatformTemplate,
  name: string,
): string {
  if (name.includes('vocechat')) {
    return '由 @HikariFroya 提供。';
  }
  if (name.includes('kook')) {
    return '由 @wuyan1003 提供。';
  }
  return '';
}

export function getPlatformDisplayName(platformId: string): string {
  return PLATFORM_DISPLAY_NAMES[platformId] || platformId;
}

export function getPlatformColor(platformId: string): string {
  return PLATFORM_COLORS[platformId] || 'grey';
}
