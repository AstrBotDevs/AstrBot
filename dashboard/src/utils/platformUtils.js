/**
 * 平台相关工具函数
 */

/**
 * 获取平台图标
 * @param {string} name - 平台名称或类型
 * @returns {string|undefined} 图标URL
 */
export function getPlatformIcon(name) {
  if (name === 'aiocqhttp') {
    return new URL('@/assets/images/platform_logos/onebot.png', import.meta.url).href
  } else if (name === 'qq_official' || name === 'qq_official_webhook') {
    return new URL('@/assets/images/platform_logos/qq.png', import.meta.url).href
  } else if (name === 'wecom' || name === 'wecom_ai_bot') {
    return new URL('@/assets/images/platform_logos/wecom.png', import.meta.url).href
  } else if (name === 'lark') {
    return new URL('@/assets/images/platform_logos/lark.png', import.meta.url).href
  } else if (name === 'dingtalk') {
    return new URL('@/assets/images/platform_logos/dingtalk.svg', import.meta.url).href
  } else if (name === 'telegram') {
    return new URL('@/assets/images/platform_logos/telegram.svg', import.meta.url).href
  } else if (name === 'discord') {
    return new URL('@/assets/images/platform_logos/discord.svg', import.meta.url).href
  } else if (name === 'slack') {
    return new URL('@/assets/images/platform_logos/slack.svg', import.meta.url).href
  } else if (name === 'kook') {
    return new URL('@/assets/images/platform_logos/kook.png', import.meta.url).href
  } else if (name === 'vocechat') {
    return new URL('@/assets/images/platform_logos/vocechat.png', import.meta.url).href
  } else if (name === 'satori' || name === 'Satori') {
    return new URL('@/assets/images/platform_logos/satori.png', import.meta.url).href
  } else if (name === 'misskey') {
    return new URL('@/assets/images/platform_logos/misskey.png', import.meta.url).href
  }
}

/**
 * 获取平台教程链接
 * @param {string} platformType - 平台类型
 * @returns {string} 教程链接
 */
export function getTutorialLink(platformType) {
  const tutorialMap = {
    "qq_official_webhook": "https://docs.astrbot.app/deploy/platform/qqofficial/webhook.html",
    "qq_official": "https://docs.astrbot.app/deploy/platform/qqofficial/websockets.html",
    "aiocqhttp": "https://docs.astrbot.app/deploy/platform/aiocqhttp/napcat.html",
    "wecom": "https://docs.astrbot.app/deploy/platform/wecom.html",
    "wecom_ai_bot": "https://docs.astrbot.app/deploy/platform/wecom_ai_bot.html",
    "lark": "https://docs.astrbot.app/deploy/platform/lark.html",
    "telegram": "https://docs.astrbot.app/deploy/platform/telegram.html",
    "dingtalk": "https://docs.astrbot.app/deploy/platform/dingtalk.html",
    "weixin_official_account": "https://docs.astrbot.app/deploy/platform/weixin-official-account.html",
    "discord": "https://docs.astrbot.app/deploy/platform/discord.html",
    "slack": "https://docs.astrbot.app/deploy/platform/slack.html",
    "kook": "https://docs.astrbot.app/deploy/platform/kook.html",
    "vocechat": "https://docs.astrbot.app/deploy/platform/vocechat.html",
    "satori": "https://docs.astrbot.app/deploy/platform/satori/llonebot.html",
    "misskey": "https://docs.astrbot.app/deploy/platform/misskey.html",
  }
  return tutorialMap[platformType] || "https://docs.astrbot.app";
}

/**
 * 获取平台描述
 * @param {Object} template - 平台模板
 * @param {string} name - 平台名称
 * @returns {string} 平台描述
 */
export function getPlatformDescription(template, name) {
  // special judge for community platforms
  if (name.includes('vocechat')) {
    return "由 @HikariFroya 提供。";
  } else if (name.includes('kook')) {
    return "由 @wuyan1003 提供。"
  }
  return '';
}
