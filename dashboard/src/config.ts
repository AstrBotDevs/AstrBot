export type ConfigProps = {
  Sidebar_drawer: boolean;
  Customizer_drawer: boolean;
  mini_sidebar: boolean;
  fontTheme: string;
  uiTheme: string;
  inputBg: boolean;
};

function checkUITheme() {
  const theme = localStorage.getItem("uiTheme");
  console.log('memorized theme: ', theme);
  if (!theme || !(['PurpleTheme', 'PurpleThemeDark'].includes(theme))) {
    localStorage.setItem("uiTheme", "PurpleTheme");
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
