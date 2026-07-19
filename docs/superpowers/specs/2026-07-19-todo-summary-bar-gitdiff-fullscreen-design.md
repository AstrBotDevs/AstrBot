# Todo Summary Bar and Git Diff Fullscreen Layering Design

> Author: elecvoid243
> Date: 2026-07-19

## Goal

Keep `TodoSummaryBar` above normal Chat UI layers while ensuring it is covered by the fullscreen `GitDiffSidebar`.

## Design

`GitDiffSidebar` owns the fullscreen state, so it emits a typed `fullscreen-change` event whenever `globalFullscreen` changes. `Chat.vue` stores that state and applies a conditional class to `TodoSummaryBar` only while the Git Diff sidebar is both open and fullscreen.

The normal TodoSummaryBar layer remains `z-index: 9999`. The conditional fullscreen class sets it to `z-index: 1200`, below the Git Diff fullscreen layer at `z-index: 1300`. The bar remains mounted, preserving its position and state, but is visually covered by the opaque fullscreen sidebar. Closing the sidebar or exiting fullscreen removes the conditional class and restores the normal layer.

## Scope

- Modify `dashboard/src/components/chat/GitDiffSidebar.vue` to emit the fullscreen state.
- Modify `dashboard/src/components/chat/Chat.vue` to consume the event and apply the conditional z-index class.
- Add a focused regression test for the cross-component wiring and layer values.

## Non-goals

- Do not change the TodoSidebar open/close behavior.
- Do not permanently lower the TodoSummaryBar z-index.
- Do not add global state or change the Git Diff fullscreen Teleport behavior.
