import { useModuleI18n } from '@/i18n/composables';
import { usePluginI18n } from '@/utils/pluginI18n';

const CONFIG_METADATA_I18N_PREFIXES = [
  'ai_group.',
  'ext_group.',
  'misc_config_group.',
  'platform_group.',
  'provider_group.',
  'system_group.',
] as const;

function isConfigMetadataI18nKey(value: string): boolean {
  return CONFIG_METADATA_I18N_PREFIXES.some((prefix) =>
    value.startsWith(prefix),
  );
}

interface ConfigTextResolverProps {
  pluginName?: string;
  pluginI18n?: Record<string, unknown>;
}

export function useConfigTextResolver(props: ConfigTextResolverProps = {}) {
  const { tm, getRaw } = useModuleI18n('features/config-metadata');
  const { configText } = usePluginI18n();

  const translateIfKey = (value: unknown) => {
    if (!value || typeof value !== 'string') return value;
    const raw = getRaw(value);
    if (typeof raw === 'string') {
      return tm(value);
    }
    if (raw !== null) {
      return raw;
    }
    if (isConfigMetadataI18nKey(value)) {
      console.warn(
        `Translation key not found: features.config-metadata.${value}`,
      );
    }
    return value;
  };

  const hasPluginI18n = (): boolean => {
    return Boolean(
      props.pluginName &&
      props.pluginI18n &&
      Object.keys(props.pluginI18n).length > 0,
    );
  };

  const resolveConfigText = (path: string, attr: string, fallback: unknown) => {
    const fallbackText = (translateIfKey(fallback) as string) || '';
    if (!hasPluginI18n()) {
      return fallbackText;
    }
    return configText(props.pluginI18n, path, attr, fallbackText);
  };

  return {
    translateIfKey,
    resolveConfigText,
  };
}
