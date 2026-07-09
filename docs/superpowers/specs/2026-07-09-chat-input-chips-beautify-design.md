# ChatInput 上方 Status Chips 视觉美化 — 设计文档

| 项目 | 内容 |
|------|------|
| 主题 | 重构 ChatInput 上方的 4 个 status chip（项目加载 / Codegraph / Plan-Build / 查看工作区）的视觉风格，按"角色"显式分层，强化一致性，去除红色滥用 |
| 日期 | 2026-07-09（创建） |
| 作者 | elecvoid243 |
| 状态 | Design — 待用户 review |
| 关联代码 | `dashboard/src/components/chat/ChatInput.vue`、`SpcodeProjectIndicator.vue`、`SpcodeCodegraphChip.vue`、`SpcodePlanModeChip.vue`、`GitDiffChip.vue` |
| 前置 spec | 无（纯样式层重构，不涉及后端或 composable 行为变更） |

---

## 1. 背景与目标

### 1.1 现状

`ChatInput.vue` 的 `.input-area__status-row` 区域（行 14-100）在 spcode 插件启用时显示 4 个 chip，每个 chip 用 Vuetify `v-chip` 实现，承载三种**完全不同**的角色：

| Chip 文件 | 角色 | 当前变体策略 | 颜色策略 | 视觉重量 |
|---|---|---|---|---|
| `SpcodeProjectIndicator.vue` | 状态显示（已/未加载） | loaded→`tonal`+`success` / 未加载→`outlined` | 二态 | 中 |
| `SpcodeCodegraphChip.vue` | 状态显示（4 态：matched / mismatch / no-project / not-running） | `tonal` 仅在完全匹配；其他全 `outlined` | success / warning / error | 重 |
| `SpcodePlanModeChip.vue` | 切换（plan ↔ build） | plan→`tonal`+`warning` / build→`outlined`+`success` | 二态对偶 | 中 |
| `GitDiffChip.vue` | 导航（打开工作区面板） | 永远 `outlined`+`undefined` | 单一 | 轻 |

### 1.2 痛点

1. **角色混淆**：状态、切换、导航三种语义被当成"chip"一种视觉容器，缺少视觉差异化
2. **变体语义错位**：`outlined` 给人的感觉是"未填/被动"，但 `GitDiffChip` 实际是「打开工作区」主动操作；`tonal` 给人的感觉是"激活/选中"，但 codegraph "匹配"只是正常态不是"激活"
3. **红色过载**：`codegraph not-running` 用 `error`（红）—— 但实际只是"未启动"，不是错误；让用户产生焦虑
4. **元素不齐**：4 个 chip 中只有 2 个有 path 文本、只有 2 个有状态点概念，视觉密度不齐
5. **plan/build 切换不可见**：当前 chip 在 plan/build 间 toggle 改变整个色系，但用户难以一眼看出"这是个开关"
6. **布局分散**：左右各一组 + 右组内 `flex-direction: column`，中间留有大片空白

### 1.3 目标

1. **按角色分层**：把 4 个 chip 按"状态显示 / 切换器 / 导航"三种角色分配三种视觉范式，让差异**显式化**
2. **统一规则**：所有 chip 高度、间距、动效、暗色模式行为统一（除 plan 段切器 28px 比 chip 26px 高 2px）
3. **降级红色**：codegraph not-running 改为中性灰（空心圆点），仅在真正错误场景保留红色（本期未触发，token 预埋）
4. **状态点化**：状态显示类 chip 增加 6px 左侧状态点，icon 颜色与点同色但不刷背景，信息密度更高
5. **plan/build 升 segmented control**：用 Material 标准的 segmented control 双段切换器，明确"这是 toggle"，激活段用主色蓝淡背景（与发送按钮同源）
6. **去除 git-diff chip 的边框**：改为 ghost button，hover 时才出背景，明确"这是入口不是状态"

### 1.4 非目标

- ❌ **不**修改任何 composable 行为（`useSpcodeProjectStatus` / `useSpcodeCodegraphStatus` / `useSpcodePlanMode` 完全不变）
- ❌ **不**修改 ChatInput 的 `showSpcodeIndicator` / `showPlanModeChip` 等显隐逻辑（仅样式层）
- ❌ **不**改 `ProjectLoadDialog` / `CodegraphLoadDialog` 等 chip 触发的下游
- ❌ **不**引入新依赖（用现有 vue 3 + vuetify 3）
- ❌ **不**做 active 段切换的 ripple 动画（避免视觉噪声）
- ❌ **不**做动效偏好（prefers-reduced-motion）—— 现有动效也没有这个支持，避免范围蔓延
- ❌ **不**引入 Storybook / 视觉回归工具（项目无 Storybook，用 vitest 快照 + 手动 QA 替代）
- ❌ **不**改 i18n key 路径（仅在现有 `spcodeProjectLoad.planModeChip.*` 下更新文案 + 新增 2 个 segment aria-label key）

---

## 2. 设计决策（已与用户确认）

| # | 决策点 | 选择 | 理由 |
|---|--------|------|------|
| 1 | 设计方向 | **C. Differentiated roles**（按角色分层） | 改动面最小、风险最低；承认 4 chip 是 3 种东西，把差异显式化；segmented control 是 plan/build 最优解 |
| 2 | 状态显示范式 | **Status badge**（左侧 6px 状态点 + icon + label + 可选 path） | 状态点比纯 icon 颜色更易扫读；path 在需要时（loaded/mismatch）才出现 |
| 3 | 切换器范式 | **Segmented control**（双段 + active 段填色） | Material 标准组件，认知成本低；明确"这是 toggle"；激活态视觉与发送按钮同源 |
| 4 | 导航范式 | **Ghost button**（无边框 + hover 淡背景） | 与 status badge 的 1px 边框形成对比，强调"入口不是状态"；最少视觉重量 |
| 5 | codegraph not-running 颜色 | **中性灰**（空心圆点 + `on-surface 45%`） | 不是真正错误，是"未启动"状态；红色会制造不必要焦虑 |
| 6 | plan 激活态背景色 | **primary 蓝 12% 透明** | 与发送按钮 (`input-action-btn` #5594c6) 同源，视觉一致 |
| 7 | 状态点尺寸 | **6×6px** | 小但可见，不抢戏；与 chip 高 26px 比例约 23% |
| 8 | chip 高度 | **26px** | 比输入框 24px 圆角稍高 2px，有"控件感" |
| 9 | segmented 高度 | **28px** | 比 chip 高 2px，强调"可切换" |
| 10 | 段间分隔线 | **1px on-surface 8% border-left** | 视觉上"可分"但不"切断"；不要无分隔（会失去分段感） |
| 11 | 点已激活段行为 | **no-op**（不 emit toggle） | 避免误触把 plan 切到 build 又切回来；不引入 shake/feedback（YAGNI） |
| 12 | path 显示规则 | **仅在 2 个状态显示** | project loaded（让用户知道加载的是哪个）+ codegraph mismatch（让用户看到冲突的） |
| 13 | 动效时长 | **背景色 150ms ease**（chip hover）/ **200ms ease**（segmented 切换） | 不缩放避免抖动；动效有节奏差而非统一值 |
| 14 | 暗色模式 | **token 自动反转**（`--v-theme-*`） + **primary 背景 dark 下 18%**（比 light 的 12% 更亮才能看清） | 复用 Vuetify 主题系统 |
| 15 | 可访问性 | `role="tablist"`/`role="tab"` + `aria-selected` + 状态点 `aria-label` + focus-visible outline | 屏幕阅读器不读颜色；键盘 nav 可用 |
| 16 | i18n | **更新** planModeChip 的 tooltip 文案（描述当前 → 操作指引）+ **新增** 2 个 segment aria-label | 不改 key 路径；旧 tooltip 信息密度低 |
| 17 | 实施拆分 | **9 个 commit**（每个 chip + token + i18n 独立） | 出问题可单独 revert；每个 commit 独立 review |
| 18 | 回滚粒度 | **每个组件 commit 独立** | 不至于一个失败导致整批回滚 |

---

## 3. 架构与文件改动

### 3.1 架构原则

- **样式层重构，逻辑层零侵入**：所有 composable 行为不变；4 个 chip 组件的事件契约（emit 名与参数）保持兼容
- **token 化**：所有颜色/间距/尺寸走 CSS custom property，新增 `--sp-*` 命名空间（避免与 Vuetify `--v-*` 冲突）
- **新增 1 个通用 UI 组件**：`SpSegmentedControl.vue`（不耦合 spcode 业务，未来其他 toggle 场景可复用）
- **最小侵入父组件**：仅 `ChatInput.vue` 的 `.input-area__status-row__*` CSS 改 column → row，模板不改

### 3.2 调用链

```
ChatInput.vue (parent)
  ├─ <SpcodeProjectIndicator>   @open-load-dialog     (unchanged)
  ├─ <SpcodeCodegraphChip>      @open-codegraph-dialog (unchanged)
  ├─ <SpcodePlanModeChip>       @toggle                (unchanged)
  └─ <GitDiffChip>              @open-diff-sidebar     (unchanged)

  ChatInput.handlePlanModeToggle()     ← UNCHANGED
    ├─ status.value.active
    ├─ void spcodePlanMode.setActive(!status.value.active)  ← optimistic flip
    └─ void sendMessage(`/plan` or `/build`)
```

### 3.3 文件改动清单

| 文件 | 性质 | 估算行数 | 备注 |
|---|---|---|---|
| `dashboard/src/styles/_sp-tokens.css` | **新增** | ~25 | token 定义 + dark theme override |
| `dashboard/src/components/chat/SpSegmentedControl.vue` | **新增** | ~80 | 通用 segmented control，2+ 段 |
| `dashboard/src/components/chat/SpcodeProjectIndicator.vue` | **重写** | ~120 | v-chip → status badge |
| `dashboard/src/components/chat/SpcodeCodegraphChip.vue` | **重写** | ~150 | v-chip → status badge（多 1 态规则） |
| `dashboard/src/components/chat/SpcodePlanModeChip.vue` | **重写** | ~110 | v-chip → SpSegmentedControl 包装 |
| `dashboard/src/components/chat/GitDiffChip.vue` | **重写** | ~40 | v-chip → ghost button |
| `dashboard/src/components/chat/ChatInput.vue` | **改** | ~20 | status row column→row，gap 调整 |
| `dashboard/src/i18n/locales/{zh-CN,en-US,ru-RU}/features/chat.json` | **改/新增** | ~24 (8 × 3) | tooltip 文案 + 2 个 segment aria-label |
| `dashboard/src/components/chat/SpSegmentedControl.spec.ts` | **新增** | ~60 | 单元测试（项目首次引入 component 单元测试？—— 见 §6.3） |

**总计**：新增 ~165 行 / 改 ~250 行 / 删 ~100 行

### 3.4 目录结构

```
dashboard/src/
├── components/chat/
│   ├── ChatInput.vue                    (改 CSS)
│   ├── SpSegmentedControl.vue           (新增)
│   ├── SpSegmentedControl.spec.ts       (新增)
│   ├── SpcodeProjectIndicator.vue       (重写)
│   ├── SpcodeCodegraphChip.vue          (重写)
│   ├── SpcodePlanModeChip.vue           (重写)
│   └── GitDiffChip.vue                  (重写)
├── styles/
│   └── _sp-tokens.css                   (新增)
└── i18n/locales/{zh-CN,en-US,ru-RU}/features/chat.json
```

---

## 4. 视觉规范

### 4.1 三个视觉范式

| 范式 | 适用 chip | 高度 | 边框 | 背景 | 状态点 |
|---|---|---|---|---|---|
| **Status badge** | ProjectIndicator, CodegraphChip | 26px | 1px `on-surface 12%` | transparent → hover 4% | 6×6px 圆点 |
| **Segmented control** | PlanModeChip | 28px | 1px `on-surface 16%`（外框） | active 段 `primary 12%` | 无 |
| **Ghost button** | GitDiffChip | 26px | 无 | transparent → hover 4% | 无 |

### 4.2 颜色 token

新增到 `dashboard/src/styles/_sp-tokens.css`：

```css
:root,
.v-theme--light {
  --sp-chip-border: rgba(var(--v-theme-on-surface), 0.12);
  --sp-chip-border-strong: rgba(var(--v-theme-on-surface), 0.16);
  --sp-chip-divider: rgba(var(--v-theme-on-surface), 0.08);
  --sp-chip-hover-bg: rgba(var(--v-theme-on-surface), 0.04);
  --sp-chip-active-bg: rgba(var(--v-theme-on-surface), 0.08);

  --sp-segmented-active-bg: rgba(var(--v-theme-primary), 0.12);

  --sp-status-dot-success: rgb(var(--v-theme-success));
  --sp-status-dot-warning: rgb(var(--v-theme-warning));
  --sp-status-dot-neutral: rgba(var(--v-theme-on-surface), 0.45);
  --sp-status-dot-error: rgb(var(--v-theme-error));  /* 预埋，本期不触发 */

  --sp-text-primary: rgb(var(--v-theme-on-surface));
  --sp-text-muted: rgba(var(--v-theme-on-surface), 0.65);
  --sp-text-path: rgba(var(--v-theme-on-surface), 0.55);

  --sp-chip-height: 26px;
  --sp-segmented-height: 28px;
}

.v-theme--dark {
  --sp-chip-border: rgba(var(--v-theme-on-surface), 0.16);
  --sp-chip-border-strong: rgba(var(--v-theme-on-surface), 0.20);
  --sp-chip-divider: rgba(var(--v-theme-on-surface), 0.12);

  --sp-segmented-active-bg: rgba(var(--v-theme-primary), 0.18);  /* dark 下更亮 */
}
```

### 4.3 间距 & 排版

- chip 间水平间距：`6px`（紧凑但能区分）
- 大组（left vs right）：`space-between`（保留）
- 字体：label `12px / 500`、path `11px / 400 + monospace`、状态点 `6×6px`
- 行高：等于组件高度
- 圆角：status badge 12px、segmented 外 14px / 内 12px、ghost button 12px

### 4.4 动效

- chip / ghost button hover：`background-color 150ms ease`，不缩放
- segmented 切换：active 段 `background-color 200ms ease`，不 translate
- 状态点颜色变化：200ms ease
- tooltip：保留现状 200ms 延迟
- **不**做 prefers-reduced-motion 处理（现状也没有，避免范围蔓延）

---

## 5. 详细样式

### 5.1 Status badge（ProjectIndicator + CodegraphChip 共用）

```html
<button class="sp-status-badge" :class="...">
  <span class="sp-status-badge__dot" :class="dotClass" aria-hidden="true" />
  <v-icon size="14" class="sp-status-badge__icon">{{ icon }}</v-icon>
  <span class="sp-status-badge__label">{{ label }}</span>
  <span v-if="path" class="sp-status-badge__path" :title="path">{{ path }}</span>
</button>
```

```css
.sp-status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: var(--sp-chip-height);
  padding: 0 10px;
  border: 1px solid var(--sp-chip-border);
  border-radius: 12px;
  background: transparent;
  color: var(--sp-text-primary);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 150ms ease;
  max-width: 100%;
  min-width: 0;
}

.sp-status-badge:hover { background: var(--sp-chip-hover-bg); }
.sp-status-badge:active { background: var(--sp-chip-active-bg); }
.sp-status-badge:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 1px;
}

.sp-status-badge__dot {
  flex: 0 0 6px;
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--sp-status-dot-success);
  transition: background-color 200ms ease;
}

.sp-status-badge__dot--warning { background: var(--sp-status-dot-warning); }
.sp-status-badge__dot--neutral { background: var(--sp-status-dot-neutral); }
.sp-status-badge__dot--error   { background: var(--sp-status-dot-error); }

/* 空心点（"未启动/未加载"） */
.sp-status-badge--empty .sp-status-badge__dot {
  background: transparent;
  box-shadow: inset 0 0 0 1.5px var(--sp-status-dot-neutral);
}

.sp-status-badge__icon {
  flex: 0 0 14px;
  color: rgb(var(--v-theme-primary));
}

.sp-status-badge__label { white-space: nowrap; }

.sp-status-badge__path {
  font-family: var(--v-font-mono, monospace);
  font-size: 11px;
  font-weight: 400;
  color: var(--sp-text-path);
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
```

### 5.2 Status badge 状态映射

#### `SpcodeProjectIndicator`

| 状态 | dot class | icon | label | path | 整组 modifier |
|---|---|---|---|---|---|
| 未加载 | `--neutral` | `mdi-folder-outline` | "未加载项目" | — | `--empty` |
| 已加载 | `--success` | `mdi-folder-check-outline` | "项目已加载" | 显示 | — |

#### `SpcodeCodegraphChip`

| 状态 | dot class | icon | label | path | 整组 modifier |
|---|---|---|---|---|---|
| running + matched | `--success` | `mdi-database-check` | "Codegraph 已连接" | — | — |
| running + mismatch | `--warning` | `mdi-alert-circle-outline` | "Codegraph 路径不匹配" | 显示 codegraph 路径 | — |
| MCP not running | `--neutral` | `mdi-database-off-outline` | "Codegraph 未启动" | — | `--empty` |
| MCP 跑但没项目 | `--neutral` | `mdi-database-remove-outline` | "Codegraph 未加载" | — | `--empty` |

> 关键：error 状态点（红）**仅在真正错误场景使用**（本期未触发，token 预埋）。

### 5.3 SpSegmentedControl（通用组件）

```vue
<template>
  <div :class="['sp-segmented', { 'sp-segmented--disabled': disabled }]" role="tablist">
    <button
      v-for="(seg, i) in segments"
      :key="seg.value"
      type="button"
      role="tab"
      :aria-selected="seg.value === modelValue"
      :disabled="disabled"
      :tabindex="seg.value === modelValue ? 0 : -1"
      :class="['sp-segmented__seg', { 'sp-segmented__seg--active': seg.value === modelValue }]"
      @click="onClick(seg.value)"
      @keydown="onKeydown($event, i)"
    >
      <v-icon v-if="seg.icon" size="14">{{ seg.icon }}</v-icon>
      <span>{{ seg.label }}</span>
    </button>
  </div>
</template>
```

```ts
// Props
interface Segment { value: string; label: string; icon?: string }
defineProps<{
  segments: Segment[];           // >= 2
  modelValue: string;            // 当前激活 value
  disabled?: boolean;
}>()
const emit = defineEmits<{ 'update:modelValue': [v: string]; change: [v: string] }>()

function onClick(value: string): void {
  if (value === props.modelValue) return   // 关键：点已激活段 no-op
  emit('update:modelValue', value)
  emit('change', value)
}

function onKeydown(e: KeyboardEvent, i: number): void {
  const len = props.segments.length
  if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
    e.preventDefault()
    const next = props.segments[(i + 1) % len]
    onClick(next.value)
    focusSegment((i + 1) % len)
  } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
    e.preventDefault()
    const prev = props.segments[(i - 1 + len) % len]
    onClick(prev.value)
    focusSegment((i - 1 + len) % len)
  } else if (e.key === 'Home') {
    e.preventDefault(); onClick(props.segments[0].value); focusSegment(0)
  } else if (e.key === 'End') {
    e.preventDefault(); onClick(props.segments[len - 1].value); focusSegment(len - 1)
  }
}
```

```css
.sp-segmented {
  display: inline-flex;
  border: 1px solid var(--sp-chip-border-strong);
  border-radius: 14px;
  background: transparent;
  overflow: hidden;
  height: var(--sp-segmented-height);
}

.sp-segmented__seg {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: calc(var(--sp-segmented-height) - 2px);  /* 留出 1px 上下边框 */
  padding: 0 12px;
  border: 0;
  background: transparent;
  color: var(--sp-text-muted);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 200ms ease, color 200ms ease;
}

.sp-segmented__seg + .sp-segmented__seg {
  border-left: 1px solid var(--sp-chip-divider);
}

.sp-segmented__seg--active {
  background: var(--sp-segmented-active-bg);
  color: rgb(var(--v-theme-primary));
}

.sp-segmented__seg:hover:not(.sp-segmented__seg--active) {
  background: var(--sp-chip-hover-bg);
  color: var(--sp-text-primary);
}

.sp-segmented__seg:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;   /* outline 在边框内，避免溢出 */
}
```

### 5.4 PlanModeChip（segmented control 包装）

```vue
<template>
  <SpSegmentedControl
    :segments="segments"
    :model-value="modeValue"
    :title="tooltipText"
    @change="onChange"
  />
</template>

<script setup lang="ts">
const { tm } = useModuleI18n('features/chat')
const { status } = useSpcodePlanMode()
const emit = defineEmits<{ (e: 'toggle'): void }>()

const isPlanActive = computed(() => status.value.active === true)
const modeValue = computed(() => (isPlanActive.value ? 'plan' : 'build'))

const segments = computed(() => [
  { value: 'plan',  label: tm('spcodeProjectLoad.planModeChip.activeLabel'),   icon: 'mdi-clipboard-list-outline' },
  { value: 'build', label: tm('spcodeProjectLoad.planModeChip.inactiveLabel'), icon: 'mdi-hammer-wrench' },
])

function onChange(next: string): void {
  // next 是用户想切到的目标（不是当前）；与现状"emit toggle，父组件决定切到哪"语义一致
  emit('toggle')
}
</script>
```

> 父组件 `ChatInput.handlePlanModeToggle` **完全不变**：
> ```ts
> function handlePlanModeToggle() {
>   const nextActive = !spcodePlanMode.status.value.active
>   void spcodePlanMode.setActive(nextActive)
>   void sendMessage(nextActive ? '/plan' : '/build')
> }
> ```

### 5.5 Ghost button（GitDiffChip）

```html
<button class="sp-ghost-btn" type="button" @click="open">
  <v-icon size="14">mdi-folder-open-outline</v-icon>
  <span>{{ label }}</span>
</button>
```

```css
.sp-ghost-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: var(--sp-chip-height);
  padding: 0 8px;
  border: 0;
  border-radius: 12px;
  background: transparent;
  color: var(--sp-text-muted);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 150ms ease, color 150ms ease;
}
.sp-ghost-btn:hover {
  background: var(--sp-chip-hover-bg);
  color: var(--sp-text-primary);
}
.sp-ghost-btn:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 1px;
}
```

> icon 从 `mdi-folder-open`（实心）改 `mdi-folder-open-outline`（轻量），与 ghost button 整体调性一致。

---

## 6. 布局、测试、可访问性

### 6.1 整体布局

```html
<!-- ChatInput.vue: 模板不改，仅 CSS 改 column → row -->
<div class="input-area__status-row">
  <div class="input-area__status-row__left">
    <SpcodeProjectIndicator />
    <SpcodeCodegraphChip />
  </div>
  <div class="input-area__status-row__right">
    <SpcodePlanModeChip />
    <GitDiffChip />
  </div>
</div>
```

```css
.input-area__status-row { align-items: center; gap: 8px; /* 保留 space-between */ }
.input-area__status-row__left  { display: flex; gap: 6px; align-items: center; }
.input-area__status-row__right { display: flex; gap: 6px; align-items: center; }
.input-area__status-row__chips-stack { display: none; }  /* 不再需要 */
```

**关键**：右组内从 `flex-direction: column` 改为 `row`，因为 plan 改 segmented 后**永远显示**（不会消失），不再需要"叠放占位"的旧策略。

**响应式**：桌面（≥ md）单行；移动（< md）沿用现有 `comment-count-chip` 的 `d-none d-md-flex` 隐藏策略，本设计不增加移动端复杂度。

### 6.2 i18n 影响

#### zh-CN（其他 locale 类比）

```json
{
  "spcodeProjectLoad": {
    "planModeChip": {
      "activeLabel": "Plan",
      "inactiveLabel": "Build",
      "activeTooltip": "当前为 Plan 模式 · 点击切换到 Build",
      "inactiveTooltip": "当前为 Build 模式 · 点击切换到 Plan",
      "activeTooltipMulti": "当前 session 是 Plan · 还有 {count} 个 session 也在 Plan",
      "activeSegment": "Plan 模式",
      "inactiveSegment": "Build 模式"
    }
  }
}
```

| Key | 变化 |
|---|---|
| `activeLabel` / `inactiveLabel` | **不变** |
| `activeTooltip` / `inactiveTooltip` / `activeTooltipMulti` | **更新文案**（从描述当前 → 操作指引） |
| `activeSegment` / `inactiveSegment` | **新增**（`aria-label` 翻译） |

en-US / ru-RU 同步：en 文案"Currently in Plan · Click to switch to Build"，ru 类比。

### 6.3 测试策略

**单元测试**（vitest）：
- `SpSegmentedControl.spec.ts`：
  - 默认 2 段渲染正确
  - 点击 inactive 段 → emit `update:modelValue` / `change`
  - 点击 active 段 → **no emit**（关键防误触契约）
  - 键盘 ← → 切换段，焦点跟随
  - `aria-selected` / `role="tab"` 属性正确
  - 边界：3+ 段、disabled

**视觉回归**（vitest + happy-dom + `@vue/test-utils`）：
- 每个组件 1 个快照测试，**light + dark × 各状态**：
  - ProjectIndicator：2 态 × 2 theme = 4 快照
  - CodegraphChip：4 态 × 2 theme = 8 快照
  - PlanModeChip：2 态 × 2 theme = 4 快照
  - GitDiffChip：1 态（hover/focus 单独覆盖）× 2 theme = 2 快照

> 项目无 Storybook；这是 dashboard **首次**引入 component 单元测试 —— 决策点：要么引入 vitest（轻量、Vue 3 一等公民），要么仅用手动 QA。**推荐引入**（与 AstrBot 整体 Vitest 栈一致，仅 dashboard 此前未跟上）。

**手动 QA checklist**（9 项）：
- [ ] light + dark 主题下 4 chip 同时显示
- [ ] 项目未加载时 dot 空心灰色、点击 → ProjectLoadDialog 打开
- [ ] 项目加载后 dot 实心 success、path 正确截断（48 字符 + … 前缀）
- [ ] codegraph 4 态切换视觉符合 §5.2 表
- [ ] plan ↔ build 切换：active 段填色、inactive 灰、点击 active 段无响应
- [ ] segmented 键盘 nav：tab 进入 → ←/→ 切段 → Enter 不响应（已激活）
- [ ] git-diff hover 出淡背景、点击 → 工作区面板打开
- [ ] 暗色模式下 `primary 18%` 背景在 dark text 旁边可读
- [ ] 移动端（< md）4 chip 仍可显示不溢出（如果有 comment chip 时）

**可访问性**：
- 状态点 `aria-label`（屏幕阅读器不读颜色）
- 键盘 focus ring（`outline: 2px primary`）
- segmented `role="tablist"` + `role="tab"` + `aria-selected`
- axe-core 自动扫描（如有）

### 6.4 风险 & 回滚

| 风险 | 概率 | 缓解 |
|---|---|---|
| 用户已习惯 chip 风格，segmented 看着"陌生" | 中 | release notes 标注；segmented 是 Material 标准组件，认知成本低 |
| 状态点 + icon 同时存在，元素变多 | 中 | 状态点仅 6px，视觉上是"信号灯"；如反馈多，可降级回"icon 变色"方案（设计变体 B 已在脑里备好） |
| 暗色模式 `primary 18%` 背景不够明显 | 低 | 准备 16% / 20% 备选；用截图对比选最佳 |
| 现有 4 组件 CSS class 被外部依赖 | 低 | `git grep` + `codegraph_explore` 验证 `.spcode-codegraph-chip--*` 等无跨文件引用 |
| plan/build 切换从"点哪都一样"变"分两段"，旧用户误以为只能选 Plan | 低 | tooltip 显式说"点击切换到 Build"；segmented 是通用 UI 模式 |
| dashboard 首次引入 component 单元测试 | 中 | vitest 配置与 AstrBot 核心测试栈一致；如担心风险可仅加 snapshot 跳过逻辑测试 |

**回滚方案**：
- 9 commit 独立，单独 `git revert <sha>` 不影响其他
- 出问题最坏回滚 `SpcodePlanModeChip` 单 commit（segmented 退回 v-chip），其他 3 chip 保留美化

### 6.5 实施顺序（9 commits）

```
1. chore(ui): add --sp-* design tokens (_sp-tokens.css)
2. feat(ui): introduce SpSegmentedControl generic component (+ spec)
3. test(ui): add SpSegmentedControl unit tests
4. refactor(chat): rewrite SpcodeProjectIndicator as status badge
5. refactor(chat): rewrite SpcodeCodegraphChip as status badge
6. refactor(chat): rewrite SpcodePlanModeChip as segmented control
7. refactor(chat): rewrite GitDiffChip as ghost button
8. style(chat): adjust ChatInput status row layout (column→row, gap)
9. chore(i18n): update planModeChip tooltips + add segment aria-labels (3 locales)
```

每个 commit 独立可 review / revert。

---

## 7. 不做的事（YAGNI 边界，再强调一次）

- ❌ 不引入新依赖
- ❌ 不改 composable
- ❌ 不改 ChatInput 业务逻辑
- ❌ 不改 ProjectLoadDialog / CodegraphLoadDialog
- ❌ 不做 ripple / shake 动效
- ❌ 不做 prefers-reduced-motion
- ❌ 不引入 Storybook
- ❌ 不改 i18n key 路径
- ❌ 不动 backend
- ❌ 不为本期未触发的 error 状态点写测试

---

## 8. 验收标准

满足以下全部条件视为完成：

1. ✅ 4 个 chip 在 light + dark 主题下视觉与 §5 一致
2. ✅ codegraph 4 态视觉符合 §5.2 表，无红色滥用
3. ✅ plan/build 用 segmented control，active 段 `primary 12%/18%` 背景
4. ✅ 点击已激活 plan 段 **不**发送任何请求（验证网络面板 + composable 不被调）
5. ✅ 键盘 tab 进入 plan segment 后 ← → 可切换，Enter 无效
6. ✅ git-diff chip 无边框，hover 出淡背景
7. ✅ 现有 composable 单测全过（如果有）
8. ✅ 新增 SpSegmentedControl 单测全过
9. ✅ 移动端（< md）4 chip 不溢出
10. ✅ 9 个 commit 独立可 revert
11. ✅ i18n 3 locale 文案一致，aria-label 完整
12. ✅ `pnpm typecheck` + `pnpm lint` 无错

---

## 9. 后续可能的扩展（不纳入本期）

- 状态点改用 SVG 自定义形状（diamond / square）传达更细粒度状态
- chip 折叠模式：窗口太窄时 4 chip 折成 `+N` 折叠菜单
- segmented control 复用：未来如果有 "terse / verbose" 之类的 toggle 可直接用
- 主题扩展：增加 `high-contrast` 主题下的高对比色 token
- 动画偏好（prefers-reduced-motion）支持

---

## 10. 关联资料

- `dashboard/src/components/chat/ChatInput.vue`（status row 在行 14-100、CSS 在行 1565-1600）
- `dashboard/src/components/chat/SpcodeProjectIndicator.vue`
- `dashboard/src/components/chat/SpcodeCodegraphChip.vue`
- `dashboard/src/components/chat/SpcodePlanModeChip.vue`
- `dashboard/src/components/chat/GitDiffChip.vue`
- `dashboard/src/composables/useSpcodeProjectStatus.ts`（不修改）
- `dashboard/src/composables/useSpcodeCodegraphStatus.ts`（不修改）
- `dashboard/src/composables/useSpcodePlanMode.ts`（不修改）
- `dashboard/src/i18n/locales/{zh-CN,en-US,ru-RU}/features/chat.json`
