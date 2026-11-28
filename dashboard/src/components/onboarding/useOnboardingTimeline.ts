import { nextTick, onBeforeUnmount, onMounted, ref, watch, type Ref } from 'vue';
import type { ChatRecord } from '@/composables/useMessages';

export type WidgetKind = 'notice' | 'model' | 'trial' | 'platform' | 'welcome';
export type WidgetStatus = 'active' | 'done' | 'skipped';

export interface GuideStreamEntry {
  kind: 'guide';
  id: string;
  role: 'assistant' | 'user';
  textKey?: string;
  textParams?: Record<string, string>;
  rawText?: string;
  widget?: WidgetKind;
  widgetStatus?: WidgetStatus;
  summaryKey?: string;
  summaryParams?: Record<string, string>;
  expanded?: boolean;
  expandedMounted?: boolean;
  revealed?: boolean;
  typedLength?: number;
  typingDone?: boolean;
}

export interface ChatStreamEntry {
  kind: 'chat';
  id: string;
  records: ChatRecord[];
}

export type StreamEntry = GuideStreamEntry | ChatStreamEntry;

interface UseOnboardingTimelineOptions {
  translate: (key: string, params?: Record<string, string>) => string;
  hasLiveChat: Ref<boolean>;
  scrollContainer: Ref<HTMLElement | undefined>;
  streamFeed: Ref<HTMLElement | undefined>;
  composerShell: Ref<HTMLElement | undefined>;
  onDeactivateFormWidgets?: () => void;
}

/**
 * Manages the onboarding conversation timeline, sequential typewriter queue,
 * collapsible widget lookups, and sticky-bottom auto-scroll behavior.
 */
export function useOnboardingTimeline(options: UseOnboardingTimelineOptions) {
  const { translate, hasLiveChat, scrollContainer, streamFeed, composerShell } = options;

  let entryCounter = 1;
  const nextEntryId = (prefix: string) => `${prefix}-${++entryCounter}`;

  const activeWidgetId = ref('guide-notice-1');
  const shouldStickToBottom = ref(true);
  const isAwayFromBottom = ref(false);
  const timeline = ref<StreamEntry[]>([
    {
      kind: 'guide',
      id: activeWidgetId.value,
      role: 'assistant',
      textKey: 'guide.agentGreeting',
      widget: 'notice',
      widgetStatus: 'active',
    },
  ]);

  let mounted = true;
  let activeTypingTimer: number | null = null;
  let layoutObserver: ResizeObserver | undefined;
  const typingQueue: string[] = [];

  function shouldAnimateTyping(): boolean {
    if (typeof window === 'undefined') return false;
    return !window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  }

  function resolveEntryText(entry: GuideStreamEntry): string {
    if (entry.rawText !== undefined) return entry.rawText;
    if (!entry.textKey) return '';
    return translate(entry.textKey, entry.textParams);
  }

  function resolveDisplayedText(entry: GuideStreamEntry): string {
    const full = resolveEntryText(entry);
    if (entry.typingDone !== false || entry.typedLength === undefined) return full;
    return Array.from(full).slice(0, entry.typedLength).join('');
  }

  function resolveSummaryText(entry: GuideStreamEntry): string {
    if (!entry.summaryKey) return '';
    return translate(entry.summaryKey, entry.summaryParams);
  }

  function handleStreamScroll() {
    const container = scrollContainer.value;
    if (!container) return;
    const distanceToBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
    shouldStickToBottom.value = distanceToBottom < 72;
    isAwayFromBottom.value = distanceToBottom > 12;
  }

  function scrollToBottom(force = false) {
    void nextTick(() => {
      const container = scrollContainer.value;
      if (!container) return;
      if (force) shouldStickToBottom.value = true;
      container.scrollTop = container.scrollHeight;
      isAwayFromBottom.value = false;
    });
  }

  function flushTypingQueue() {
    if (activeTypingTimer !== null && typeof window !== 'undefined') {
      window.clearTimeout(activeTypingTimer);
      activeTypingTimer = null;
    }
    typingQueue.length = 0;
    for (const item of timeline.value) {
      if (item.kind === 'guide') {
        item.revealed = true;
        item.typedLength = undefined;
        item.typingDone = true;
      }
    }
  }

  function runNextQueuedTyping() {
    if (activeTypingTimer !== null || !typingQueue.length) return;
    const nextId = typingQueue[0];
    const entry = timeline.value.find(
      (item): item is GuideStreamEntry => item.kind === 'guide' && item.id === nextId,
    );
    if (!entry) {
      typingQueue.shift();
      runNextQueuedTyping();
      return;
    }
    entry.revealed = true;
    const chars = Array.from(resolveEntryText(entry));
    if (!shouldAnimateTyping() || !chars.length) {
      entry.typedLength = undefined;
      entry.typingDone = true;
      typingQueue.shift();
      scrollToBottom(true);
      runNextQueuedTyping();
      return;
    }
    const budgetMs = entry.role === 'user' ? 240 : 620;
    const stepMs = Math.max(12, Math.min(26, Math.round(budgetMs / chars.length)));
    const tick = () => {
      activeTypingTimer = null;
      if (!mounted) return;
      const nextLength = (entry.typedLength ?? 0) + 1;
      if (nextLength >= chars.length) {
        entry.typedLength = undefined;
        entry.typingDone = true;
        typingQueue.shift();
        scrollToBottom();
        if (typingQueue.length) {
          activeTypingTimer = window.setTimeout(() => {
            activeTypingTimer = null;
            runNextQueuedTyping();
          }, 90);
        }
        return;
      }
      entry.typedLength = nextLength;
      scrollToBottom();
      activeTypingTimer = window.setTimeout(tick, stepMs);
    };
    scrollToBottom(true);
    activeTypingTimer = window.setTimeout(tick, stepMs);
  }

  function startInitialTyping() {
    const initial = timeline.value[0];
    if (initial?.kind === 'guide' && shouldAnimateTyping()) {
      initial.revealed = true;
      initial.typedLength = 0;
      initial.typingDone = false;
      typingQueue.push(initial.id);
      runNextQueuedTyping();
    }
  }

  function findActiveWidget(kind?: WidgetKind): GuideStreamEntry | undefined {
    for (let i = timeline.value.length - 1; i >= 0; i--) {
      const item = timeline.value[i];
      if (item.kind === 'guide' && item.widget && item.widgetStatus === 'active') {
        if (!kind || item.widget === kind) return item;
      }
    }
    return undefined;
  }

  function deactivateActiveFormWidgets(reason: 'skipped' | 'done' = 'skipped') {
    for (const item of timeline.value) {
      if (
        item.kind === 'guide' &&
        item.widget &&
        item.widget !== 'welcome' &&
        item.widgetStatus === 'active'
      ) {
        item.widgetStatus = item.widget === 'trial' && hasLiveChat.value ? 'done' : reason;
        if (!item.summaryKey) {
          if (item.widget === 'notice') item.summaryKey = 'guide.summaryNoticeDone';
          else if (item.widget === 'model') item.summaryKey = 'guide.summaryModelSkipped';
          else if (item.widget === 'trial') {
            item.summaryKey = hasLiveChat.value
              ? 'guide.summaryTrialDone'
              : 'guide.summaryTrialSkipped';
          } else if (item.widget === 'platform') {
            item.summaryKey = 'guide.summaryPlatformSkipped';
          }
        }
      }
    }
    options.onDeactivateFormWidgets?.();
  }

  function pushGuideMessage(entry: Omit<GuideStreamEntry, 'kind' | 'id'>, idPrefix = 'guide') {
    const id = nextEntryId(idPrefix);
    if (entry.widget && entry.widgetStatus === 'active') {
      activeWidgetId.value = id;
    }
    const animate =
      shouldAnimateTyping() && (entry.role === 'assistant' || entry.rawText === undefined);
    const queued = animate && typingQueue.length > 0;
    timeline.value.push({
      kind: 'guide',
      id,
      ...entry,
      revealed: !queued,
      typedLength: animate ? 0 : undefined,
      typingDone: !animate,
    });
    if (animate) {
      typingQueue.push(id);
      runNextQueuedTyping();
    } else {
      scrollToBottom(true);
    }
  }

  function appendLiveChatExchange(userRecord: ChatRecord, botRecord: ChatRecord) {
    const lastEntry = timeline.value[timeline.value.length - 1];
    if (lastEntry && lastEntry.kind === 'chat') {
      lastEntry.records.push(userRecord, botRecord);
    } else {
      timeline.value.push({
        kind: 'chat',
        id: nextEntryId('chat'),
        records: [userRecord, botRecord],
      });
    }
    scrollToBottom(true);
  }

  onMounted(() => {
    if (typeof ResizeObserver === 'undefined') return;
    layoutObserver = new ResizeObserver((entries) => {
      const container = scrollContainer.value;
      if (!container) return;
      for (const entry of entries) {
        if (entry.target === composerShell.value) {
          const height = Math.ceil(entry.target.getBoundingClientRect().height);
          container.style.setProperty('--chat-composer-height', `${height}px`);
        }
      }
      if (shouldStickToBottom.value) {
        container.scrollTop = container.scrollHeight;
        isAwayFromBottom.value = false;
      } else {
        isAwayFromBottom.value =
          container.scrollHeight - container.scrollTop - container.clientHeight > 12;
      }
    });
    if (streamFeed.value) layoutObserver.observe(streamFeed.value);
    if (composerShell.value) layoutObserver.observe(composerShell.value);
  });

  watch(
    [streamFeed, composerShell],
    (elements, previousElements) => {
      if (!layoutObserver) return;
      for (const element of previousElements) {
        if (element) layoutObserver.unobserve(element);
      }
      for (const element of elements) {
        if (element) layoutObserver.observe(element);
      }
      if (composerShell.value && scrollContainer.value) {
        const height = Math.ceil(composerShell.value.getBoundingClientRect().height);
        scrollContainer.value.style.setProperty('--chat-composer-height', `${height}px`);
      }
    },
    { flush: 'post' },
  );

  onBeforeUnmount(() => {
    mounted = false;
    flushTypingQueue();
    layoutObserver?.disconnect();
  });

  return {
    timeline,
    activeWidgetId,
    shouldStickToBottom,
    isAwayFromBottom,
    resolveEntryText,
    resolveDisplayedText,
    resolveSummaryText,
    handleStreamScroll,
    scrollToBottom,
    flushTypingQueue,
    startInitialTyping,
    findActiveWidget,
    deactivateActiveFormWidgets,
    pushGuideMessage,
    appendLiveChatExchange,
  };
}
