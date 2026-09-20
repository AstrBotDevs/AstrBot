import { onScopeDispose, ref } from 'vue';

/**
 * 拖拽上传热区:管理拖拽遮罩显隐与 drop 事件。
 * 事件挂在聊天区域容器上,drop 时把文件交给 onDrop 回调走现有上传链路。
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
        dragover(e: DragEvent) {
            if (dragLeaveTimeout) {
                clearTimeout(dragLeaveTimeout);
                dragLeaveTimeout = null;
            }
            if (!e.dataTransfer?.types.includes('Files')) return;
            e.preventDefault();
            isDragging.value = true;
        },
        dragleave() {
            dragLeaveTimeout = window.setTimeout(() => {
                isDragging.value = false;
            }, 50);
        },
        drop(e: DragEvent) {
            e.preventDefault();
            isDragging.value = false;
            if (dragLeaveTimeout) {
                clearTimeout(dragLeaveTimeout);
                dragLeaveTimeout = null;
            }
            const files = e.dataTransfer?.files;
            if (files && files.length > 0) {
                onDrop(files);
            }
        },
    };

    return { isDragging, dragEvents };
}
