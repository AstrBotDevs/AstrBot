import type { ThemeTypes } from "@/types/themeTypes/ThemeType";
import { DARK_THEME_NAME } from "./constants";

/**
 * BlueBusiness Dark Theme - Material Design 3 inspired
 * Seed Color: #005FB0 (Business Blue)
 *
 * MD3 Dark Mode Colors:
 * - Uses tonal surface variants instead of shadows for elevation
 * - Higher saturation for better contrast in dark mode
 * - Surface tint color applied to create depth perception
 */
const BlueBusinessDarkTheme: ThemeTypes = {
  name: DARK_THEME_NAME,
  dark: true,
  variables: {
    "border-color": "#1F2124",
    "carousel-control-size": 10,
    // Aliases for custom text colors — maps to standard MD3 on-surface
    "primaryText": "rgba(226, 226, 231, 0.92)",
    "secondaryText": "rgba(226, 226, 231, 0.65)",
  },
  colors: {
    // === MD3 Core Colors (Cherenkov Energy - Deep Reactor) ===
    primary: "#00F2FF", // Cherenkov blue — high-energy particle light
    "primary-darken-1": "#00C4CC", // Cherenkov hover
    secondary: "#636366", // Lead gray — does not compete for visual focus
    "secondary-darken-1": "#4A4A4D", // Hover state
    tertiary: "#7DD9CC", // Light teal
    "tertiary-darken-1": "#5FCBBA", // Hover state

    // === MD3 Semantic Colors (Cherenkov Energy) ===
    info: "#00C8E8", // Cherenkov info cyan
    success: "#00C7BE", // Mint — industrial precision green
    warning: "#FF9500", // Amber —仪表盘警示感
    error: "#FF3B30", // Lava red —故障告警

    // === MD3 Container Colors (Dark Mode - deeper containers) ===
    "primary-container": "#004A55", // Deep cyan container
    "on-primary-container": "#A0F7FF", // Light text on container
    "secondary-container": "#2A2A2E", // Dark gray container
    "on-secondary-container": "#C8C8CC", // Light text on container
    "tertiary-container": "#00574A", // Dark teal container
    "on-tertiary-container": "#9CF1E8", // Light text on container
    "error-container": "#3D0D0A", // Deep red container
    "on-error-container": "#FFDAD6", // Light text on container

    // === MD3 Surface Colors (Cherenkov Energy —极黑背景) ===
    surface: "#0D0D0F", // Dark glass —磨砂钛金，带 0.4 透明度
    "on-surface": "#E2E2E7", // Light text on dark surface
    "surface-variant": "#1A1A1E", // Elevated dark surface (glassmorphism layer)
    "on-surface-variant": "#636366", // Muted — does not compete for focus
    surfaceTint: "#00F2FF", // Cherenkov blue tint for elevation

    // === MD3 Outline Colors (Industrial — cold gray 1px) ===
    outline: "#1F2124", // Industrial lines — cold gray
    "outline-variant": "#2A2A2E", // Subtle borders

    // === MD3 Inverse Colors (Dark Mode becomes light) ===
    "inverse-surface": "#E2E2E7", // Light surface
    "inverse-on-surface": "#303033", // Dark text on light
    "inverse-primary": "#004A55", // Dark primary on light

    // === Additional UI Colors ===
    background: "#050507", // Absolute abyss —屏蔽所有杂光
    accent: "#FFAB91", // Peach accent

    // === Light Variant Colors (inverted for dark mode) ===
    lightprimary: "#003544", // Deep Cherenkov for subtle backgrounds
    lightsecondary: "#2A2A2E", // Dark gray for subtle backgrounds
    lightsuccess: "#003D35", // Deep mint
    lighterror: "#3D0D0A", // Deep red
    lightwarning: "#3D2800", // Deep amber

    // === Text Colors ===
    primaryText: "#E2E2E7", // Light text
    secondaryText: "#636366", // Muted gray

    // === Border Colors ===
    borderLight: "#2A2A2E", // Subtle borders on dark
    border: "#1F2124", // Default dark border — industrial gray
    inputBorder: "#3A3A3E", // Input borders

    // === Container/Card Colors ===
    containerBg: "rgba(13, 13, 15, 0.6)", // Dark glass with backdrop blur
    "on-surface-variant-bg": "rgba(26, 26, 34, 0.5)", // Slightly lighter glassmorphism

    // === Social Colors ===
    facebook: "#5388D4",
    twitter: "#4DA6E8",
    linkedin: "#2A7BB0",

    // === Gray Scale (Dark Mode - inverted feel) ===
    gray100: "#303033",
    gray200: "#424250",
    gray300: "#5C5C6B",
    gray400: "#787888",
    gray500: "#9E9EAB",
    gray600: "#BDBDCA",
    gray700: "#D1D1D9",
    gray800: "#E8E8EC",
    gray900: "#F5F5F7",

    // === Primary/Secondary Tonal Range (Dark Mode) ===
    primary50: "#001A41",
    primary100: "#002D64",
    primary200: "#004A8F",
    primary300: "#0068BA",
    primary400: "#1E88E5",
    primary500: "#42A5F5",
    primary600: "#64B5F6",
    primary700: "#90CAF9",
    primary800: "#BBDEFB",
    primary900: "#E3F2FD",

    secondary50: "#1A1B21",
    secondary100: "#2F303A",
    secondary200: "#454655",
    secondary300: "#5C5E70",
    secondary400: "#74778B",
    secondary500: "#8E91A6",
    secondary600: "#ABABC4",
    secondary700: "#CACAE0",
    secondary800: "#E0E0EC",
    secondary900: "#F3F3F8",

    // === Code/Monaco Editor Colors (Dark) ===
    codeBg: "#1A1B21",
    preBg: "#121218",
    code: "#E4E1E6",

    // === Chat Bubble Colors (Dark Mode) ===
    chatMessageBubble: "#2D3040", // User bubble - darker
    chatAssistantBubble: "#1E2A3F", // Assistant bubble - dark blue

    // === Component Specific ===
    mcpCardBg: "#1E1E26",

    // === Overlay ===
    overlay: "#000000AA",
  },
};

export { BlueBusinessDarkTheme };
