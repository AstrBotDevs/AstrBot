<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from "vue";
import { fetchWithAuth } from "@/api/http";

const props = defineProps<{
  src: string;
  alt?: string;
  imageClass?: string;
  loadingText?: string;
  unavailableText?: string;
}>();
const emit = defineEmits<{ click: [url: string] }>();
const objectUrl = ref("");
const loading = ref(false);
let controller: AbortController | null = null;

function revoke() {
  if (objectUrl.value) URL.revokeObjectURL(objectUrl.value);
  objectUrl.value = "";
}

async function load(src: string) {
  controller?.abort();
  const requestController = new AbortController();
  controller = requestController;
  revoke();
  if (!src) return;
  loading.value = true;
  try {
    const response = await fetchWithAuth(src, {
      signal: requestController.signal,
    });
    if (!response.ok)
      throw new Error(`media request failed: ${response.status}`);
    const blob = await response.blob();
    if (requestController.signal.aborted || controller !== requestController) {
      return;
    }
    objectUrl.value = URL.createObjectURL(blob);
  } catch (error) {
    if (
      (error as DOMException)?.name !== "AbortError" &&
      controller === requestController
    ) {
      objectUrl.value = "";
    }
  } finally {
    if (controller === requestController) loading.value = false;
  }
}

watch(() => props.src, load, { immediate: true });
onBeforeUnmount(() => {
  controller?.abort();
  revoke();
});
</script>

<template>
  <img
    v-if="objectUrl"
    :src="objectUrl"
    :alt="alt"
    :class="imageClass"
    loading="lazy"
    @click.stop="emit('click', objectUrl)"
  />
  <span v-else-if="loading" class="media-loading" :aria-label="loadingText" />
  <span v-else class="media-unavailable">{{ unavailableText }}</span>
</template>
