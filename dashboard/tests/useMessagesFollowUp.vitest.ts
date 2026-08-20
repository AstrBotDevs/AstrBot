import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ref } from 'vue';

const testState = vi.hoisted(() => ({
  sockets: [] as MockWebSocket[],
}));

vi.mock('@/api/v1', () => ({
  chatApi: {
    unifiedWebSocketUrl: () => 'ws://example.test/unified-chat',
    stopSession: vi.fn().mockResolvedValue({ data: { status: 'ok' } }),
  },
  fileApi: {},
}));

vi.mock('@/api/http', () => ({
  fetchWithAuth: vi.fn(),
}));

import { chatApi } from '@/api/v1';
import { useMessages } from '@/composables/useMessages';

class MockWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;

  readonly CONNECTING = MockWebSocket.CONNECTING;
  readonly OPEN = MockWebSocket.OPEN;
  readonly CLOSING = MockWebSocket.CLOSING;
  readonly CLOSED = MockWebSocket.CLOSED;
  readyState = MockWebSocket.OPEN;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void | Promise<void>) | null = null;

  constructor(_url: string) {
    testState.sockets.push(this);
  }

  addEventListener(_type: string, _listener: () => void, _options?: unknown) {}

  close() {
    this.readyState = MockWebSocket.CLOSED;
    void this.onclose?.();
  }

  send(_data: string) {}

  emit(payload: Record<string, unknown>) {
    this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent);
  }
}

describe('useMessages follow-up streams', () => {
  beforeEach(() => {
    testState.sockets.length = 0;
    vi.mocked(chatApi.stopSession).mockClear();
  });

  it('keeps a captured follow-up with its target run and routes concurrent events', () => {
    vi.stubGlobal('WebSocket', MockWebSocket);
    const sessionId = 'session-1';
    const messages = useMessages({ currentSessionId: ref(sessionId) });
    const first = messages.createLocalExchange({
      sessionId,
      messageId: 'request-1',
      parts: [{ type: 'plain', text: 'first' }],
    });

    messages.sendMessageStream({
      sessionId,
      messageId: 'request-1',
      parts: [{ type: 'plain', text: 'first' }],
      transport: 'websocket',
      botRecord: first.botRecord,
      userRecord: first.userRecord,
    });
    const socket = testState.sockets[0];
    socket.emit({
      ct: 'chat',
      type: 'run_started',
      message_id: 'request-1',
      data: { run_id: 'request-1' },
    });

    const followUp = messages.createLocalExchange({
      sessionId,
      messageId: 'request-2',
      parts: [{ type: 'plain', text: 'follow up' }],
    });
    messages.sendMessageStream({
      sessionId,
      messageId: 'request-2',
      parts: [{ type: 'plain', text: 'follow up' }],
      transport: 'websocket',
      botRecord: followUp.botRecord,
      userRecord: followUp.userRecord,
    });

    socket.emit({
      ct: 'chat',
      type: 'follow_up_captured',
      message_id: 'request-2',
      data: { target_run_id: 'request-1' },
    });
    socket.emit({ ct: 'chat', type: 'end', message_id: 'request-2' });
    socket.emit({
      ct: 'chat',
      type: 'plain',
      message_id: 'request-1',
      data: 'answer',
      streaming: true,
    });

    const records = messages.messagesBySession[sessionId];
    expect(records).toEqual([
      first.userRecord,
      followUp.userRecord,
      first.botRecord,
    ]);
    expect(messages.messageParts(first.botRecord)).toEqual([
      { type: 'plain', text: 'answer' },
    ]);
    expect(messages.isMessageStreaming(first.botRecord, 2)).toBe(true);
    expect(messages.isMessageStreaming(followUp.botRecord, 2)).toBe(false);

    socket.emit({ ct: 'chat', type: 'end', message_id: 'request-1' });
    expect(messages.isSessionRunning(sessionId)).toBe(false);
  });

  it('restores a complete response suffix while preserving break fallbacks', () => {
    vi.stubGlobal('WebSocket', MockWebSocket);
    const sessionId = 'session-1';
    const messages = useMessages({ currentSessionId: ref(sessionId) });

    const complete = messages.createLocalExchange({
      sessionId,
      messageId: 'complete-request',
      parts: [{ type: 'plain', text: 'first' }],
    });
    messages.sendMessageStream({
      sessionId,
      messageId: 'complete-request',
      parts: [{ type: 'plain', text: 'first' }],
      transport: 'websocket',
      botRecord: complete.botRecord,
      userRecord: complete.userRecord,
    });
    const socket = testState.sockets[testState.sockets.length - 1];
    socket.emit({
      ct: 'chat',
      type: 'plain',
      message_id: 'complete-request',
      data: 'partial',
      streaming: true,
    });
    socket.emit({
      ct: 'chat',
      type: 'complete',
      message_id: 'complete-request',
      data: 'partial response',
    });

    expect(messages.messageParts(complete.botRecord)).toEqual([
      { type: 'plain', text: 'partial response' },
    ]);

    const noPlain = messages.createLocalExchange({
      sessionId,
      messageId: 'no-plain-request',
      parts: [{ type: 'plain', text: 'second' }],
    });
    messages.sendMessageStream({
      sessionId,
      messageId: 'no-plain-request',
      parts: [{ type: 'plain', text: 'second' }],
      transport: 'websocket',
      botRecord: noPlain.botRecord,
      userRecord: noPlain.userRecord,
    });
    socket.emit({
      ct: 'chat',
      type: 'complete',
      message_id: 'no-plain-request',
      data: 'complete response',
    });

    expect(messages.messageParts(noPlain.botRecord)).toEqual([
      { type: 'plain', text: 'complete response' },
    ]);

    const interrupted = messages.createLocalExchange({
      sessionId,
      messageId: 'break-request',
      parts: [{ type: 'plain', text: 'third' }],
    });
    messages.sendMessageStream({
      sessionId,
      messageId: 'break-request',
      parts: [{ type: 'plain', text: 'third' }],
      transport: 'websocket',
      botRecord: interrupted.botRecord,
      userRecord: interrupted.userRecord,
    });
    socket.emit({
      ct: 'chat',
      type: 'plain',
      message_id: 'break-request',
      data: 'interrupted',
      streaming: true,
    });
    socket.emit({
      ct: 'chat',
      type: 'break',
      message_id: 'break-request',
      data: 'interrupted response',
    });

    expect(messages.messageParts(interrupted.botRecord)).toEqual([
      { type: 'plain', text: 'interrupted' },
    ]);

    const breakFallback = messages.createLocalExchange({
      sessionId,
      messageId: 'break-fallback-request',
      parts: [{ type: 'plain', text: 'fourth' }],
    });
    messages.sendMessageStream({
      sessionId,
      messageId: 'break-fallback-request',
      parts: [{ type: 'plain', text: 'fourth' }],
      transport: 'websocket',
      botRecord: breakFallback.botRecord,
      userRecord: breakFallback.userRecord,
    });
    socket.emit({
      ct: 'chat',
      type: 'break',
      message_id: 'break-fallback-request',
      data: 'tool-call handoff',
    });

    expect(messages.messageParts(breakFallback.botRecord)).toEqual([
      { type: 'plain', text: 'tool-call handoff' },
    ]);
  });

  it('keeps agent_stats on the originating request and can interrupt that session', async () => {
    vi.stubGlobal('WebSocket', MockWebSocket);
    const sessionId = 'session-1';
    const messages = useMessages({ currentSessionId: ref(sessionId) });
    const first = messages.createLocalExchange({
      sessionId,
      messageId: 'request-1',
      parts: [{ type: 'plain', text: 'first' }],
    });
    messages.sendMessageStream({
      sessionId,
      messageId: 'request-1',
      parts: [{ type: 'plain', text: 'first' }],
      transport: 'websocket',
      botRecord: first.botRecord,
      userRecord: first.userRecord,
    });
    const second = messages.createLocalExchange({
      sessionId,
      messageId: 'request-2',
      parts: [{ type: 'plain', text: 'second' }],
    });
    messages.sendMessageStream({
      sessionId,
      messageId: 'request-2',
      parts: [{ type: 'plain', text: 'second' }],
      transport: 'websocket',
      botRecord: second.botRecord,
      userRecord: second.userRecord,
    });

    const socket = testState.sockets[0];
    socket.emit({
      ct: 'chat',
      type: 'agent_stats',
      message_id: 'request-1',
      data: { token_usage: { output: 1 } },
    });
    socket.emit({
      ct: 'chat',
      type: 'agent_stats',
      message_id: 'request-1',
      data: { token_usage: { output: 2 } },
    });
    socket.emit({
      ct: 'chat',
      type: 'agent_stats',
      message_id: 'request-2',
      data: { token_usage: { output: 9 } },
    });

    expect(first.botRecord.content.agentStats).toEqual({
      token_usage: { output: 2 },
    });
    expect(second.botRecord.content.agentStats).toEqual({
      token_usage: { output: 9 },
    });

    await messages.stopSession(sessionId);
    expect(chatApi.stopSession).toHaveBeenCalledWith(sessionId);
  });
});
