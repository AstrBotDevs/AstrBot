<template>
  <div class="rule-editor">
    <div class="d-flex align-center justify-space-between mb-3">
      <span class="text-subtitle-2">{{ tm('label') }}</span>
      <v-btn
        size="small"
        color="primary"
        variant="tonal"
        @click="addRootGroup"
      >
        <v-icon start>mdi-plus</v-icon>
        {{ tm('addGroup') }}
      </v-btn>
    </div>

    <div v-if="!rule" class="text-center py-4 text-grey">
      {{ tm('empty') }}
    </div>

    <RuleNode
      v-else
      :node="rule"
      :is-root="true"
      :depth="1"
      :modalities="modalities"
      @update="updateRule"
      @remove="removeRule"
    />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useModuleI18n } from '@/i18n/composables'
import RuleNode from './RuleNode.vue'

const { tm } = useModuleI18n('features/chain-management.ruleEditor')

const props = defineProps({
  modelValue: {
    type: Object,
    default: null
  },
  modalities: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['update:modelValue'])

const rule = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

function addRootGroup() {
  const newGroup = {
    type: 'and',
    children: [
      { type: 'condition', condition: { type: 'umo', operator: 'include', value: '*' } }
    ]
  }

  if (!rule.value) {
    // 没有规则，创建新的根规则组
    rule.value = newGroup
  } else if (rule.value.type === 'or') {
    // 已经是 OR 根节点，添加新的并行规则组
    rule.value = {
      ...rule.value,
      children: [...rule.value.children, newGroup]
    }
  } else {
    // 将现有规则和新规则包装在 OR 组中（并行）
    rule.value = {
      type: 'or',
      children: [rule.value, newGroup]
    }
  }
}

function updateRule(newVal) {
  rule.value = newVal
}

function removeRule() {
  rule.value = null
}
</script>

<style scoped>
.rule-editor {
  padding: 12px;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.01);
}
</style>
