import { resolveThemeName, themeNames } from '@/design/theme';

export type ThemeMode = 'light' | 'dark' | 'system';

export type ConfigProps = {
  Sidebar_drawer: boolean;
  Customizer_drawer: boolean;
  mini_sidebar: boolean;
  themeMode: ThemeMode;
  inputBg: boolean;
};

function checkThemeMode(): ThemeMode {
  const mode = localStorage.getItem('themeMode') as ThemeMode | null;
  if (mode === 'light' || mode === 'dark' || mode === 'system') return mode;

  localStorage.setItem('themeMode', 'system');
  return 'system';
}

export function resolveUiTheme(mode: ThemeMode): string {
  if (mode === 'dark' || mode === 'light') return resolveThemeName(mode);
  return getSystemUiTheme();
}

export function getSystemUiTheme(): string {
  const prefersDark =
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-color-scheme: dark)').matches;
  return prefersDark ? themeNames.dark : themeNames.light;
}

export function getInitialSystemPrefersDark(): boolean {
  return getSystemUiTheme() === themeNames.dark;
}

const themeMode = checkThemeMode();

const config: ConfigProps = {
  Sidebar_drawer: true,
  Customizer_drawer: false,
  mini_sidebar: false,
  themeMode,
  inputBg: false,
};

export default config;
