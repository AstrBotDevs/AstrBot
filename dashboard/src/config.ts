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

function checkThemeMode(): ThemeMode {
  const mode = localStorage.getItem('themeMode') as ThemeMode | null;
  if (mode === 'light' || mode === 'dark' || mode === 'system') return mode;

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

export function resolveUiTheme(mode: ThemeMode): string {
  if (mode === 'dark') return 'PurpleThemeDark';
  if (mode === 'light') return 'PurpleTheme';
  const prefersDark =
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-color-scheme: dark)').matches;
  return prefersDark ? 'PurpleThemeDark' : 'PurpleTheme';
}

const themeMode = checkThemeMode();
const uiTheme = resolveUiTheme(themeMode);

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
