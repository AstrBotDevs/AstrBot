import { useCustomizerStore } from '@/stores/customizer';
import { useTheme } from 'vuetify';

export function useThemeToggle() {
  const customizer = useCustomizerStore();
  const theme = useTheme();

  function toggleTheme() {
    const newTheme = customizer.uiTheme === 'PurpleThemeDark' ? 'PurpleTheme' : 'PurpleThemeDark';
    customizer.SET_UI_THEME(newTheme);
    theme.global.name.value = newTheme;
  }

  return {
    toggleTheme
  };
}
