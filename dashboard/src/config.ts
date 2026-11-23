import { DARK_THEME_NAME, LIGHT_THEME_NAME } from "@/theme/constants";

export type ThemeMode = "light" | "dark" | "system";

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
  const mode = localStorage.getItem("themeMode");
  if (mode === "light" || mode === "dark" || mode === "system") return mode;
  if (mode === "auto" || localStorage.getItem("autoSwitchTheme") === "true") {
    localStorage.setItem("themeMode", "system");
    return "system";
  }

  const legacyTheme = localStorage.getItem("uiTheme");
  const migratedMode =
    legacyTheme === DARK_THEME_NAME || legacyTheme === "PurpleThemeDark"
      ? "dark"
      : legacyTheme === LIGHT_THEME_NAME || legacyTheme === "PurpleTheme"
        ? "light"
        : "system";
  localStorage.setItem("themeMode", migratedMode);
  return migratedMode;
}

export function resolveUiTheme(mode: ThemeMode): string {
  if (mode === "dark") return DARK_THEME_NAME;
  if (mode === "light") return LIGHT_THEME_NAME;
  const prefersDark = typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches;
  return prefersDark ? DARK_THEME_NAME : LIGHT_THEME_NAME;
}

const themeMode = checkThemeMode();
const uiTheme = resolveUiTheme(themeMode);
localStorage.setItem("uiTheme", uiTheme);

const config: ConfigProps = {
  Sidebar_drawer: true,
  Customizer_drawer: false,
  mini_sidebar: false,
  fontTheme: "Roboto",
  uiTheme,
  themeMode,
  inputBg: false,
};

export default config;
