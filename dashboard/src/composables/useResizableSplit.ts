// Author: elecvoid243, 2026-07-12
// Spec: docs/superpowers/specs/2026-07-11-document-manager-design.md §3.5
//
// Mouse-drag resize state machine for two-pane split layouts.
// Lifted verbatim from FileBrowserView.vue's local resize handler
// so DocumentManager can use the same gesture with identical
// clamping behavior. The containerRef parameter is optional —
// when omitted, the percent math falls back to document.body width
// which is what FileBrowserView does today.

import { ref, onBeforeUnmount, type Ref } from "vue";

export interface UseResizableSplitOptions {
  initialPercent?: number;
  minPercent?: number;
  maxPercent?: number;
  containerRef?: Ref<HTMLElement | null>;
  /**
   * Which edge the dragged pane anchors to. 'left' (default) treats
   * percent as "distance from the left edge of the container" (the
   * file-browser / tree-pane pattern). 'right' flips the math so
   * percent is "distance from the right edge" — i.e. the right pane
   * occupies `percent` of the container width. This lets the same
   * composable drive panes on either side without callers having
   * to mirror the math themselves.
   */
  direction?: "left" | "right";
}

export interface UseResizableSplit {
  percent: Ref<number>;
  isResizing: Ref<boolean>;
  startResize: (e: MouseEvent) => void;
}

const DEFAULT_MIN = 15;
const DEFAULT_MAX = 70;
const DEFAULT_INIT = 30;

export function useResizableSplit(
  opts: UseResizableSplitOptions = {},
): UseResizableSplit {
  const min = opts.minPercent ?? DEFAULT_MIN;
  const max = opts.maxPercent ?? DEFAULT_MAX;
  const init = opts.initialPercent ?? DEFAULT_INIT;
  const direction = opts.direction ?? "left";

  const percent = ref<number>(init);
  const isResizing = ref<boolean>(false);

  function clamp(pct: number): number {
    return Math.min(max, Math.max(min, pct));
  }

  function onMouseMove(e: MouseEvent) {
    if (!isResizing.value) return;
    const container = opts.containerRef?.value;
    let width = 0;
    let left = 0;
    let right = 0;
    if (container) {
      const rect = container.getBoundingClientRect();
      width = rect.width;
      left = rect.left;
      right = rect.right;
    } else if (typeof document !== "undefined") {
      width = document.body.clientWidth || window.innerWidth || 0;
      left = 0;
      right = left + width;
    } else {
      return;
    }
    if (width <= 0) return;
    // 'left' : percent = how far the cursor is from the left edge
    // 'right': percent = how far the cursor is from the right edge
    //          (so the right pane shrinks/grows as the user drags)
    const raw =
      direction === "right"
        ? ((right - e.clientX) / width) * 100
        : ((e.clientX - left) / width) * 100;
    percent.value = clamp(raw);
  }

  function onMouseUp() {
    if (!isResizing.value) return;
    isResizing.value = false;
    if (typeof document !== "undefined") {
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
    }
  }

  function startResize(e: MouseEvent) {
    e.preventDefault();
    isResizing.value = true;
    if (typeof document !== "undefined") {
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
      document.addEventListener("mousemove", onMouseMove);
      document.addEventListener("mouseup", onMouseUp);
    }
  }

  onBeforeUnmount(() => {
    if (isResizing.value) onMouseUp();
  });

  return { percent, isResizing, startResize };
}
