<script setup lang="ts">
import { RouterLink } from "vue-router";
import ConversationPage from "@/views/ConversationPage.vue";
import { useModuleI18n } from "@/i18n/composables";

const { tm } = useModuleI18n("features/conversation");
</script>

<template>
  <div class="legacy-conversation-page">
    <div class="legacy-switch">
      <RouterLink v-slot="{ href, navigate }" custom :to="{ name: 'Conversation' }">
        <v-btn :href="href" size="small" variant="tonal" @click="navigate">
          {{ tm("workspace.newVersion") }}
        </v-btn>
      </RouterLink>
    </div>
    <ConversationPage />
  </div>
</template>

<style scoped>
.legacy-conversation-page {
  padding: 0 12px 24px;
}

.legacy-switch {
  align-items: center;
  display: flex;
  justify-content: flex-end;
  min-height: 42px;
}
</style>
