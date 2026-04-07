import { createVuetify } from "vuetify";
// MDI font loaded in index.html via CDN
import * as components from "vuetify/components";
import * as directives from "vuetify/directives";
import { BlueBusinessLightTheme } from "@/theme/BlueBusinessLightTheme";
import { BlueBusinessDarkTheme } from "@/theme/BlueBusinessDarkTheme";
import { LIGHT_THEME_NAME, DARK_THEME_NAME } from "@/theme/constants";

export default createVuetify({
  components,
  directives,

  theme: {
    defaultTheme: LIGHT_THEME_NAME,
    themes: {
      [LIGHT_THEME_NAME]: BlueBusinessLightTheme,
      [DARK_THEME_NAME]: BlueBusinessDarkTheme,
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
