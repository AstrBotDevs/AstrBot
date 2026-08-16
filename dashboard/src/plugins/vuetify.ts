import { createVuetify } from 'vuetify';
import 'vuetify/styles';
import '@/assets/mdi-subset/materialdesignicons-subset.css';
import * as components from 'vuetify/components';
import * as directives from 'vuetify/directives';
import { astrBotThemes, themeNames } from '@/design/theme';

export default createVuetify({
  components,
  directives,

  theme: {
    defaultTheme: themeNames.light,
    themes: astrBotThemes,
  },
  defaults: {
    VBtn: {
      rounded: 'md',
    },
    VCard: {
      elevation: 0,
      rounded: 'md',
      variant: 'outlined',
    },
    VSnackbar: {
      elevation: 4,
      rounded: 'md',
    },
    VTextField: {
      density: 'compact',
      rounded: 'md',
      variant: 'outlined',
    },
    VSelect: {
      density: 'compact',
      rounded: 'md',
      variant: 'outlined',
    },
    VTextarea: {
      density: 'compact',
      rounded: 'md',
      variant: 'outlined',
    },
    VListItem: {
      density: 'compact',
      rounded: 'sm',
    },
    VTooltip: {
      location: 'top',
    },
  },
});
