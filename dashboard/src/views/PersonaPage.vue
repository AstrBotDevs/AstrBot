<template>
  <div class="persona-page">
    <v-container fluid class="pa-0">
      <PersonaManager />
    </v-container>
  </div>
</template>

<script>
import { PersonaManager } from "@/views/persona";

export default {
  name: "PersonaPage",
  components: {
    PersonaManager,
  },
};
</script>

<style scoped>
.persona-page {
  margin: 0 auto;
  max-width: 1200px;
  padding: 24px;
  width: 100%;
}

@media (max-width: 768px) {
  .persona-page {
    padding: 16px;
  }
}
</style>
