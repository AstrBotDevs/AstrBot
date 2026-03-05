import axios from 'axios'

export const LOG_LANG_LOCALE_STORAGE_KEY = 'logLangLocale'
export const DEFAULT_LOG_LANG_LOCALE = 'zh-CN'

function safeGetLocalStorageItem(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch (_error) {
    return null
  }
}

function safeSetLocalStorageItem(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch (_error) {
    // ignore
  }
}

export function getOrInitLogLangLocale(): string {
  const storedLocale = safeGetLocalStorageItem(LOG_LANG_LOCALE_STORAGE_KEY)
  if (storedLocale) return storedLocale
  safeSetLocalStorageItem(LOG_LANG_LOCALE_STORAGE_KEY, DEFAULT_LOG_LANG_LOCALE)
  return DEFAULT_LOG_LANG_LOCALE
}

export function setStoredLogLangLocale(langLocale: string): void {
  safeSetLocalStorageItem(LOG_LANG_LOCALE_STORAGE_KEY, langLocale)
}

export type SetBackendLogLangLocaleResult = {
  ok: boolean
  message?: string
}

export async function setBackendLogLangLocale(
  langLocale: string
): Promise<SetBackendLogLangLocaleResult> {
  const response = await axios.post('/api/setLang', { lang: langLocale })
  const ok =
    response?.data?.status
      ? response.data.status === 'ok'
      : response?.data?.code
        ? response.data.code === 200
        : true

  const message = response?.data?.message ?? response?.data?.data?.message
  return { ok, message }
}

export async function initBackendLogLangLocale(): Promise<void> {
  const langLocale = getOrInitLogLangLocale()
  const token = safeGetLocalStorageItem('token')
  if (!token) return

  try {
    const result = await setBackendLogLangLocale(langLocale)
    if (!result.ok) {
      console.error('Failed to set language on server:', result.message)
    }
  } catch (error) {
    console.error('Error setting language on server:', error)
  }
}
