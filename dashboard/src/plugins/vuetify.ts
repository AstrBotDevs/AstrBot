import { createVuetify } from 'vuetify';
import '@mdi/font/css/materialdesignicons.css';
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
    VBtn: {
      elevation: 0,
      variant: 'flat',
      rounded: 'md'
    },
    VCard: {
      elevation: 0,
      rounded: 'lg',
      variant: 'flat'
    },
    VTextField: {
      rounded: 'lg',
      variant: 'outlined',
      density: 'comfortable'
    },
    VSelect: {
      rounded: 'lg',
      variant: 'outlined',
      density: 'comfortable'
    },
    VTextarea: {
      rounded: 'lg',
      variant: 'outlined',
      density: 'comfortable'
    },
    VChip: {
      elevation: 0,
      rounded: 'md',
      variant: 'tonal'
    },
    VDialog: {
      maxWidth: '600px'
    },
    VTooltip: {
      // set v-tooltip default location to top
      location: 'top'
    }
  }
});
