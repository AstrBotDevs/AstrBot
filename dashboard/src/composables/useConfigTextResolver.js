import { useModuleI18n } from '@/i18n/composables'
import { usePluginI18n } from '@/utils/pluginI18n'

export function useConfigTextResolver(props = {}) {
  const { tm, getRaw } = useModuleI18n('features/config-metadata')
  const { configText } = usePluginI18n()

  const translateIfKey = (value) => {
    if (!value || typeof value !== 'string') return value
    return getRaw(value) ? tm(value) : value
  }

  const hasPluginI18n = () => {
    return Boolean(
      props.pluginName
      && props.pluginI18n
      && Object.keys(props.pluginI18n).length > 0,
    )
  }

  const resolveConfigText = (path, attr, fallback) => {
    const fallbackText = translateIfKey(fallback) || ''
    if (!hasPluginI18n()) {
      return fallbackText
    }
    return configText(props.pluginI18n, path, attr, fallbackText)
  }

  return {
    translateIfKey,
    resolveConfigText,
  }
}
