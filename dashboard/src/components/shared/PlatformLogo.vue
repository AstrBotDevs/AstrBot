<template>
  <img
    v-if="icon && failedIcon !== icon"
    :src="icon"
    alt=""
    class="platform-logo"
    @error="failedIcon = icon"
  />
</template>

<script setup>
import { computed, ref } from "vue";
import { getPlatformIcon } from "@/utils/platformUtils";

const props = defineProps({
  platformType: { type: String, default: "" },
});
const icon = computed(() => getPlatformIcon(props.platformType));
const failedIcon = ref("");
</script>

<style scoped>
.platform-logo {
  width: 16px;
  height: 16px;
  flex: 0 0 auto;
  object-fit: contain;
}
</style>
