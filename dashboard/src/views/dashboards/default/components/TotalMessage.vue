<script setup>
 //
</script>

<template>
  <v-card elevation="0" class="bg-secondary overflow-hidden bubble-shape bubble-secondary-shape">
    <v-card-text>
      <div class="d-flex align-start mb-3">
        <v-btn icon rounded="sm" color="darksecondary" variant="flat">
          <v-icon icon="mdi-account-multiple-outline"></v-icon>
        </v-btn>
      </div>
      <v-row>
        <v-col cols="6">
          <h2 class="text-h1 font-weight-medium">
            {{ stat.message_count }}
          </h2>
          <span class="text-subtitle-1 text-medium-emphasis text-white">消息总数</span>
        </v-col>
      </v-row>
    </v-card-text>
  </v-card>

</template>

<script>

export default {
  name: 'TotalMessage',
  props: ['stat'],
  data: () => ({
    stat: {
      message_count: 0
    }
  }),

  mounted() {
  }
};
</script>