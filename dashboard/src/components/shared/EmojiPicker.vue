<template>
  <v-menu
    v-model="menuOpen"
    location="bottom start"
    :close-on-content-click="false"
    offset="8"
  >
    <template #activator="{ props: activatorProps }">
      <button
        v-bind="activatorProps"
        type="button"
        class="emoji-picker-trigger"
        :aria-label="tm('emoji.title')"
      >
        <span aria-hidden="true">{{ modelValue || '📚' }}</span>
      </button>
    </template>

    <v-card class="emoji-picker-menu" min-width="300" max-width="340">
      <v-card-title class="text-body-1 pa-3">{{ tm('emoji.title') }}</v-card-title>
      <div class="emoji-category-tabs">
        <button
          v-for="category in emojiCategories"
          :key="category.key"
          type="button"
          class="emoji-category-tab"
          :class="{ 'is-active': activeCategory === category.key }"
          :aria-label="tm(`emoji.categories.${category.key}`)"
          @click="activeCategory = category.key"
        >
          <span aria-hidden="true">{{ category.icon }}</span>
        </button>
      </div>
      <v-divider />
      <v-card-text class="pa-2">
        <div class="emoji-grid">
          <button
            v-for="emoji in activeEmojis"
            :key="emoji"
            type="button"
            class="emoji-option"
            :aria-label="emoji"
            @click="selectEmoji(emoji)"
          >
            {{ emoji }}
          </button>
        </div>
      </v-card-text>
    </v-card>
  </v-menu>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useModuleI18n } from '@/i18n/composables'

defineProps<{
  modelValue: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const { tm } = useModuleI18n('features/knowledge-base/index')
const menuOpen = ref(false)
const activeCategory = ref('books')

const emojiCategories = [
  {
    key: 'books',
    icon: '📚',
    emojis: ['📚', '📖', '📕', '📗', '📘', '📙', '📓', '📔', '📒', '📑', '🗂️', '📂', '📁', '🗃️', '🗄️']
  },
  {
    key: 'emotions',
    icon: '🙂',
    emojis: ['😀', '😃', '😄', '😁', '😆', '😅', '🤣', '😂', '🙂', '🙃', '😉', '😊', '😇', '🥰', '😍']
  },
  {
    key: 'objects',
    icon: '💡',
    emojis: ['💡', '🔬', '🔭', '🗿', '🏆', '🎯', '🎓', '🔑', '🔒', '🔓', '🔔', '🔕', '🔨', '🛠️', '⚙️']
  },
  {
    key: 'symbols',
    icon: '⭐',
    emojis: ['❤️', '🧡', '💛', '💚', '💙', '💜', '🖤', '🤍', '🤎', '⭐', '🌟', '✨', '💫', '⚡', '🔥']
  }
]

const activeEmojis = computed(() =>
  emojiCategories.find((category) => category.key === activeCategory.value)?.emojis || []
)

function selectEmoji(emoji: string) {
  emit('update:modelValue', emoji)
  menuOpen.value = false
}
</script>

<style scoped>
.emoji-picker-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 56px;
  height: 48px;
  padding: 0 10px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font-size: 24px;
}

.emoji-picker-trigger:hover {
  background: rgba(var(--v-theme-on-surface), 0.06);
}

.emoji-picker-menu {
  overflow: hidden;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.13);
  border-radius: 16px;
}

.emoji-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 2px;
}

.emoji-category-tabs {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 2px;
  padding: 0 8px 8px;
}

.emoji-category-tab {
  height: 32px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  cursor: pointer;
  font-size: 18px;
}

.emoji-category-tab:hover,
.emoji-category-tab.is-active {
  background: rgba(var(--v-theme-primary), 0.12);
}

.emoji-option {
  min-width: 0;
  padding: 0;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font-size: 22px;
  line-height: 36px;
}

.emoji-option:hover {
  background: rgba(var(--v-theme-primary), 0.12);
}
</style>
