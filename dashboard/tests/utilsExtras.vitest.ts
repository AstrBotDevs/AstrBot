import { effectScope } from 'vue';
import { describe, expect, it, vi } from 'vitest';
import { copyToClipboard } from '@/utils/clipboard';
import { useDragUpload } from '@/composables/useDragUpload';
import { useRecording } from '@/composables/useRecording';
import {
  clearSidebarCustomization,
  getSidebarCustomization,
  resolveSidebarItems,
  setSidebarCustomization,
} from '@/utils/sidebarCustomization';
import { MORE_GROUP_KEY } from '@/layouts/full/vertical-sidebar/sidebarItem';

describe('frontend utility extras', () => {
  it('covers sidebar customization persistence and merge', () => {
    clearSidebarCustomization();
    expect(getSidebarCustomization()).toBeNull();
    setSidebarCustomization({
      mainItems: ['core.navigation.chat', 'dup', 'dup'],
      moreItems: ['core.navigation.about'],
    });
    const stored = getSidebarCustomization();
    expect(stored?.mainItems).toContain('core.navigation.chat');
    const items = [
      { title: 'core.navigation.chat', icon: 'mdi-chat' },
      { title: 'core.navigation.about', icon: 'mdi-information' },
      {
        title: MORE_GROUP_KEY,
        children: [{ title: 'core.navigation.about' }],
      },
    ];
    const resolved = resolveSidebarItems(items, stored, {
      cloneItems: true,
      assembleMoreGroup: true,
    });
    expect(resolved.mainItems.length).toBeGreaterThan(0);
    expect(resolved.normalizedMainKeys.length).toBeGreaterThan(0);
    clearSidebarCustomization();
  });

  it('covers drag upload events and clipboard fallback', async () => {
    const dropped: FileList[] = [];
    const scope = effectScope();
    const drag = scope.run(() =>
      useDragUpload((files) => {
        dropped.push(files);
      }),
    );
    if (!drag) throw new Error('drag composable failed');
    const file = new File(['x'], 'a.txt');
    const dataTransfer = {
      types: ['Files'],
      files: { 0: file, length: 1, item: () => file },
    } as unknown as DataTransfer;
    drag.dragEvents.dragover({
      preventDefault() {},
      dataTransfer,
    } as DragEvent);
    expect(drag.isDragging.value).toBe(true);
    drag.dragEvents.dragleave();
    drag.dragEvents.drop({
      preventDefault() {},
      dataTransfer,
    } as DragEvent);
    expect(drag.isDragging.value).toBe(false);
    scope.stop();

    Object.defineProperty(window, 'isSecureContext', {
      configurable: true,
      value: false,
    });
    document.execCommand = vi.fn(() => true) as typeof document.execCommand;
    expect(await copyToClipboard('hello')).toBe(true);
    expect(await copyToClipboard('')).toBe(false);
  });

  it('covers recording success path with a fake MediaRecorder', async () => {
    class FakeRecorder {
      stream = { getTracks: () => [{ stop: vi.fn() }] };
      mimeType = 'audio/webm';
      ondataavailable: ((event: { data: Blob }) => void) | null = null;
      onstop: (() => void) | null = null;
      start() {
        this.ondataavailable?.({
          data: new Blob(['audio'], { type: 'audio/webm' }),
        });
      }
      stop() {
        this.onstop?.();
      }
      static isTypeSupported() {
        return true;
      }
    }
    vi.stubGlobal('MediaRecorder', FakeRecorder);
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        getUserMedia: vi.fn(async () => ({
          getTracks: () => [{ stop: vi.fn() }],
        })),
      },
    });
    const recording = useRecording();
    await recording.startRecording((label) => {
      expect(label).toContain('录音');
    });
    const file = await recording.stopRecording();
    expect(file.size).toBeGreaterThan(0);
    vi.unstubAllGlobals();
  });
});
