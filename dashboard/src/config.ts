import { LIGHT_THEME_NAME, DARK_THEME_NAME } from "@/theme/constants";

export type ConfigProps = {
  Sidebar_drawer: boolean;
  Customizer_drawer: boolean;
  mini_sidebar: boolean;
  fontTheme: string;
  uiTheme: string;
  inputBg: boolean;
};

function checkUITheme() {
  /* 检查localStorage有无记忆的主题选项，如有则使用，否则使用默认值 */
  const theme = localStorage.getItem("uiTheme");
  if (!theme || ![LIGHT_THEME_NAME, DARK_THEME_NAME].includes(theme)) {
    localStorage.setItem("uiTheme", LIGHT_THEME_NAME); // todo: 这部分可以根据vuetify.ts的默认主题动态调整
    return LIGHT_THEME_NAME;
  } else return theme;
}

const config: ConfigProps = {
  Sidebar_drawer: true,
  Customizer_drawer: false,
  mini_sidebar: false,
  fontTheme: "Roboto",
  uiTheme: checkUITheme(),
  inputBg: false,
};

export default config;
