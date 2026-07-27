import type { ThemeTypes } from "@/types/themeTypes/ThemeType";
import { LIGHT_THEME_NAME } from "./constants";

/**
 * BlueBusiness Light Theme - Material Design 3 inspired
 * Seed Color: #005FB0 (Business Blue)
 *
 * MD3 Color Roles:
 * - Primary: Most prominent color, used for FABs and key actions
 * - Secondary: Less prominent components like Chips
 * - Tertiary: Emphasis/balance, used for inputs and decorations
 * - Surface: Background areas with tonal elevation
 * - Error: Error/warning states
 */
const BlueBusinessLightTheme: ThemeTypes = {
  name: LIGHT_THEME_NAME,
  dark: false,
  variables: {
    "border-color": "#003153",
    "carousel-control-size": 10,
  },
  colors: {
    // === MD3 Core Colors (Blueprint Prussian Blue) ===
    primary: "#003153", // Prussian Blue — serious, not flashy
    "primary-darken-1": "#001F33", // Darker for hover states
    secondary: "#3A4A5C", // Cool gray-blue — restrained
    "secondary-darken-1": "#2A3A4C", // Darker secondary
    tertiary: "#006B5B", // Teal — restrained accent
    "tertiary-darken-1": "#00574A", // Darker tertiary

    // === MD3 Semantic Colors (Industrial — muted, not flashy) ===
    info: "#00B2D4", // Arc cyan — 高亮交互点
    success: "#00C7BE", // Mint — industrial precision
    warning: "#FF9500", // Amber —仪表盘警示感
    error: "#8B0000", // Deep red —严肃感

    // === MD3 Container Colors (Blueprint — subtle tonal elevation) ===
    "primary-container": "#D8E2FF", // Light blue container
    "on-primary-container": "#001A41", // Text on primary container
    "secondary-container": "#D8E2EC", // Light gray-blue container
    "on-secondary-container": "#111423", // Text on secondary container
    "tertiary-container": "#9CF1E8", // Light teal container
    "on-tertiary-container": "#00201D", // Text on tertiary container
    "error-container": "#FFDAD6", // Light red container
    "on-error-container": "#410002", // Text on error container

    // === MD3 Surface Colors (Blueprint Lab) ===
    surface: "#F0F4F8", // Cool blue-gray lab white
    "on-surface": "#1A2B3C", // Deep indigo text
    "surface-variant": "#E4E9F2", // Slightly deeper surface
    "on-surface-variant": "#3A4A5C", // Muted indigo text
    surfaceTint: "#003153", // Prussian Blue tint overlay

    // === MD3 Outline Colors ===
    outline: "#74777F", // Borders and dividers
    "outline-variant": "#C4C6D0", // Subtle borders

    // === MD3 Inverse Colors ===
    "inverse-surface": "#303033", // Used for dark surfaces in light mode
    "inverse-on-surface": "#F3F0F4", // Text on inverse surface
    "inverse-primary": "#A1C9FF", // Primary on dark backgrounds

    // === Additional UI Colors (Lab White) ===
    background: "#F0F4F8", // Cool blue-gray lab white
    accent: "#FFAB91", // Peach accent (Vuetify legacy)

    // === Light Variant Colors ===
    lightprimary: "#E8F4FD", // Very light blue for subtle backgrounds
    lightsecondary: "#F0F2F5", // Very light gray for subtle backgrounds
    lightsuccess: "#E8F5E9", // Very light green
    lighterror: "#FFEBEE", // Very light red
    lightwarning: "#FFF8E1", // Very light amber

    // === Text Colors ===
    primaryText: "#001A41", // Primary text color
    secondaryText: "#44474F", // Secondary text color

    // === Border Colors ===
    borderLight: "#E1E2EC", // Light borders
    border: "#C4C6D0", // Default borders
    inputBorder: "#74777F", // Input field borders

    // === Container/Card Colors ===
    containerBg: "rgba(240, 244, 248, 0.75)", // Translucent lab glass
    "on-surface-variant-bg": "rgba(228, 233, 242, 0.8)", // Slightly deeper

    // === Social Colors ===
    facebook: "#4267B2",
    twitter: "#1DA1F2",
    linkedin: "#0E76A8",

    // === Gray Scale ===
    gray100: "#F5F5F5",
    gray200: "#EEEEEE",
    gray300: "#E0E0E0",
    gray400: "#BDBDBD",
    gray500: "#9E9E9E",
    gray600: "#757575",
    gray700: "#616161",
    gray800: "#424242",
    gray900: "#212121",

    // === Primary/Secondary Tonal Range ===
    primary50: "#E3F2FD",
    primary100: "#BBDEFB",
    primary200: "#90CAF9",
    primary300: "#64B5F6",
    primary400: "#42A5F5",
    primary500: "#2196F3",
    primary600: "#1E88E5",
    primary700: "#1976D2",
    primary800: "#1565C0",
    primary900: "#0D47A1",

    secondary50: "#ECEFF1",
    secondary100: "#CFD8DC",
    secondary200: "#B0BEC5",
    secondary300: "#90A4AE",
    secondary400: "#78909C",
    secondary500: "#607D8B",
    secondary600: "#546E7A",
    secondary700: "#455A64",
    secondary800: "#37474F",
    secondary900: "#263238",

    // === Code/Monaco Editor Colors ===
    codeBg: "#F5F7FF",
    preBg: "#F8F9FF",
    code: "#1B1B1F",

    // === Chat Bubble Colors (Blueprint — tinted, not white) ===
    chatMessageBubble: "#DDE3ED", // User bubble — cool blue-gray
    chatAssistantBubble: "#EEF2FA", // Assistant bubble — blueprint paper

    // === Component Specific ===
    mcpCardBg: "#F5F7FF",

    // === Overlay ===
    overlay: "#FFFFFFDD",
  },
};

export { BlueBusinessLightTheme };
