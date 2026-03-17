import { ref, computed } from 'vue';
import { translations as staticTranslations } from './translations';
import type { Locale } from './types';

// 全局状态
const currentLocale = ref<Locale>('zh-CN');
const translations = ref<Record<string, any>>({});

/**
 * 初始化i18n系统
 */
export async function initI18n(locale: Locale = 'zh-CN') {
  currentLocale.value = locale;

  // 加载静态翻译数据
  loadTranslations(locale);
}

/**
 * 加载翻译数据（现在从静态导入获取）
 */
function loadTranslations(locale: Locale) {
  try {
    const data = staticTranslations[locale];
    if (data) {
      translations.value = data;
    } else {
      console.warn(`Translations not found for locale: ${locale}`);
      // 回退到中文
      if (locale !== 'zh-CN') {
        console.log('Falling back to zh-CN');
        translations.value = staticTranslations['zh-CN'];
      }
    }
  } catch (error) {
    console.error(`Failed to load translations for ${locale}:`, error);
    // 回退到中文
    if (locale !== 'zh-CN') {
      console.log('Falling back to zh-CN');
      translations.value = staticTranslations['zh-CN'];
    }
  }
}

/**
 * 主要的翻译函数组合
 */
export function useI18n() {
  // 翻译函数
  const t = (key: string, params?: Record<string, string | number>): string => {
    const keys = key.split('.');
    let value: any = translations.value;

    // 遍历键路径
    for (const k of keys) {
      if (value && typeof value === 'object' && k in value) {
        value = value[k];
      } else {
        console.warn(`Translation key not found: ${key}`);
        // 返回带括号的键名，便于在开发时识别缺失的翻译
        return `[MISSING: ${key}]`;
      }
    }

    if (typeof value !== 'string') {
      console.warn(`Translation value is not string: ${key}`, value);
      // 返回带括号的键名，便于在开发时识别类型错误的翻译
      return `[INVALID: ${key}]`;
    }

    // 此时value确定是string类型
    let result: string = value;

    // 处理参数插值
    if (params) {
      result = result.replace(/\{(\w+)\}/g, (match: string, paramKey: string) => {
        return params[paramKey]?.toString() || match;
      });
    }

    return result;
  };

  // 切换语言
  const setLocale = async (newLocale: Locale) => {
    if (newLocale !== currentLocale.value) {
      currentLocale.value = newLocale;
      loadTranslations(newLocale);

      // 保存到localStorage
      localStorage.setItem('astrbot-locale', newLocale);

      // 触发自定义事件，通知相关页面重新加载配置数据
      // 这是因为插件适配器的 i18n 数据是通过后端 API 注入的，
      // 需要根据 Accept-Language 头重新获取
      window.dispatchEvent(new CustomEvent('astrbot-locale-changed', {
        detail: { locale: newLocale }
      }));
    }
  };

  // 获取当前语言
  const locale = computed(() => currentLocale.value);

  // 获取可用语言列表
  const availableLocales: Locale[] = ['zh-CN', 'en-US', 'ru-RU'];

  // 检查是否已加载
  const isLoaded = computed(() => Object.keys(translations.value).length > 0);

  return {
    t,
    locale,
    setLocale,
    availableLocales,
    isLoaded
  };
}

/**
 * 模块特定的翻译函数
 */
export function useModuleI18n(moduleName: string) {
  const { t } = useI18n();

  const tm = (key: string, params?: Record<string, string | number>): string => {
    // 将斜杠转换为点号以匹配嵌套对象结构
    const normalizedModuleName = moduleName.replace(/\//g, '.');
    return t(`${normalizedModuleName}.${key}`, params);
  };

  // 获取原始翻译值（可能是字符串、数组或对象）
  const getRaw = (key: string): any => {
    const normalizedModuleName = moduleName.replace(/\//g, '.');
    const fullKey = `${normalizedModuleName}.${key}`;
    const keys = fullKey.split('.');
    let value: any = translations.value;

    for (const k of keys) {
      if (value && typeof value === 'object' && k in value) {
        value = value[k];
      } else {
        return null;
      }
    }

    return value;
  };

  return { tm, getRaw };
}

/**
 * 语言切换器组合函数
 */
export function useLanguageSwitcher() {
  const { locale, setLocale, availableLocales } = useI18n();

  const languageOptions = computed(() => [
    { value: 'zh-CN', label: '简体中文', flag: '🇨🇳' },
    { value: 'en-US', label: 'English', flag: '🇺🇸' },
    { value: 'ru-RU', label: 'Русский', flag: '🇷🇺' }
  ]);

  const currentLanguage = computed(() => {
    return languageOptions.value.find(lang => lang.value === locale.value);
  });

  const switchLanguage = async (newLocale: Locale) => {
    await setLocale(newLocale);
  };

  return {
    locale,
    languageOptions,
    currentLanguage,
    switchLanguage,
    availableLocales
  };
}

/**
 * 将动态翻译数据（如插件提供的 i18n）合并到当前翻译中。
 * @param modulePath 模块路径，如 'features.config-metadata'
 * @param allLocaleData 所有语言的翻译数据，如 { "zh-CN": {...}, "en-US": {...} }
 */
export function mergeDynamicTranslations(modulePath: string, allLocaleData: Record<string, any>) {
  const locale = currentLocale.value;
  const localeData = allLocaleData[locale];
  if (!localeData || typeof localeData !== 'object') return;

  const pathParts = modulePath.split('.');
  let target: any = translations.value;
  for (const part of pathParts) {
    if (!(part in target) || typeof target[part] !== 'object') {
      target[part] = {};
    }
    target = target[part];
  }

  deepMerge(target, localeData);

  // 触发响应式更新
  translations.value = { ...translations.value };
}

function deepMerge(target: Record<string, any>, source: Record<string, any>) {
  for (const key of Object.keys(source)) {
    if (source[key] && typeof source[key] === 'object' && !Array.isArray(source[key])) {
      if (!(key in target) || typeof target[key] !== 'object') {
        target[key] = {};
      }
      deepMerge(target[key], source[key]);
    } else {
      target[key] = source[key];
    }
  }
}

// 初始化函数（在应用启动时调用）
export async function setupI18n() {
  // 从localStorage获取保存的语言设置
  const savedLocale = localStorage.getItem('astrbot-locale') as Locale;
  const initialLocale = savedLocale && ['zh-CN', 'en-US', 'ru-RU'].includes(savedLocale)
    ? savedLocale
    : 'zh-CN';

  await initI18n(initialLocale);
} 