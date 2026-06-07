export type ThemeMode = 'light' | 'dark' | 'system';

export type ConfigProps = {
  Sidebar_drawer: boolean;
  Customizer_drawer: boolean;
  mini_sidebar: boolean;
  fontTheme: string;
  uiTheme: string;
  themeMode: ThemeMode;
  inputBg: boolean;
};

/** 读 localStorage 中的 themeMode，默认 'system' */
function checkThemeMode(): ThemeMode {
  const mode = localStorage.getItem('themeMode') as ThemeMode | null;
  if (mode === 'light' || mode === 'dark' || mode === 'system') return mode;

  // 迁移旧数据：如果存在旧的 uiTheme 但没有 themeMode，按旧值推断意图
  const legacyTheme = localStorage.getItem('uiTheme');
  if (legacyTheme === 'PurpleThemeDark') {
    localStorage.setItem('themeMode', 'dark');
    return 'dark';
  }
  if (legacyTheme === 'PurpleTheme') {
    localStorage.setItem('themeMode', 'light');
    return 'light';
  }

  localStorage.setItem('themeMode', 'system');
  return 'system';
}

/** 根据 themeMode 计算出实际应使用的 Vuetify 主题名 */
function resolveUiTheme(mode: ThemeMode): string {
  if (mode === 'dark') return 'PurpleThemeDark';
  if (mode === 'light') return 'PurpleTheme';
  // system：用 matchMedia 判断当前系统偏好
  const prefersDark =
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-color-scheme: dark)').matches;
  return prefersDark ? 'PurpleThemeDark' : 'PurpleTheme';
}

const themeMode = checkThemeMode();
const uiTheme = resolveUiTheme(themeMode);

// 保证 uiTheme 在 localStorage 中与计算结果一致
localStorage.setItem('uiTheme', uiTheme);

const config: ConfigProps = {
  Sidebar_drawer: true,
  Customizer_drawer: false,
  mini_sidebar: false,
  fontTheme: 'Roboto',
  uiTheme,
  themeMode,
  inputBg: false,
};

export default config;
