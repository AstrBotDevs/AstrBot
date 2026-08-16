import type { ThemeDefinition } from 'vuetify';

export const themeNames = {
  light: 'AstrBotLight',
  dark: 'AstrBotDark',
} as const;

export type AstrBotThemeName = (typeof themeNames)[keyof typeof themeNames];

type ThemeColors = Record<string, string>;

const sharedThemeVariables = {
  'border-color': '#c4ccd6',
  'carousel-control-size': 10,
};

const lightColors: ThemeColors = {
  primary: '#2678b8',
  secondary: '#4d667d',
  background: '#f6f8fb',
  surface: '#ffffff',
  'surface-variant': '#e9eef4',
  'on-surface': '#18212b',
  'on-surface-variant': '#526070',
  outline: '#758393',
  'outline-variant': '#c4ccd6',
  success: '#2e7d32',
  warning: '#a15c00',
  error: '#ba1a1a',
  info: '#1769aa',
  'on-primary': '#ffffff',
  'on-secondary': '#ffffff',
  'on-background': '#18212b',
  'on-success': '#ffffff',
  'on-warning': '#ffffff',
  'on-error': '#ffffff',
  'on-info': '#ffffff',
  'app-surface': '#f6f8fb',
  'code-surface': '#f2f5f8',
  'code-text': '#18212b',
  'chat-bubble': '#e8f1f8',
  'extension-surface': '#fbfcfe',
};

const darkColors: ThemeColors = {
  primary: '#83b8e0',
  secondary: '#b0c8dd',
  background: '#12171d',
  surface: '#1b222a',
  'surface-variant': '#27313c',
  'on-surface': '#e2e8ef',
  'on-surface-variant': '#c0cad5',
  outline: '#8a99a8',
  'outline-variant': '#3f4b58',
  success: '#7fcd85',
  warning: '#f1b968',
  error: '#ffb4ab',
  info: '#9dcbef',
  'on-primary': '#003352',
  'on-secondary': '#1a3143',
  'on-background': '#e2e8ef',
  'on-success': '#003907',
  'on-warning': '#3d2800',
  'on-error': '#690005',
  'on-info': '#00344d',
  'app-surface': '#12171d',
  'code-surface': '#161d25',
  'code-text': '#e2e8ef',
  'chat-bubble': '#26333f',
  'extension-surface': '#202932',
};

export const AstrBotLight: ThemeDefinition = {
  dark: false,
  colors: lightColors,
  variables: sharedThemeVariables,
};

export const AstrBotDark: ThemeDefinition = {
  dark: true,
  colors: darkColors,
  variables: sharedThemeVariables,
};

export const astrBotThemes = {
  [themeNames.light]: AstrBotLight,
  [themeNames.dark]: AstrBotDark,
};

export function resolveThemeName(mode: 'light' | 'dark'): AstrBotThemeName {
  return mode === 'dark' ? themeNames.dark : themeNames.light;
}

export function applyUserThemeColors(
  themes: Record<string, ThemeDefinition> | undefined,
  primary?: string | null,
  secondary?: string | null,
) {
  if (!themes) return;

  for (const name of Object.values(themeNames)) {
    const theme = themes[name];
    if (!theme?.colors) continue;
    if (primary) theme.colors.primary = primary;
    if (secondary) theme.colors.secondary = secondary;
  }
}

export const defaultThemeColors = {
  primary: lightColors.primary,
  secondary: lightColors.secondary,
};
