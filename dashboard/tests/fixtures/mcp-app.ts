import { createApp } from 'vue';
import 'vuetify/styles';
import vuetify from '../../src/plugins/vuetify';
import { initI18n } from '../../src/i18n/composables';
import Fixture from './McpAppFixture.vue';
await initI18n('en-US');
createApp(Fixture).use(vuetify).mount('#app');
