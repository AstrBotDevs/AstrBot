<template>
  <div
    class="pdf-page"
    :style="{ width: `${width}px`, height: `${height}px` }"
    role="img"
    :aria-label="tm('workspaceFiles.pdf.pageLabel', { page, total })"
  >
    <div v-if="error" class="pdf-placeholder pdf-error" role="alert">
      {{ error }}
    </div>
    <div v-else-if="!rendered" class="pdf-placeholder" aria-hidden="true">
      <v-progress-circular v-if="visible" indeterminate size="22" width="2" />
      <span>{{ page }}</span>
    </div>
    <div ref="pageHost" class="pdf-canvas" />
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { PDFDocumentProxy, RenderTask } from "pdfjs-dist";
import { useModuleI18n } from "@/i18n/composables";

const props = defineProps<{
  document: PDFDocumentProxy;
  page: number;
  total: number;
  width: number;
  height: number;
  scrollRoot: HTMLElement | null;
}>();
const { tm } = useModuleI18n("features/chat");
const pageHost = ref<HTMLElement | null>(null);
const visible = ref(false);
const rendered = ref(false);
const error = ref("");
let observer: IntersectionObserver | undefined;
onMounted(() => {
  observer = new IntersectionObserver(
    ([entry]) => {
      visible.value = entry.isIntersecting;
    },
    {
      root: props.scrollRoot,
      rootMargin: "600px 0px",
    },
  );
  if (pageHost.value) observer.observe(pageHost.value);
});
onBeforeUnmount(() => observer?.disconnect());

watch(
  [visible, () => props.document, () => props.width, () => props.page],
  async ([nearViewport, document, width, pageNumber], _, onCleanup) => {
    let cancelled = false;
    let task: RenderTask | undefined;
    let canvas: HTMLCanvasElement | undefined;
    onCleanup(() => {
      cancelled = true;
      task?.cancel();
      canvas?.remove();
      // Release the raster buffer when a page leaves the nearby viewport.
      if (canvas) canvas.width = canvas.height = 0;
    });
    rendered.value = false;
    error.value = "";
    if (!nearViewport || width <= 0) return;
    try {
      const page = await document.getPage(pageNumber);
      if (cancelled) return;
      const original = page.getViewport({ scale: 1 });
      const view = page.getViewport({ scale: width / original.width });
      const ratio = Math.min(
        window.devicePixelRatio || 1,
        2,
        Math.sqrt(8_000_000 / (view.width * view.height)),
        8192 / view.width,
        8192 / view.height,
      );
      canvas = window.document.createElement("canvas");
      canvas.width = Math.max(1, Math.floor(view.width * ratio));
      canvas.height = Math.max(1, Math.floor(view.height * ratio));
      canvas.style.width = `${view.width}px`;
      canvas.style.height = `${view.height}px`;
      canvas.setAttribute("aria-hidden", "true");
      task = page.render({
        canvas,
        viewport: view,
        transform: [ratio, 0, 0, ratio, 0, 0],
      });
      await task.promise;
      if (cancelled) return;
      pageHost.value?.replaceChildren(canvas);
      rendered.value = true;
    } catch (cause) {
      if (
        !cancelled &&
        (cause as Error)?.name !== "RenderingCancelledException"
      ) {
        error.value = tm("workspaceFiles.pdf.loadFailed");
      }
    }
  },
  { flush: "post" },
);
</script>

<style scoped>
.pdf-page {
  position: relative;
  flex: 0 0 auto;
  background: white;
  box-shadow: 0 1px 6px #0002;
}
.pdf-canvas {
  position: absolute;
  inset: 0;
}
.pdf-canvas :deep(canvas) {
  display: block;
}
.pdf-placeholder {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 12px;
  color: #888;
  font-size: 13px;
}
.pdf-error {
  padding: 24px;
  text-align: center;
}
</style>
