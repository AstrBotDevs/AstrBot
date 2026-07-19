# Todo Summary Bar Git Diff Fullscreen Layering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the draggable TodoSummaryBar on top during normal Chat usage, but below the fullscreen GitDiffSidebar.

**Architecture:** GitDiffSidebar emits its local fullscreen state through a typed event. Chat.vue stores that state and adds a conditional class to the existing fixed TodoSummaryBar. Normal state keeps `z-index: 9999`; the fullscreen condition sets `z-index: 1200`, below GitDiffSidebar's `z-index: 1300`.

**Tech Stack:** Vue 3 `<script setup>`, TypeScript, scoped CSS, Vitest.

## Global Constraints

- Work directly on the `all` branch; do not create a worktree.
- Keep the change limited to the TodoSummaryBar/GitDiffSidebar stacking interaction.
- Use English comments and logs when comments are needed.
- Preserve the existing GitDiffSidebar Teleport and TodoSummaryBar drag behavior.

---

### Task 1: Add the regression test

**Files:**
- Create: `dashboard/src/components/chat/ChatTodoSummaryBar.spec.ts`

- [ ] **Step 1: Write a failing test**

Add a focused integration contract test that reads both SFCs and asserts the fullscreen event, the parent listener, the conditional class, and the two layer values. The test must fail before the implementation because those contracts do not exist yet.

- [ ] **Step 2: Run the focused test**

Run from `dashboard`:

```cmd
pnpm exec vitest run src/components/chat/ChatTodoSummaryBar.spec.ts
```

Expected: FAIL because `GitDiffSidebar.vue` does not yet declare `fullscreen-change` and `Chat.vue` does not yet consume it.

### Task 2: Wire fullscreen state and conditional z-index

**Files:**
- Modify: `dashboard/src/components/chat/GitDiffSidebar.vue:200,269-275`
- Modify: `dashboard/src/components/chat/Chat.vue:395-401,615-621,814-815,2758-2811`

- [ ] **Step 1: Emit the fullscreen state from GitDiffSidebar**

Extend the existing `defineEmits` contract with `fullscreen-change`, then emit `globalFullscreen` from its existing immediate watcher so the parent receives both initial and subsequent values.

- [ ] **Step 2: Consume the state in Chat.vue**

Add `gitDiffFullscreen`, bind `@fullscreen-change="gitDiffFullscreen = $event"` to `GitDiffSidebar`, and add a TodoSummaryBar class that is active only when `gitDiffSidebarOpen && gitDiffFullscreen`.

- [ ] **Step 3: Add the layer override**

Keep `.todo-summary-bar { z-index: 9999; }`. Add a later scoped rule for the fullscreen class with `z-index: 1200`, so it remains below `.git-diff-sidebar.is-fullscreen { z-index: 1300; }` and restores automatically when the class is removed.

### Task 3: Verify

**Files:**
- Verify: `dashboard/src/components/chat/ChatTodoSummaryBar.spec.ts`
- Verify: `dashboard/src/components/chat/Chat.vue`
- Verify: `dashboard/src/components/chat/GitDiffSidebar.vue`

- [ ] **Step 1: Run the focused regression test**

```cmd
pnpm exec vitest run src/components/chat/ChatTodoSummaryBar.spec.ts
```

Expected: PASS.

- [ ] **Step 2: Run dashboard type checking**

```cmd
pnpm typecheck
```

Expected: exit code 0 with no TypeScript errors.

- [ ] **Step 3: Run the dashboard production build**

```cmd
pnpm build
```

Expected: exit code 0.

- [ ] **Step 4: Review the final diff**

```cmd
git diff --check
git diff -- dashboard/src/components/chat/Chat.vue dashboard/src/components/chat/GitDiffSidebar.vue dashboard/src/components/chat/ChatTodoSummaryBar.spec.ts
```

Expected: no whitespace errors and only the scoped behavior change plus its regression test.
