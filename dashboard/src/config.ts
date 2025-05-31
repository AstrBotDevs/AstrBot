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
  if (!theme || !(['PurpleTheme', 'PurpleThemeDark'].includes(theme))) {
    localStorage.setItem("uiTheme", "PurpleTheme");   // todo: 这部分可以根据vuetify.ts的默认主题动态调整
    return 'PurpleTheme';
  } else return theme;
}

const config: ConfigProps = {
  Sidebar_drawer: true,
  Customizer_drawer: false,
  mini_sidebar: false,
  fontTheme: 'Roboto',
  uiTheme: checkUITheme(),
  inputBg: false
};

export default config;
