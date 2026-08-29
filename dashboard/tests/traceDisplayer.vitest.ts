import { flushPromises } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import TraceDisplayer from '@/components/shared/TraceDisplayer.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

const state = vi.hoisted(() => ({
  history: vi.fn(),
  sources: [] as Array<{
    close: ReturnType<typeof vi.fn>;
    onerror: (() => void) | null;
  }>,
}));

vi.mock('@/api/v1', () => ({
  logApi: {
    history: state.history,
    liveUrl: () => '/api/v1/logs/live',
  },
}));

vi.mock('event-source-polyfill', () => ({
  EventSourcePolyfill: class {
    close = vi.fn();
    onerror: (() => void) | null = null;

    constructor() {
      state.sources.push(this);
    }
  },
}));

describe('TraceDisplayer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    state.sources.splice(0);
    state.history.mockResolvedValue({ data: { data: { logs: [] } } });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('cancels a scheduled SSE reconnect when the displayer is unmounted', async () => {
    vi.useFakeTimers();
    const wrapper = mountWithVuetify(TraceDisplayer);
    await flushPromises();

    expect(state.history).toHaveBeenCalledOnce();
    expect(state.sources).toHaveLength(1);

    state.sources[0]!.onerror?.();
    expect(state.sources[0]!.close).toHaveBeenCalledOnce();

    wrapper.unmount();
    await vi.runAllTimersAsync();

    expect(state.sources).toHaveLength(1);
    expect(state.history).toHaveBeenCalledOnce();
  });

  it('renders table chrome from the trace catalog', async () => {
    const wrapper = mountWithVuetify(TraceDisplayer);
    await flushPromises();

    expect(wrapper.text()).toContain('Time');
    expect(wrapper.text()).toContain('Event ID');
    expect(wrapper.text()).toContain('UMO');
    expect(wrapper.text()).toContain('Sender');
    expect(wrapper.text()).toContain('Content');
    expect(wrapper.text()).toContain('No trace data yet');
    expect(wrapper.text()).not.toContain('Outline');
  });
});
