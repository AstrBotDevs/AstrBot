<template>
  <div class="workspace-pdf">
    <div
      ref="viewport"
      class="pdf-scroll"
      :aria-busy="loading"
      @scroll.passive="rememberPage"
    >
      <div v-if="error" class="pdf-state" role="alert">{{ error }}</div>
      <div v-else-if="loading" class="pdf-state" role="status">
        <v-progress-circular indeterminate size="24" width="2" />
        <span>{{ tm("workspaceFiles.pdf.loading") }}</span>
      </div>
      <div v-else-if="pdf" class="pdf-pages">
        <WorkspacePdfPage
          v-for="(layout, index) in pageLayouts"
          :key="index"
          :document="pdf"
          :page="index + 1"
          :total="pdf.numPages"
          :width="layout.width"
          :height="layout.height"
          :scroll-root="viewport"
        />
      </div>
    </div>
    <div
      v-if="pdf && !loading && !error"
      class="pdf-zoom-hub"
      role="group"
      :aria-label="tm('workspaceFiles.pdf.zoomControls')"
    >
      <v-btn
        icon
        size="x-small"
        variant="text"
        :disabled="zoom <= 0.5"
        :aria-label="tm('workspaceFiles.pdf.zoomOut')"
        :title="tm('workspaceFiles.pdf.zoomOut')"
        @click="emit('update:zoom', Math.max(0.5, zoom - 0.25))"
        ><Minus :size="16"
      /></v-btn>
      <v-btn
        size="x-small"
        variant="text"
        class="pdf-zoom-value"
        :title="tm('workspaceFiles.pdf.fitWidth')"
        :aria-label="tm('workspaceFiles.pdf.fitWidth')"
        @click="emit('update:zoom', 1)"
        >{{ Math.round(zoom * 100) }}%</v-btn
      >
      <v-btn
        icon
        size="x-small"
        variant="text"
        :disabled="zoom >= 3"
        :aria-label="tm('workspaceFiles.pdf.zoomIn')"
        :title="tm('workspaceFiles.pdf.zoomIn')"
        @click="emit('update:zoom', Math.min(3, zoom + 0.25))"
        ><Plus :size="16"
      /></v-btn>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  shallowRef,
  watch,
} from "vue";
import { Minus, Plus } from "@lucide/vue";
import {
  getDocument,
  GlobalWorkerOptions,
  version,
  type PDFDocumentProxy,
  type PDFDocumentLoadingTask,
} from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { useModuleI18n } from "@/i18n/composables";
import WorkspacePdfPage from "./WorkspacePdfPage.vue";

const props = defineProps<{ file: Blob; page: number; zoom: number }>();
const emit = defineEmits<{
  "update:page": [page: number];
  "update:zoom": [zoom: number];
}>();
const { tm } = useModuleI18n("features/chat");
const pdf = shallowRef<PDFDocumentProxy | null>(null);
const viewport = ref<HTMLElement | null>(null);
const width = ref(0);
const loading = ref(true);
const error = ref("");
const pageSizes = shallowRef<Array<{ width: number; height: number }>>([]);
const pageLayouts = computed(() => {
  const pageWidth = Math.max(1, width.value - 32) * props.zoom;
  let top = 16;
  return pageSizes.value.map((size) => {
    const height = (pageWidth * size.height) / size.width;
    const layout = { width: pageWidth, height, top };
    top += height + 16;
    return layout;
  });
});
GlobalWorkerOptions.workerSrc = workerUrl;
const resourceBase = `${import.meta.env.BASE_URL}pdfjs/${version}/`;
const observer = new ResizeObserver(([entry]) => {
  width.value = Math.floor(entry.contentRect.width);
});
onMounted(() => {
  if (viewport.value) observer.observe(viewport.value);
});
onBeforeUnmount(() => observer.disconnect());

watch(
  () => props.file,
  async (file, _, onCleanup) => {
    let cancelled = false;
    let task: PDFDocumentLoadingTask | undefined;
    onCleanup(() => {
      cancelled = true;
      void task?.destroy().catch(() => {});
    });
    pdf.value = null;
    pageSizes.value = [];
    loading.value = true;
    error.value = "";
    try {
      const data = await file.arrayBuffer();
      if (cancelled) return;
      task = getDocument({
        data,
        cMapUrl: `${resourceBase}cmaps/`,
        cMapPacked: true,
        standardFontDataUrl: `${resourceBase}standard_fonts/`,
        wasmUrl: `${resourceBase}wasm/`,
        iccUrl: `${resourceBase}iccs/`,
      });
      const document = await task.promise;
      if (cancelled) return;
      // Read dimensions without rasterizing pages, keeping mixed-size page slots stable.
      const sizes: Array<{ width: number; height: number }> = [];
      for (let start = 1; start <= document.numPages; start += 20) {
        const batch = await Promise.all(
          Array.from(
            { length: Math.min(20, document.numPages - start + 1) },
            async (_, index) => {
              const page = await document.getPage(start + index);
              const { width, height } = page.getViewport({ scale: 1 });
              return { width, height };
            },
          ),
        );
        if (cancelled) return;
        sizes.push(...batch);
      }
      pdf.value = document;
      pageSizes.value = sizes;
    } catch (cause) {
      if (cancelled) return;
      error.value = tm(
        (cause as Error)?.name === "PasswordException"
          ? "workspaceFiles.pdf.passwordProtected"
          : "workspaceFiles.pdf.loadFailed",
      );
    } finally {
      if (!cancelled) loading.value = false;
    }
  },
  { immediate: true },
);

watch(pageLayouts, async (layouts, previous, onCleanup) => {
  let cancelled = false;
  onCleanup(() => {
    cancelled = true;
  });
  const container = viewport.value;
  if (!container || !layouts.length) return;
  const scrollTop = container.scrollTop;
  const oldIndex = previous.findIndex(
    (layout) => layout.top + layout.height > scrollTop,
  );
  const index = Math.min(
    layouts.length - 1,
    oldIndex >= 0 ? oldIndex : Math.max(0, props.page - 1),
  );
  const offset =
    oldIndex >= 0
      ? (scrollTop - previous[index].top) / previous[index].height
      : 0;
  await nextTick();
  if (cancelled) return;
  // Keep the same position within the page when zooming or resizing the panel.
  container.scrollTop = Math.max(
    0,
    layouts[index].top + offset * layouts[index].height,
  );
});

function rememberPage() {
  if (loading.value || !viewport.value) return;
  const top = viewport.value.scrollTop + 16;
  const index = pageLayouts.value.findIndex(
    (layout) => layout.top + layout.height > top,
  );
  if (index >= 0 && index + 1 !== props.page) emit("update:page", index + 1);
}
</script>

<style scoped>
.workspace-pdf {
  position: relative;
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  min-width: 0;
}
.pdf-scroll {
  overflow: auto;
  overflow-anchor: none;
  scrollbar-gutter: stable;
  flex: 1;
  min-height: 0;
  background: rgba(var(--v-theme-on-surface), 0.04);
}
.pdf-pages {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  width: max-content;
  min-width: 100%;
  padding: 16px 16px 80px;
}
.pdf-zoom-hub {
  position: absolute;
  right: 20px;
  bottom: 16px;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 5px 6px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 12px;
  background: rgba(var(--v-theme-surface), 0.92);
  color: rgb(var(--v-theme-on-surface));
  box-shadow: 0 4px 20px #0002;
  backdrop-filter: blur(12px);
}
.pdf-zoom-value {
  min-width: 50px;
  font-variant-numeric: tabular-nums;
}
.pdf-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 32px 16px;
  text-align: center;
  font-size: 13px;
  color: rgba(var(--v-theme-on-surface), 0.65);
}
</style>
