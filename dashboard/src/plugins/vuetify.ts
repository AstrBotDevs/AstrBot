import { createVuetify } from 'vuetify';
import '@/assets/mdi-subset/materialdesignicons-subset.css';
import * as components from 'vuetify/components';
import * as directives from 'vuetify/directives';
import { PurpleTheme } from '@/theme/LightTheme';
import { PurpleThemeDark } from "@/theme/DarkTheme";
import { LIGHT_THEME_NAME, DARK_THEME_NAME } from "@/theme/constants";

export default createVuetify({
  components,
  directives,

  theme: {
    defaultTheme: LIGHT_THEME_NAME,
    themes: {
      [LIGHT_THEME_NAME]: PurpleTheme,
      [DARK_THEME_NAME]: PurpleThemeDark,
    },
  },
  defaults: {
    VBtn: {},
    VCard: {
      rounded: "lg",
    },
    VTextField: {
      rounded: "lg",
    },
    VTooltip: {
      // set v-tooltip default location to top
      location: "top",
    },
  },
});
