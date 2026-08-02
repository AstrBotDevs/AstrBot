<script setup>
defineProps({
  label: {
    type: String,
    required: true,
  },
  tone: {
    type: String,
    required: true,
  },
});
</script>

<template>
  <v-chip
    size="x-small"
    variant="flat"
    :class="['capability-source-chip', `capability-source-chip--${tone}`]"
    :title="label"
  >
    {{ label }}
  </v-chip>
</template>

<style scoped>
.capability-source-chip {
  margin: 0;
}

.capability-source-chip--plugin {
  border: 1px solid rgba(21, 101, 192, 0.35) !important;
  background-color: rgba(33, 150, 243, 0.22) !important;
  color: #0d47a1 !important;
}

.capability-source-chip--mcp {
  border: 1px solid rgba(230, 81, 0, 0.35) !important;
  background-color: rgba(255, 112, 67, 0.22) !important;
  color: #bf360c !important;
}

.capability-source-chip--local {
  border: 1px solid rgba(46, 125, 50, 0.35) !important;
  background-color: rgba(76, 175, 80, 0.2) !important;
  color: #1b5e20 !important;
}

.capability-source-chip--preset {
  border: 1px solid rgba(106, 27, 154, 0.35) !important;
  background-color: rgba(156, 39, 176, 0.2) !important;
  color: #6a1b9a !important;
}

.capability-source-chip--mixed {
  border: 1px solid rgba(0, 105, 92, 0.35) !important;
  background-color: rgba(0, 150, 136, 0.2) !important;
  color: #00695c !important;
}

:global(.v-theme--dark) .capability-source-chip--plugin {
  color: #64b5f6 !important;
}

:global(.v-theme--dark) .capability-source-chip--mcp {
  color: #ffab91 !important;
}

:global(.v-theme--dark) .capability-source-chip--local {
  color: #a5d6a7 !important;
}

:global(.v-theme--dark) .capability-source-chip--preset {
  color: #ce93d8 !important;
}

:global(.v-theme--dark) .capability-source-chip--mixed {
  color: #80cbc4 !important;
}
</style>
