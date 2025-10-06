export type RouteLike = { path: string };

export function useChatRouteSync() {
  function onRouteChange(
    to: RouteLike,
    currCid: string,
    conversations: Array<{ cid: string }> | undefined,
    opts: {
      setPendingCid: (cid: string) => void;
      getConversationMessages: (cid: string) => void;
    }
  ) {
    if (!to || !to.path) return;

    // 仅处理 /chat/<cid> 或 /chatbox/<cid>
    if (to.path.startsWith('/chat/') || to.path.startsWith('/chatbox/')) {
      const pathCid = to.path.split('/')[2];
      if (pathCid && pathCid !== currCid) {
        if (conversations && conversations.length > 0) {
          const exists = conversations.some((c) => c.cid === pathCid);
          if (exists) {
            opts.getConversationMessages(pathCid);
          } else {
            opts.setPendingCid(pathCid);
          }
        } else {
          opts.setPendingCid(pathCid);
        }
      }
    }
  }

  function onConversationsChange(
    newConversations: Array<{ cid: string }> | undefined,
    currCid: string,
    pendingCid: string | null,
    opts: {
      selectAndOpen: (cid: string) => void;
      clearPending: () => void;
    }
  ) {
    if (!newConversations || newConversations.length === 0) return;

    if (pendingCid) {
      const found = newConversations.find((c) => c.cid === pendingCid);
      if (found) {
        opts.selectAndOpen(pendingCid);
        opts.clearPending();
        return;
      }
    }

    // 没有 URL 指定且当前未选中，则默认打开第一个
    if (!currCid && newConversations.length > 0) {
      const first = newConversations[0];
      opts.selectAndOpen(first.cid);
    }
  }

  return { onRouteChange, onConversationsChange };
}
