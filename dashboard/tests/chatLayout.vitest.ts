import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

function readSource(path: string): string {
  return readFileSync(path, 'utf8');
}

describe('chat viewport layout', () => {
  it('locks the dashboard shell to the viewport on chat routes', () => {
    const primitives = readSource('src/styles/app-primitives.scss');

    expect(primitives).toContain('html:has(.dashboard-main--chat)');
    expect(primitives).toContain('body:has(.dashboard-main--chat)');
    expect(primitives).toContain(
      '.dashboard-app:has(.dashboard-main--chat) .v-application__wrap',
    );
    expect(primitives).toContain('height: 100dvh');
    expect(primitives).toContain('flex: 1 1 0%');
    expect(primitives).toContain('.chat-layout-panel > *');
  });

  it('lets the message pane and reasoning sidebar shrink inside the chat shell', () => {
    const chat = readSource('src/components/chat/Chat.vue');
    const sidebar = readSource('src/components/chat/ReasoningSidebar.vue');
    const chatMain = chat.slice(chat.indexOf('.chat-main {'));

    expect(chat).toContain('flex: 1 1 0%;');
    expect(chatMain).toContain('min-height: 0;');
    expect(chatMain).toContain('overflow: hidden;');
    expect(sidebar).toContain('.reasoning-sidebar-root {');
    expect(sidebar).toContain('min-height: 0;');
    expect(sidebar).toContain('overflow: hidden;');
  });

  it('caps expanded tool-call details so they scroll inside the pane', () => {
    const toolCall = readSource(
      'src/components/chat/message_list_comps/ToolCallCard.vue',
    );
    const ipython = readSource(
      'src/components/chat/message_list_comps/IPythonToolBlock.vue',
    );

    expect(toolCall).toContain('max-height: min(20vh, 160px);');
    expect(toolCall).toContain('max-height: min(28vh, 200px);');
    expect(ipython).toContain('max-height: min(28vh, 200px);');
  });
});
