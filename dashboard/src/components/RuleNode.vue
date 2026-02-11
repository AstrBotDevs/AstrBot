<template>
  <div class="rule-node" :class="{ 'is-root': isRoot }">
    <!-- Logical Group (AND/OR/NOT) -->
    <div v-if="isGroup" class="group-node">
      <div class="group-header d-flex align-center ga-2 mb-2">
        <v-chip
          :color="groupColor"
          size="small"
          label
        >
          {{ groupLabel }}
        </v-chip>
        <v-btn
          v-if="node.type !== 'not'"
          size="x-small"
          color="primary"
          variant="text"
          icon
          @click="addCondition"
        >
          <v-icon size="small">mdi-plus</v-icon>
          <v-tooltip activator="parent" location="top">{{ tm('addCondition') }}</v-tooltip>
        </v-btn>
        <v-btn
          v-if="node.type !== 'not' && canAddSubGroup"
          size="x-small"
          color="secondary"
          variant="text"
          icon
          @click="addSubGroup"
        >
          <v-icon size="small">mdi-folder-plus</v-icon>
          <v-tooltip activator="parent" location="top">{{ tm('addSubGroup') }}</v-tooltip>
        </v-btn>
        <v-spacer></v-spacer>
        <v-btn
          size="x-small"
          color="error"
          variant="text"
          icon
          @click="$emit('remove')"
        >
          <v-icon size="small">mdi-delete</v-icon>
        </v-btn>
      </div>
      <div class="group-children">
        <RuleNode
          v-for="(child, index) in node.children"
          :key="index"
          :node="child"
          :depth="isRootOrContainer ? 1 : depth + 1"
          :modalities="modalities"
          @update="(val) => updateChild(index, val)"
          @remove="removeChild(index)"
        />
      </div>
    </div>

    <!-- Condition -->
    <div v-else class="condition-node d-flex align-center ga-2 flex-wrap">
      <v-select
        v-model="conditionType"
        :items="conditionTypes"
        item-title="label"
        item-value="value"
        density="compact"
        variant="outlined"
        hide-details
        style="max-width: 140px;"
      ></v-select>

      <v-select
        v-model="conditionOperator"
        :items="operatorOptions"
        item-title="label"
        item-value="value"
        density="compact"
        variant="outlined"
        hide-details
        style="max-width: 100px;"
      ></v-select>

      <!-- UMO: text input -->
      <v-text-field
        v-if="conditionType === 'umo'"
        v-model="conditionValue"
        :placeholder="tm('umoPlaceholder')"
        density="compact"
        variant="outlined"
        hide-details
        style="min-width: 200px; flex: 1;"
      ></v-text-field>

      <!-- Modality: dropdown -->
      <v-select
        v-else-if="conditionType === 'modality'"
        v-model="conditionValue"
        :items="modalityOptions"
        item-title="label"
        item-value="value"
        density="compact"
        variant="outlined"
        hide-details
        style="min-width: 140px; flex: 1;"
      ></v-select>

      <!-- Text Regex: text input -->
      <v-text-field
        v-else-if="conditionType === 'text_regex'"
        v-model="conditionValue"
        :placeholder="tm('regexPlaceholder')"
        density="compact"
        variant="outlined"
        hide-details
        style="min-width: 200px; flex: 1;"
      ></v-text-field>

      <v-btn
        size="x-small"
        color="error"
        variant="text"
        icon
        @click="$emit('remove')"
      >
        <v-icon size="small">mdi-delete</v-icon>
      </v-btn>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useModuleI18n } from '@/i18n/composables'

const { tm } = useModuleI18n('features/chain-management.ruleEditor')

const MAX_DEPTH = 2

const props = defineProps({
  node: {
    type: Object,
    required: true
  },
  isRoot: {
    type: Boolean,
    default: false
  },
  depth: {
    type: Number,
    default: 1
  },
  modalities: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['update', 'remove'])

const isGroup = computed(() => ['and', 'or', 'not'].includes(props.node.type))

// 根级 OR 容器：用于包含多个并行规则组，其子节点仍为 depth=1
const isRootOrContainer = computed(() => props.isRoot && props.node.type === 'or')

const canAddSubGroup = computed(() => props.depth < MAX_DEPTH)

const conditionTypes = computed(() => [
  { label: tm('types.umo'), value: 'umo' },
  { label: tm('types.modality'), value: 'modality' },
  { label: tm('types.textRegex'), value: 'text_regex' }
])

const operatorOptions = computed(() => [
  { label: tm('operators.include'), value: 'include' },
  { label: tm('operators.exclude'), value: 'exclude' }
])

const modalityOptions = computed(() => {
  if (props.modalities && props.modalities.length > 0) {
    return props.modalities
  }
  // fallback
  return [
    { label: 'text', value: 'text' },
    { label: 'image', value: 'image' },
    { label: 'audio', value: 'audio' },
    { label: 'video', value: 'video' },
    { label: 'file', value: 'file' }
  ]
})

const groupLabel = computed(() => {
  switch (props.node.type) {
    case 'and': return 'AND'
    case 'or': return 'OR'
    case 'not': return 'NOT'
    default: return props.node.type.toUpperCase()
  }
})

const groupColor = computed(() => {
  switch (props.node.type) {
    case 'and': return 'primary'
    case 'or': return 'success'
    case 'not': return 'warning'
    default: return 'grey'
  }
})

const conditionType = computed({
  get: () => props.node.condition?.type || 'umo',
  set: (val) => {
    const defaultModalityValue = modalityOptions.value[0]?.value || 'text'
    const newNode = {
      ...props.node,
      condition: {
        type: val,
        operator: props.node.condition?.operator || 'include',
        value: val === 'modality' ? defaultModalityValue : (val === 'umo' ? '*' : '.*')
      }
    }
    emit('update', newNode)
  }
})

const conditionOperator = computed({
  get: () => props.node.condition?.operator || 'include',
  set: (val) => {
    const newNode = {
      ...props.node,
      condition: {
        ...props.node.condition,
        operator: val
      }
    }
    emit('update', newNode)
  }
})

const conditionValue = computed({
  get: () => props.node.condition?.value || '',
  set: (val) => {
    const newNode = {
      ...props.node,
      condition: {
        ...props.node.condition,
        value: val
      }
    }
    emit('update', newNode)
  }
})

function updateChild(index, newVal) {
  const newChildren = [...props.node.children]
  newChildren[index] = newVal
  emit('update', { ...props.node, children: newChildren })
}

function removeChild(index) {
  const newChildren = props.node.children.filter((_, i) => i !== index)
  if (newChildren.length === 0) {
    emit('remove')
  } else if (newChildren.length === 1 && props.node.type !== 'not') {
    // Collapse single-child group
    emit('update', newChildren[0])
  } else {
    emit('update', { ...props.node, children: newChildren })
  }
}

function addCondition() {
  const newChildren = [
    ...props.node.children,
    { type: 'condition', condition: { type: 'umo', operator: 'include', value: '*' } }
  ]
  emit('update', { ...props.node, children: newChildren })
}

function addSubGroup() {
  if (!canAddSubGroup.value) return
  const newChildren = [
    ...props.node.children,
    { type: 'and', children: [{ type: 'condition', condition: { type: 'umo', operator: 'include', value: '*' } }] }
  ]
  emit('update', { ...props.node, children: newChildren })
}

</script>

<style scoped>
.rule-node {
  margin-bottom: 8px;
}

.rule-node:last-child {
  margin-bottom: 0;
}

.group-node {
  padding: 12px;
  border: 1px solid rgba(0, 0, 0, 0.12);
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.02);
}

.group-children {
  padding-left: 16px;
  border-left: 2px solid rgba(0, 0, 0, 0.08);
  margin-left: 8px;
}

.condition-node {
  padding: 8px 12px;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 6px;
  background: white;
}

.is-root > .group-node {
  border-color: rgba(var(--v-theme-primary), 0.3);
}
</style>
