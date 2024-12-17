<script setup lang="ts"></script>

<template>
  <v-card elevation="0" class="bg-primary overflow-hidden bubble-shape-sm bubble-primary mb-6">
    <v-card-text class="pa-5">
      <div class="d-flex align-center gap-3">
        <v-btn color="darkprimary" icon rounded="sm" variant="flat">
          <v-icon icon="mdi-clock"></v-icon>
        </v-btn>
        <div>
          <h4 class="text-h4 font-weight-medium">{{ stat.running }}</h4>
          <span class="text-subtitle-2 text-medium-emphasis text-white">运行时间</span>
        </div>
        <v-spacer></v-spacer>
        <div>
          <v-btn icon rounded="sm" variant="plain">
            <v-icon color="black" icon="mdi-stop" size="32"></v-icon>
          </v-btn>
        </div>
      </div>
    </v-card-text>
  </v-card>

  <v-card elevation="0" class="bubble-shape-sm overflow-hidden bubble-warning">
    <v-card-text class="pa-5">
      <div class="d-flex align-center gap-3">
        <v-btn color="lightwarning" icon rounded="sm" variant="flat">
          <v-icon icon="mdi-memory"></v-icon>
        </v-btn>
        <div>
          <h4 class="text-h4 font-weight-medium">{{ stat.memory?.process }} / {{ stat.memory?.system }} MiB</h4>

          <span class="text-subtitle-2 text-disabled font-weight-medium">占用内存</span>
        </div>
      </div>
    </v-card-text>
  </v-card>
</template>


<script>

export default {
  name: 'OnlineTime',
  components: {
  },
  props: ['stat'],
  watch: {
  },
  data: () => ({
    stat: {
      memory: "Loading",
      running: "Loading",
    },
  }),

  mounted() {
  }
};

</script>