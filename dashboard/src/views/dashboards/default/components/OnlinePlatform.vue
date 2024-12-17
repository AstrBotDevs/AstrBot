<script setup>
 //
</script>

<template>
  <v-card elevation="0" class="bg-primary overflow-hidden bubble-shape bubble-primary-shape">
    <v-card-text>
      <div class="d-flex align-start mb-3">
        <v-btn icon rounded="sm" color="darkprimary" variant="flat">
          <v-icon icon="mdi-account-multiple-outline"></v-icon>
        </v-btn>
      </div>
      <v-row>
        <v-col cols="6">
          <h2 class="text-h1 font-weight-medium">
            {{ stat.platform_count }}
          </h2>
          <span class="text-subtitle-1 text-medium-emphasis text-white">消息平台数</span>
        </v-col>
      </v-row>
    </v-card-text>
  </v-card>
</template>


<script>

export default {
  name: 'TotalSession',
  props: ['stat'],
  data: () => ({
    stat: {
      platform_count: 0
    }
  }),
};
</script>