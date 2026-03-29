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
    "border-color": "#A1C9FF",
    "carousel-control-size": 10,
  },
  colors: {
    // === MD3 Core Colors (Business Blue - Dark Mode) ===
    primary: "#A1C9FF", // Lighter blue for better contrast on dark
    "primary-darken-1": "#5BA4FF", // Hover state blue
    secondary: "#CCC2DC", // Light purple-gray
    "secondary-darken-1": "#B8B0C8", // Hover state
    tertiary: "#7DD9CC", // Light teal
    "tertiary-darken-1": "#5FCBBA", // Hover state

    // === MD3 Semantic Colors (Dark Mode) ===
    info: "#4DD0E1", // Cyan - informational
    success: "#69F0AE", // Green - success states
    warning: "#FFD54F", // Amber - warnings
    error: "#FFB4AB", // Light red - errors

    // === MD3 Container Colors (Dark Mode - darker containers) ===
    "primary-container": "#004A8F", // Dark blue container
    "on-primary-container": "#D8E2FF", // Light text on container
    "secondary-container": "#3F4354", // Dark gray-blue container
    "on-secondary-container": "#D8E2EC", // Light text on container
    "tertiary-container": "#00574A", // Dark teal container
    "on-tertiary-container": "#9CF1E8", // Light text on container
    "error-container": "#93000A", // Dark red container
    "on-error-container": "#FFDAD6", // Light text on container

    // === MD3 Surface Colors (Dark Mode) ===
    surface: "#0F0F12", // Very dark background for reactor aesthetic
    "on-surface": "#E4E1E6", // Light text on dark surface
    "surface-variant": "#1A1A22", // Elevated dark surface (glassmorphism layer)
    "on-surface-variant": "#C4C6D0", // Light text on variant
    surfaceTint: "#A1C9FF", // Blue tint for elevation

    // === MD3 Outline Colors (Dark Mode) ===
    outline: "#8E9099", // Borders in dark mode
    "outline-variant": "#44474F", // Subtle borders

    // === MD3 Inverse Colors (Dark Mode becomes light) ===
    "inverse-surface": "#E4E1E6", // Light surface
    "inverse-on-surface": "#303033", // Dark text on light
    "inverse-primary": "#005FB0", // Dark primary on light

    // === Additional UI Colors ===
    background: "#0A0A0C", // Deep reactor black
    accent: "#FFAB91", // Peach accent

    // === Light Variant Colors (inverted for dark mode) ===
    lightprimary: "#1A3A5C", // Dark blue for subtle backgrounds
    lightsecondary: "#2A2D38", // Dark gray for subtle backgrounds
    lightsuccess: "#1B3D1F", // Dark green
    lighterror: "#4D1F1F", // Dark red
    lightwarning: "#4D3D00", // Dark amber

    // === Text Colors ===
    primaryText: "#D8E2FF", // Light text
    secondaryText: "#C4C6D0", // Muted light text

    // === Border Colors ===
    borderLight: "#43444E", // Light borders on dark
    border: "#303033", // Default dark border
    inputBorder: "#8E9099", // Input borders

    // === Container/Card Colors ===
    containerBg: "rgba(20, 20, 25, 0.4)", // Translucent glassmorphism cards
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
