<template>
  <div class="list-config-item">
    <div class="d-flex align-center justify-space-between ga-2">
      <div v-if="isSingleItemMode" class="flex-grow-1 d-flex align-center ga-2">
        <v-text-field
          v-model="singleItemValue"
          :type="secretInputType"
          :append-inner-icon="secretToggleIcon"
          :autocomplete="secret ? 'new-password' : undefined"
          hide-details
          variant="outlined"
          density="compact"
          class="flex-grow-1"
          @click:append-inner="secretVisible = !secretVisible"
        ></v-text-field>
      </div>
      <div v-else>
        <span
          v-if="!modelValue || modelValue.length === 0"
          class="selector-empty-label"
        >
          {{ t('core.common.list.noItems') }}
        </span>
        <div v-else class="d-flex flex-wrap ga-2">
          <v-chip
            v-for="item in displayItems"
            :key="item"
            size="x-small"
            label
            color="primary"
          >
            {{
              secret && !secretVisible
                ? '••••••••'
                : item.length > 20
                  ? item.slice(0, 20) + '...'
                  : item
            }}
          </v-chip>
          <v-chip
            v-if="modelValue.length > maxDisplayItems"
            size="x-small"
            label
            color="secondary"
          >
            +{{ modelValue.length - maxDisplayItems }}
          </v-chip>
        </div>
      </div>
      <v-btn size="small" color="primary" variant="tonal" @click="openDialog">
        {{
          preferSingleItem
            ? t('core.common.list.addMore')
            : buttonText || t('core.common.list.modifyButton')
        }}
      </v-btn>
    </div>

    <!-- List Management Dialog -->
    <v-dialog v-model="dialog" max-width="600px" scrollable>
      <v-card class="app-dialog list-config-dialog__card">
        <v-card-title class="app-dialog__title">
          {{ dialogTitle || t('core.common.list.editTitle') }}
        </v-card-title>

        <!-- Add new item section - moved to top -->
        <v-card-text class="pa-4 pb-2">
          <div class="d-flex align-center ga-2">
            <v-text-field
              v-model="newItem"
              :type="secretInputType"
              :append-inner-icon="secretToggleIcon"
              :autocomplete="secret ? 'new-password' : undefined"
              :label="t('core.common.list.addItemPlaceholder')"
              clearable
              hide-details
              variant="outlined"
              density="compact"
              :placeholder="t('core.common.list.inputPlaceholder')"
              class="flex-grow-1"
              @click:append-inner="secretVisible = !secretVisible"
              @keyup.enter="addItem"
            >
            </v-text-field>
            <v-btn
              variant="tonal"
              color="primary"
              size="small"
              :disabled="!newItem.trim()"
              @click="addItem"
            >
              {{ t('core.common.list.addButton') }}
            </v-btn>
            <v-btn
              variant="tonal"
              color="primary"
              size="small"
              @click="showBatchImport = true"
            >
              <v-icon size="small">mdi-import</v-icon>
              {{ t('core.common.list.batchImport') }}
            </v-btn>
          </div>
        </v-card-text>

        <v-card-text class="pa-0 list-config-dialog__content">
          <v-list v-if="localItems.length > 0" density="compact">
            <v-list-item
              v-for="(item, index) in localItems"
              :key="index"
              rounded="md"
              class="ma-1 list-item-clickable"
              @click="startEdit(index, item)"
            >
              <v-list-item-title v-if="editIndex !== index" class="item-text">
                {{ secret && !secretVisible ? '••••••••' : item }}
              </v-list-item-title>
              <v-text-field
                v-else
                v-model="editItem"
                :type="secretInputType"
                :append-inner-icon="secretToggleIcon"
                :autocomplete="secret ? 'new-password' : undefined"
                hide-details
                variant="outlined"
                density="compact"
                autofocus
                @click:append-inner="secretVisible = !secretVisible"
                @keyup.enter="saveEdit"
                @keyup.esc="cancelEdit"
                @click.stop
              ></v-text-field>

              <template #append>
                <div class="d-flex">
                  <v-btn
                    v-if="editIndex === index"
                    variant="plain"
                    color="success"
                    icon
                    size="small"
                    @click.stop="saveEdit"
                  >
                    <v-icon>mdi-check</v-icon>
                  </v-btn>
                  <v-btn
                    variant="plain"
                    :color="editIndex === index ? 'error' : 'default'"
                    icon
                    size="small"
                    @click.stop="
                      editIndex === index ? cancelEdit() : removeItem(index)
                    "
                  >
                    <v-icon>mdi-close</v-icon>
                  </v-btn>
                </div>
              </template>
            </v-list-item>
          </v-list>

          <div v-else class="text-center py-8">
            <v-icon size="64" color="secondary"
              >mdi-format-list-bulleted</v-icon
            >
            <p class="text-medium-emphasis mt-4">
              {{ t('core.common.list.noItemsHint') }}
            </p>
          </div>
        </v-card-text>

        <v-card-actions class="pa-4 list-config-dialog__actions">
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="cancelDialog">{{
            t('core.common.cancel')
          }}</v-btn>
          <v-btn color="primary" @click="confirmDialog">{{
            t('core.common.confirm')
          }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Batch Import Dialog -->
    <v-dialog v-model="showBatchImport" max-width="600px" scrollable>
      <v-card class="app-dialog list-config-dialog__card">
        <v-card-title class="app-dialog__title">
          {{ t('core.common.list.batchImportTitle') }}
        </v-card-title>

        <v-card-text class="list-config-dialog__content">
          <v-textarea
            v-model="batchImportText"
            :class="{ 'secret-textarea': secret && !secretVisible }"
            :append-inner-icon="secretToggleIcon"
            :autocomplete="secret ? 'new-password' : undefined"
            :label="t('core.common.list.batchImportLabel')"
            :placeholder="t('core.common.list.batchImportPlaceholder')"
            rows="10"
            variant="outlined"
            :hint="t('core.common.list.batchImportHint')"
            persistent-hint
            @click:append-inner="secretVisible = !secretVisible"
          ></v-textarea>
        </v-card-text>

        <v-card-actions class="pa-4 list-config-dialog__actions">
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="cancelBatchImport">{{
            t('core.common.cancel')
          }}</v-btn>
          <v-btn color="primary" @click="confirmBatchImport">
            {{
              t('core.common.list.batchImportButton', {
                count: batchImportPreviewCount,
              })
            }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue';
import { useI18n } from '@/i18n/composables';

const { t } = useI18n();

const props = defineProps({
  modelValue: {
    type: Array,
    default: () => [],
  },
  label: {
    type: String,
    default: '',
  },
  buttonText: {
    type: String,
    default: '',
  },
  dialogTitle: {
    type: String,
    default: '',
  },
  maxDisplayItems: {
    type: Number,
    default: 1,
  },
  preferSingleItem: {
    type: Boolean,
    default: true,
  },
  secret: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(['update:modelValue']);

const dialog = ref(false);
const localItems = ref([]);
const originalItems = ref([]);
const newItem = ref('');
const editIndex = ref(-1);
const editItem = ref('');
const showBatchImport = ref(false);
const batchImportText = ref('');
const secretVisible = ref(false);
const secretInputType = computed(() =>
  props.secret && !secretVisible.value ? 'password' : 'text',
);
const secretToggleIcon = computed(() => {
  if (!props.secret) return undefined;
  return secretVisible.value ? 'mdi-eye-off' : 'mdi-eye';
});
const isSingleItemMode = computed(
  () => (props.modelValue?.length ?? 0) <= 1 && props.preferSingleItem,
);
const singleItemValue = computed({
  get: () => props.modelValue?.[0] ?? '',
  set: (value) => {
    // 仅当值为完全空字符串（未输入任何字符）时清空数组，
    // 允许包含空格（如 "hello world"）以及纯空格（如 " "）通过
    if (value === '') {
      emit('update:modelValue', []);
      return;
    }

    const newItems = [...(props.modelValue || [])];
    if (newItems.length === 0) {
      newItems.push(value);
    } else {
      newItems[0] = value;
    }

    emit('update:modelValue', newItems);
  },
});

// 计算要显示的项目
const displayItems = computed(() => {
  return props.modelValue.slice(0, props.maxDisplayItems);
});

// 计算批量导入的项目数量
const batchImportPreviewCount = computed(() => {
  if (!batchImportText.value) return 0;
  return batchImportText.value
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0).length;
});

// 监听 modelValue 变化，同步到 localItems，并清理空字符串
watch(
  () => props.modelValue,
  (newValue) => {
    localItems.value = [...(newValue || [])];

    // 自动清理只包含空字符串或纯空格的条目（纯空格在配置中无意义，此过滤为预期兜底行为）
    if (newValue && newValue.length > 0) {
      const filtered = newValue.filter((item) =>
        typeof item === 'string' ? item.trim() !== '' : true,
      );
      if (filtered.length !== newValue.length) {
        // 使用 nextTick 确保父组件已准备好接收更新
        void nextTick(() => {
          emit('update:modelValue', filtered);
        });
      }
    }
  },
  { immediate: true },
);

function openDialog() {
  localItems.value = [...(props.modelValue || [])];
  originalItems.value = [...(props.modelValue || [])];
  dialog.value = true;
  editIndex.value = -1;
  editItem.value = '';
  newItem.value = '';
}

function addItem() {
  if (newItem.value.trim() !== '') {
    localItems.value.push(newItem.value.trim());
    newItem.value = '';
  }
}

function removeItem(index) {
  localItems.value.splice(index, 1);
}

function startEdit(index, item) {
  editIndex.value = index;
  editItem.value = item;
}

function saveEdit() {
  if (editItem.value.trim() !== '') {
    localItems.value[editIndex.value] = editItem.value.trim();
    cancelEdit();
  }
}

function cancelEdit() {
  editIndex.value = -1;
  editItem.value = '';
}

function confirmDialog() {
  // 过滤空字符串，同时处理非字符串类型
  const filteredItems = localItems.value.filter((item) =>
    typeof item === 'string' ? item.trim() !== '' : true,
  );
  emit('update:modelValue', filteredItems);
  dialog.value = false;
}

function cancelDialog() {
  localItems.value = [...originalItems.value];
  editIndex.value = -1;
  editItem.value = '';
  newItem.value = '';
  dialog.value = false;
}

function confirmBatchImport() {
  if (batchImportText.value.trim()) {
    const newItems = batchImportText.value
      .split('\n')
      .map((line) => line.trim())
      .filter((line) => line.length > 0);

    localItems.value.push(...newItems);
    batchImportText.value = '';
    showBatchImport.value = false;
  }
}

function cancelBatchImport() {
  batchImportText.value = '';
  showBatchImport.value = false;
}
</script>

<style scoped>
.list-config-item {
  width: 100%;
}

.v-list-item {
  transition: all 0.2s ease;
}

.list-item-clickable {
  cursor: pointer;
}

.list-item-clickable:hover {
  background-color: rgba(var(--v-theme-primary), 0.08);
}

.item-text {
  user-select: none;
}

.v-chip {
  margin: 2px;
}

.secret-textarea :deep(textarea) {
  -webkit-text-security: disc;
}

.list-config-dialog__card {
  display: flex;
  flex-direction: column;
  max-height: min(88dvh, 760px);
}

.list-config-dialog__content {
  flex: 1 1 auto;
  min-height: 0;
  max-height: min(60dvh, 520px);
  overflow-y: auto;
  overscroll-behavior: contain;
}

.list-config-dialog__actions {
  flex-shrink: 0;
}
</style>
