<template>
  <v-menu
    v-model="menuOpen"
    location="bottom start"
    :close-on-content-click="false"
    offset="8"
  >
    <template #activator="{ props: activatorProps }">
      <v-btn
        v-bind="activatorProps"
        class="emoji-picker-trigger"
        variant="tonal"
        size="large"
        :aria-label="tm('emoji.title')"
      >
        <span aria-hidden="true">{{ modelValue || '📚' }}</span>
        <v-icon size="16" class="ms-1">mdi-chevron-down</v-icon>
      </v-btn>
    </template>

    <v-card class="emoji-picker-menu" min-width="300" max-width="340">
      <v-card-title class="text-body-1 pa-3">{{ tm('emoji.title') }}</v-card-title>
      <v-tabs v-model="activeCategory" density="compact" grow color="primary">
        <v-tab
          v-for="category in emojiCategories"
          :key="category.key"
          :value="category.key"
          :aria-label="tm(`emoji.categories.${category.key}`)"
        >
          <span aria-hidden="true">{{ category.icon }}</span>
        </v-tab>
      </v-tabs>
      <v-divider />
      <v-card-text class="pa-2">
        <div class="emoji-grid">
          <v-btn
            v-for="emoji in activeEmojis"
            :key="emoji"
            class="emoji-option"
            variant="text"
            size="36"
            :aria-label="emoji"
            @click="selectEmoji(emoji)"
          >
            {{ emoji }}
          </v-btn>
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
  min-width: 56px;
  padding-inline: 10px;
  font-size: 24px;
}

.emoji-picker-menu {
  overflow: hidden;
}

.emoji-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 2px;
}

.emoji-option {
  min-width: 0;
  padding: 0;
  font-size: 22px;
}
</style>
