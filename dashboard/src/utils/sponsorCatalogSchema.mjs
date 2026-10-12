export const SPONSOR_TEMPLATES = [
  'OpenAI Compatible', 'OpenAI Responses', 'Google Gemini', 'Anthropic',
  'MiraRouter', 'SSYCloud(胜算云)', 'AIHubMix'
]

export const SPONSOR_CACHE_TTL = 6 * 60 * 60 * 1000
export const SPONSOR_CATALOG_URL = 'https://sponsors.astrbot.app/providers.json'
export const SPONSOR_LOCALES = {
  'zh-CN': '简体中文',
  'en-US': 'English',
  'ja-JP': '日本語',
  'ru-RU': 'Русский'
}

/**
 * Validate the public catalog before publishing, caching, or applying presets.
 *
 * Args:
 *   input: Untrusted catalog JSON.
 * Returns:
 *   A normalized catalog containing only supported public fields.
 * Raises:
 *   TypeError: If a field, URL, identifier, or template is invalid.
 */
export function parseSponsorCatalog(input) {
  if (!input || input.version !== 1 || !Array.isArray(input.sponsors) || input.sponsors.length > 100) {
    throw new TypeError('Invalid sponsor catalog version or list')
  }
  if (typeof input.updated_at !== 'string' || !Number.isFinite(Date.parse(input.updated_at))) {
    throw new TypeError('Invalid catalog timestamp')
  }
  const ids = new Set()
  const sponsors = input.sponsors.map(item => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) {
      throw new TypeError('Invalid sponsor entry')
    }
    const fields = { id: 64, title: 80, logo: 2048, subtitle: 160, api_base: 2048, template: 80 }
    const sponsor = {}
    for (const [key, limit] of Object.entries(fields)) {
      if (typeof item[key] !== 'string' || item[key].length > limit) {
        throw new TypeError(`Invalid sponsor ${key}`)
      }
      sponsor[key] = item[key].trim()
      if (key !== 'subtitle' && !sponsor[key]) throw new TypeError(`Missing sponsor ${key}`)
    }
    if (!/^[a-z0-9][a-z0-9_-]{0,63}$/.test(sponsor.id) || ids.has(sponsor.id)) {
      throw new TypeError('Sponsor IDs must be unique lowercase identifiers')
    }
    ids.add(sponsor.id)
    if (!SPONSOR_TEMPLATES.includes(sponsor.template)) throw new TypeError('Unsupported provider template')
    for (const key of ['website_url', 'help_url']) {
      if (item[key] === undefined) continue
      if (typeof item[key] !== 'string' || item[key].length > 2048) {
        throw new TypeError(`Invalid sponsor ${key}`)
      }
      const value = item[key].trim()
      if (value) sponsor[key] = value
    }
    for (const key of ['logo', 'api_base', 'website_url', 'help_url']) {
      if (!sponsor[key]) continue
      let url
      try { url = new URL(sponsor[key]) } catch { throw new TypeError(`Invalid ${key} URL`) }
      if (url.protocol !== 'https:' || !url.hostname || url.username || url.password || (['logo', 'api_base'].includes(key) && url.hash)) {
        throw new TypeError(`${key} must be an HTTPS URL without credentials (logo and api_base also forbid fragments)`)
      }
    }
    if (!Number.isSafeInteger(item.order) || item.order < 0 || item.order > 100000) {
      throw new TypeError('Sponsor order must be an integer from 0 to 100000')
    }
    sponsor.order = item.order
    if (item.i18n !== undefined) {
      if (!item.i18n || typeof item.i18n !== 'object' || Array.isArray(item.i18n)) {
        throw new TypeError('Invalid sponsor translations')
      }
      const translations = {}
      for (const [locale, translation] of Object.entries(item.i18n)) {
        if (!Object.hasOwn(SPONSOR_LOCALES, locale) || !translation || typeof translation !== 'object' || Array.isArray(translation)) {
          throw new TypeError('Invalid sponsor translation locale or fields')
        }
        const fields = {}
        for (const [key, limit] of [['title', 80], ['subtitle', 160]]) {
          if (translation[key] === undefined) continue
          if (typeof translation[key] !== 'string' || translation[key].length > limit) {
            throw new TypeError(`Invalid translated sponsor ${key}`)
          }
          const value = translation[key].trim()
          if (value) fields[key] = value
        }
        if (Object.keys(fields).length) translations[locale] = fields
      }
      if (Object.keys(translations).length) sponsor.i18n = translations
    }
    return sponsor
  })
  sponsors.sort((a, b) => a.order - b.order || a.id.localeCompare(b.id))
  return { version: 1, updated_at: input.updated_at, sponsors }
}
