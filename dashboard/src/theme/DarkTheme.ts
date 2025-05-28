import type { ThemeTypes } from '@/types/themeTypes/ThemeType';

const PurpleThemeDark: ThemeTypes = {
  name: 'PurpleThemeDark',
  dark: true,
  variables: {
    'border-color': '#1677ff',
    'carousel-control-size': 10
  },
  colors: {
    primary: '#1677ff',
    secondary: '#722ed1',
    info: '#03c9d7',
    success: '#52c41a',
    accent: '#FFAB91',
    warning: '#faad14',
    error: '#ff4d4f',
    lightprimary: '#eef2f6',
    lightsecondary: '#ede7f6',
    lightsuccess: '#b9f6ca',
    lighterror: '#f9d8d8',
    lightwarning: '#fff8e1',
    primaryText: '#ffffff',
    secondaryText: '#ffffffcc',
    darkprimary: '#1565c0',
    darksecondary: '#4527a0',
    borderLight: '#d0d0d0',
    border: '#333333ee',
    inputBorder: '#787878',
    containerBg: '#1a1a1a',
    surface: '#1f1f1f',
    'on-surface-variant': '#000',
    facebook: '#4267b2',
    twitter: '#1da1f2',
    linkedin: '#0e76a8',
    gray100: '#cccccccc',
    primary200: '#90caf9',
    secondary200: '#b39ddb',
    background: '#111111',
    overlay: '#111111aa',
    codeBg: '#282833',
    code: '#ffffffdd'
  }
};

export { PurpleThemeDark };
