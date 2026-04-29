/**
 * Global reactor background mouse tracking
 * Shares mouse position across all components so the canvas
 * background can react to UI element proximity.
 */
import { ref, readonly } from "vue";

const mouseX = ref(-9999);
const mouseY = ref(-9999);
const isOverUI = ref(false);

function onMouseMove(e: MouseEvent) {
  mouseX.value = e.clientX;
  mouseY.value = e.clientY;
}

function onMouseLeave() {
  mouseX.value = -9999;
  mouseY.value = -9999;
  isOverUI.value = false;
}

function setIsOverUI(val: boolean) {
  isOverUI.value = val;
}

export function useReactorBg() {
  return {
    mouseX: readonly(mouseX),
    mouseY: readonly(mouseY),
    isOverUI: readonly(isOverUI),
    onMouseMove,
    onMouseLeave,
    setIsOverUI,
  };
}
