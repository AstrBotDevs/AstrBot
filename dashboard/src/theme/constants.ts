import type { ThemePreset } from "@/types/theme";

export const LIGHT_THEME_NAME = "PurpleTheme";
export const DARK_THEME_NAME = "PurpleThemeDark";

// Theme presets based on MD3 color system
export const themePresets: ThemePreset[] = [
  {
    id: "blue-business",
    name: "活力商务蓝",
    nameEn: "Business Blue",
    primary: "#005FB0",
    secondary: "#565E71",
    tertiary: "#006B5B",
  },
  {
    id: "purple-default",
    name: "优雅紫",
    nameEn: "Elegant Purple",
    primary: "#6750A4",
    secondary: "#625B71",
    tertiary: "#7D5260",
  },
  {
    id: "teal-fresh",
    name: "自然清新绿",
    nameEn: "Nature Green",
    primary: "#386A20",
    secondary: "#55624C",
    tertiary: "#19686A",
  },
  {
    id: "orange-warm",
    name: "温暖橙棕",
    nameEn: "Warm Orange",
    primary: "#9C4323",
    secondary: "#77574E",
    tertiary: "#6C5D2F",
  },
  {
    id: "ocean-breeze",
    name: "海洋清风",
    nameEn: "Ocean Breeze",
    primary: "#0077B6",
    secondary: "#4A5568",
    tertiary: "#00B4D8",
  },
  {
    id: "rose-romantic",
    name: "浪漫玫瑰",
    nameEn: "Romantic Rose",
    primary: "#BE185D",
    secondary: "#9F1239",
    tertiary: "#DB2777",
  },
];
