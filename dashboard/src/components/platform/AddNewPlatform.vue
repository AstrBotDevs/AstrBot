<template>
  <v-dialog v-model="showDialog" max-width="900px" min-height="80%">
    <v-card class="platform-selection-dialog" :title="tm('dialog.addPlatform')">
      <v-card-text class="pa-4" style="overflow-y: auto;">
        <v-row style="padding: 0px 8px;">
          <v-col v-for="(template, name) in platformTemplates"
            :key="name" cols="12" sm="6" md="6">
            <v-card variant="outlined" hover class="platform-card" @click="selectTemplate(name)">
              <div class="platform-card-content">
                <div class="platform-card-text">
                  <v-card-title class="platform-card-title">{{ tm('dialog.connectTitle', { name }) }}</v-card-title>
                  <v-card-text class="text-caption text-medium-emphasis platform-card-description">
                    {{ getPlatformDescription(template, name) }}
                  </v-card-text>
                </div>
                <div class="platform-card-logo">
                  <img :src="getPlatformIcon(template.type)" v-if="getPlatformIcon(template.type)" class="platform-logo-img">
                  <div v-else class="platform-logo-fallback">
                    {{ name[0].toUpperCase() }}
                  </div>
                </div>
              </div>
            </v-card>
          </v-col>
          <v-col
            v-if="Object.keys(platformTemplates).length === 0"
            cols="12">
            <v-alert type="info" variant="tonal">
              {{ tm('dialog.noTemplates') }}
            </v-alert>
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script>
import { useModuleI18n } from '@/i18n/composables';
import { getPlatformIcon, getPlatformDescription } from '@/utils/platformUtils';

export default {
  name: 'AddNewPlatform',
  emits: ['update:show', 'select-template'],
  props: {
    show: {
      type: Boolean,
      default: false
    },
    metadata: {
      type: Object,
      default: () => ({})
    }
  },
  setup() {
    const { tm } = useModuleI18n('features/platform');
    return { tm };
  },
  computed: {
    showDialog: {
      get() {
        return this.show;
      },
      set(value) {
        this.$emit('update:show', value);
      }
    },
    platformTemplates() {
      return this.metadata['platform_group']?.metadata?.platform?.config_template || {};
    }
  },
  methods: {
    // 从工具函数导入
    getPlatformIcon,
    getPlatformDescription,

    selectTemplate(name) {
      this.$emit('select-template', name);
      this.closeDialog();
    },

    closeDialog() {
      this.showDialog = false;
    }
  }
}
</script>

<style scoped>
.platform-selection-dialog .v-card-title {
  border-top-left-radius: 4px;
  border-top-right-radius: 4px;
}

.platform-card {
  transition: all 0.3s ease;
  height: 100%;
  cursor: pointer;
  overflow: hidden;
  position: relative;
}

.platform-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 4px 25px 0 rgba(0, 0, 0, 0.05);
  border-color: var(--v-primary-base);
}

.platform-card-content {
  display: flex;
  align-items: center;
  height: 100px;
  padding: 16px;
  position: relative;
  z-index: 2;
}

.platform-card-text {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.platform-card-title {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 4px;
  padding: 0;
}

.platform-card-description {
  padding: 0;
  margin: 0;
}

.platform-card-logo {
  position: absolute;
  right: 0;
  top: 0;
  bottom: 0;
  width: 80px;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1;
}

.platform-logo-img {
  max-width: 60px;
  max-height: 60px;
  opacity: 0.6;
  object-fit: contain;
}

.platform-logo-fallback {
  width: 50px;
  height: 50px;
  border-radius: 50%;
  background-color: var(--v-primary-base);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  font-weight: bold;
  opacity: 0.3;
}
</style>
