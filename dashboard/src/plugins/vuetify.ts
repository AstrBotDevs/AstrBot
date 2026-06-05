import { createVuetify } from 'vuetify';
import { en, ru, zhHans } from 'vuetify/locale';
import '@/assets/mdi-subset/materialdesignicons-subset.css';
import * as components from 'vuetify/components';
import * as directives from 'vuetify/directives';
import { PurpleTheme } from '@/theme/LightTheme';
import { PurpleThemeDark } from '@/theme/DarkTheme';

const zhHansMessages = {
  ...zhHans,
  open: '打开',
  dismiss: '关闭',
  dataFooter: {
    ...zhHans.dataFooter,
    itemsPerPageText: '每页条数：',
    firstPage: '第一页',
    lastPage: '最后一页',
  },
  input: {
    ...zhHans.input,
    clear: '清空 {0}',
    prependAction: '{0} 前置操作',
    appendAction: '{0} 后置操作',
    otp: '请输入第 {0} 位验证码',
  },
  pagination: {
    ...zhHans.pagination,
    ariaLabel: {
      ...zhHans.pagination.ariaLabel,
      first: '第一页',
      last: '最后一页',
    },
  },
  stepper: {
    next: '下一步',
    prev: '上一步',
  },
  loading: '加载中...',
};

const vuetifyLocaleMap: Record<string, string> = {
  'zh-CN': 'zhHans',
  'en-US': 'en',
  'ru-RU': 'ru',
};

export const getVuetifyLocale = (locale?: string | null) => {
  if (!locale) {
    return 'zhHans';
  }
  return vuetifyLocaleMap[locale] || 'zhHans';
};

export default createVuetify({
  components,
  directives,
  locale: {
    locale: getVuetifyLocale(
      typeof localStorage === 'undefined'
        ? null
        : localStorage.getItem('astrbot-locale'),
    ),
    fallback: 'en',
    messages: {
      en,
      ru,
      zhHans: zhHansMessages,
    },
  },

  theme: {
    defaultTheme: 'PurpleTheme',
    themes: {
      PurpleTheme,
      PurpleThemeDark,
    },
  },
  defaults: {
    VBtn: {},
    VCard: {
      rounded: 'lg',
    },
    VTextField: {
      rounded: 'lg',
    },
    VTooltip: {
      // set v-tooltip default location to top
      location: 'top',
    },
  },
});
