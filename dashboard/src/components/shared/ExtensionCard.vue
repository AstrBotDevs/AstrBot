<script setup lang="ts">
const props = defineProps({
  title: String,
  link: String,
  logo: String
});

const open = (link: string | undefined) => {
  window.open(link, '_blank');
};
</script>

<template>
  <v-card variant="outlined" elevation="0" class="withbg">
    <v-card-item style="padding: 10px 14px">
      <div class="d-sm-flex align-center justify-space-between">
        <img v-if="logo" :src="logo" alt="logo" style="width: 40px; height: 40px; margin-right: 8px;">
        <v-card-title style="font-size: 17px;">{{ props.title }}</v-card-title>
        <v-spacer></v-spacer>
        <v-btn variant="plain" @click="open(props.link)">仓库</v-btn>
      </div>
    </v-card-item>
    <v-divider></v-divider>
    <v-card-text>
      <slot />
    </v-card-text>
  </v-card>
</template>
