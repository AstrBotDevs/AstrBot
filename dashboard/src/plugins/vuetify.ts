import { createVuetify } from 'vuetify';
import '@/assets/mdi-subset/materialdesignicons-subset.css';
import * as components from 'vuetify/components';
import * as directives from 'vuetify/directives';
import { PurpleTheme } from '@/theme/LightTheme';
import { PurpleThemeDark } from "@/theme/DarkTheme";

export default createVuetify({
  components,
  directives,

  theme: {
    defaultTheme: 'PurpleTheme',
    themes: {
      PurpleTheme,
      PurpleThemeDark
    }
  },
  defaults: {
    VBtn: {},
    VBtnGroup: {
      rounded: 'control'
    },
    VBtnToggle: {
      rounded: 'control'
    },
    VCard: {
      rounded: 'card'
    },
    VSnackbar: {
      elevation: 6,
      rounded: 'lg'
    },
    VTextField: {
      rounded: 'control'
    },
    VTooltip: {
      // set v-tooltip default location to top
      location: 'top'
    }
  }
});
