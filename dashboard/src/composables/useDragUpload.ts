import { onScopeDispose, ref } from 'vue';

/**
 * Own drag state for a chat surface and forward dropped files to the upload
 * pipeline used by the surrounding chat component.
 */
export function useDragUpload(onDrop: (files: FileList) => void) {
  const isDragging = ref(false);
  let dragLeaveTimeout: number | null = null;

  onScopeDispose(() => {
    if (dragLeaveTimeout !== null) {
      clearTimeout(dragLeaveTimeout);
      dragLeaveTimeout = null;
    }
  });

  const dragEvents = {
    dragover(event: DragEvent) {
      if (dragLeaveTimeout !== null) {
        clearTimeout(dragLeaveTimeout);
        dragLeaveTimeout = null;
      }
      if (!event.dataTransfer?.types.includes('Files')) return;
      event.preventDefault();
      isDragging.value = true;
    },
    dragleave() {
      dragLeaveTimeout = window.setTimeout(() => {
        isDragging.value = false;
      }, 50);
    },
    drop(event: DragEvent) {
      event.preventDefault();
      isDragging.value = false;
      if (dragLeaveTimeout !== null) {
        clearTimeout(dragLeaveTimeout);
        dragLeaveTimeout = null;
      }
      const files = event.dataTransfer?.files;
      if (files && files.length > 0) onDrop(files);
    },
  };

  return { isDragging, dragEvents };
}
