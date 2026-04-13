import type { ThemeTypes } from '@/types/themeTypes/ThemeType';

const PurpleTheme: ThemeTypes = {
  name: 'PurpleTheme',
  dark: false,
  variables: {
    'border-color': '#3c96ca',
    'carousel-control-size': 10
  },
  colors: {
    primary: '#3b82f6',
    secondary: '#6366f1',
    info: '#06b6d4',
    success: '#10b981',
    accent: '#f472b6',
    warning: '#f59e0b',
    error: '#ef4444',
    lightprimary: '#eff6ff',
    lightsecondary: '#eef2ff',
    lightsuccess: '#ecfdf5',
    lighterror: '#fef2f2',
    lightwarning: '#fffbeb',
    primaryText: '#1f2937',
    secondaryText: '#6b7280',
    darkprimary: '#2563eb',
    darksecondary: '#4f46e5',
    borderLight: '#e5e7eb',
    border: '#d1d5db',
    inputBorder: '#9ca3af',
    containerBg: '#f8fafc',
    surface: '#ffffff',
    'on-surface-variant': '#f9fafb',
    facebook: '#4267b2',
    twitter: '#1da1f2',
    linkedin: '#0e76a8',
    gray100: '#f9fafb',
    primary200: '#bfdbfe',
    secondary200: '#c7d2fe',
    background: '#ffffff',
    overlay: '#ffffffaa',
    codeBg: '#f3f4f6',
    preBg: '#f9fafb',
    code: '#1f2937',
    chatMessageBubble: '#f1f5f9',
    mcpCardBg: '#f8fafc',
  }
};

export { PurpleTheme };
