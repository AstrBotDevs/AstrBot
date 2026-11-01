<template>
  <div class="provider-sources-panel">
    <div class="provider-sources-head">
      <div class="provider-sources-head__copy">
        <h3 class="provider-sources-title">{{ title || tm('providerSources.title') }}</h3>
      </div>

      <div class="provider-sources-controls">
        <div class="provider-sources-mobile-select">
          <v-select
            :model-value="selectedSourceValue"
            :items="sourceOptions"
            item-title="title"
            item-value="value"
            density="compact"
            variant="solo-filled"
            flat
            hide-details
            :placeholder="selectHint || tm('providerSources.selectHint')"
            @update:model-value="selectSourceByValue"
        >
            <template #selection="{ item }">
              <div class="provider-source-select-value">
                <v-avatar size="22" rounded="lg" class="provider-source-avatar">
                  <v-img
                    v-if="item.raw.source?.provider"
                    :src="resolveSourceIcon(item.raw.source)"
                    :class="{ 'provider-icon--monochrome': isMonochromeSourceIcon(item.raw.source) }"
                    alt="provider logo"
                    cover
                  ></v-img>
                  <v-icon v-else size="14">mdi-creation</v-icon>
                </v-avatar>
                <span>{{ item.raw.title }}</span>
              </div>
            </template>

            <template #item="{ props: itemProps, item }">
              <v-list-item
                v-bind="itemProps"
                :subtitle="item.raw.subtitle"
              >
                <template #prepend>
                  <v-avatar size="24" rounded="lg" class="provider-source-avatar me-2">
                    <v-img
                      v-if="item.raw.source?.provider"
                      :src="resolveSourceIcon(item.raw.source)"
                      :class="{ 'provider-icon--monochrome': isMonochromeSourceIcon(item.raw.source) }"
                      alt="provider logo"
                      cover
                    ></v-img>
                    <v-icon v-else size="14">mdi-creation</v-icon>
                  </v-avatar>
                </template>
              </v-list-item>
            </template>
          </v-select>
        </div>

        <v-btn
          v-if="canDeleteSelectedSource"
          class="provider-sources-mobile-delete"
          icon="mdi-delete-outline"
          variant="text"
          size="small"
          color="error"
          :aria-label="deleteLabel || tm('providerSources.delete')"
          :title="deleteLabel || tm('providerSources.delete')"
          @click.stop="deleteSelectedSource"
        ></v-btn>

        <ProviderSourceDialog
          :source-types="availableSourceTypes"
          :tm="tm"
          @select="emitAddSource"
        />
      </div>

      <v-progress-linear
        v-if="loading"
        class="provider-sources-progress"
        color="primary"
        height="2"
        indeterminate
      />
    </div>

    <div
      v-if="localSources.length > 0"
      ref="listRef"
      class="provider-sources-list"
      :class="{ 'provider-sources-list--dragging': dragState.dragging }"
      :style="{ '--hold-ms': `${HOLD_TO_DRAG_MS}ms` }"
    >
      <button
        v-for="(source, index) in localSources"
        :key="sourceKey(source)"
        type="button"
        :data-source-index="index"
        :data-source-key="sourceKey(source)"
        :style="itemStyle(source, index)"
        :class="[
          'provider-source-item',
          {
            'provider-source-item--active': isActive(source),
            'provider-source-item--dragging': dragState.dragging && dragState.key === sourceKey(source),
            'provider-source-item--arming': armingKey === sourceKey(source),
            'provider-source-item--still': suppressTransition,
            'provider-source-item--settling': settlingKey === sourceKey(source),
            'provider-source-item--locked': Boolean(source.isPlaceholder)
          }
        ]"
        @click="handleItemClick(source, $event)"
        @pointerdown="handlePointerDown($event, source)"
        @touchmove="handleTouchMove"
      >
        <v-avatar size="28" rounded="lg" class="provider-source-item__avatar provider-source-avatar">
          <v-img
            v-if="source?.provider"
            :src="resolveSourceIcon(source)"
            :class="{ 'provider-icon--monochrome': isMonochromeSourceIcon(source) }"
            alt="provider logo"
            cover
          ></v-img>
          <v-icon v-else size="16">mdi-creation</v-icon>
        </v-avatar>

        <div class="provider-source-item__content">
          <div class="provider-source-item__title">
            {{ getSourceDisplayName(source) }}
          </div>
          <div class="provider-source-item__subtitle">
            {{ source.api_base || sourceBadge(source) }}
          </div>
        </div>

        <div class="provider-source-item__actions">
          <v-btn
            v-if="!source.isPlaceholder"
            icon="mdi-delete-outline"
            variant="text"
            size="small"
            :aria-label="deleteLabel || tm('providerSources.delete')"
            :title="deleteLabel || tm('providerSources.delete')"
            @click.stop="emitDeleteSource(source)"
          ></v-btn>
        </div>
      </button>
    </div>

    <div v-else-if="!loading" class="provider-sources-empty">
      <v-icon size="44" color="grey-lighten-1">mdi-api-off</v-icon>
      <p class="provider-sources-empty__text">
        {{ emptyText || tm('providerSources.empty') }}
      </p>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import ProviderSourceDialog from '@/components/provider/ProviderSourceDialog.vue'

const props = defineProps({
  displayedProviderSources: {
    type: Array,
    default: () => []
  },
  selectedProviderSource: {
    type: Object,
    default: null
  },
  availableSourceTypes: {
    type: Array,
    default: () => []
  },
  title: {
    type: String,
    default: ''
  },
  emptyText: {
    type: String,
    default: ''
  },
  selectHint: {
    type: String,
    default: ''
  },
  deleteLabel: {
    type: String,
    default: ''
  },
  loading: {
    type: Boolean,
    default: false
  },
  tm: {
    type: Function,
    required: true
  },
  resolveSourceIcon: {
    type: Function,
    required: true
  },
  isMonochromeSourceIcon: {
    type: Function,
    required: true
  },
  getSourceDisplayName: {
    type: Function,
    required: true
  }
})

const emit = defineEmits([
  'add-provider-source',
  'select-provider-source',
  'delete-provider-source',
  'reorder-provider-sources'
])

// 触屏长按多久算「拉起拖动」；鼠标不需要长按，按下后移动超过阈值即起拖
const HOLD_TO_DRAG_MS = 500
const MOVE_SLOP_PX = 14
// 指针越过相邻项中线这么多像素才换位，手一抖不跟着跳
const SWAP_DEAD_ZONE_PX = 8
const AUTO_SCROLL_EDGE_PX = 28
const AUTO_SCROLL_MAX_STEP = 10
// 落位动画的时长，跟 CSS 里 transform 那根过渡对齐
const SETTLE_MS = 320
// 静息态的过渡，跟 CSS 基类同一根曲线；拖动那一段会被行内关掉
const REST_TRANSITION = 'transform 0.24s cubic-bezier(0.2, 0.8, 0.3, 1)'

const listRef = ref(null)
const localSources = ref([])
// 渲染顺序固定不变，拖动只改这个排列 —— DOM 不重排，指针事件才不会中途走丢
const orderedKeys = ref([])
const suppressTransition = ref(false)
// 正在落位的那一项：动画跑完之前让它待在上层
const settlingKey = ref('')
const dragState = ref({ dragging: false, key: null })
const armingKey = ref(null)
const listStep = ref(0)

let pressTimer = null
let autoScrollFrame = null
let autoScrollDelta = 0
let armedKey = null
let dragStartRank = 0
// 起拖那一刻被拖项的中心，之后全程不变：判定全用「指针相对它的位移」算
let dragAnchor = 0
// 起拖时的滚动位置，与拖动中的实时滚动位置：列表自己滚了，锚点也得跟着走
let dragBaseScrollTop = 0
let dragScrollTop = 0
// 指针事件只记最新位置，重活挪到每帧一次：高刷屏一秒上千个 pointermove，逐个跑完整链就是掉帧的根
let dragFrame = null
let pendingPointerY = 0
// 列表在视口里的位置：起拖时量一次，只有窗口缩放或外层滚动才作废重量
let dragListRect = null
let pressPointerId = null
let pressPointerType = ''
let lastPointerY = 0
let pressStart = { x: 0, y: 0 }
let reordered = false
let suppressClick = false
let settleTimer = 0

const sourceKey = (source) => (
  source?.isPlaceholder ? `template:${source.templateKey}` : `source:${source?.id}`
)

// 集合没变时只换排列，DOM 一个节点都不动；真增删了才重建，并禁掉那一帧的过渡
function applySources(sources) {
  const list = Array.isArray(sources) ? [...sources] : []
  const keys = list.map((source) => sourceKey(source))
  const sameMembers =
    keys.length === localSources.value.length &&
    keys.every((key) => localSources.value.some((source) => sourceKey(source) === key))

  if (sameMembers) {
    // 成员没变就别动排列 —— 保存后的回声顺序会把刚拖好的位置再甩一次，
    // 表现就是落位动画走到一半突然转向。只按当前顺序把数据刷成最新。
    const byKey = new Map(list.map((source) => [sourceKey(source), source]))
    localSources.value = localSources.value.map(
      (source) => byKey.get(sourceKey(source)) || source
    )
    return
  }

  suppressTransition.value = true
  localSources.value = list
  orderedKeys.value = keys
  window.requestAnimationFrame(() => {
    window.requestAnimationFrame(() => {
      suppressTransition.value = false
    })
  })
}

watch(
  () => props.displayedProviderSources,
  (sources) => {
    // 拖动过程中不要被外部数据覆盖本地顺序
    if (dragState.value.dragging) return
    applySources(sources)
  },
  { immediate: true }
)

// 行高变了（窗口缩放、字体变化）就重新量一次
watch(
  () => localSources.value.length,
  () => measureListStep(),
  { flush: 'post' }
)

function getListNode() {
  const host = listRef.value
  if (!host) return null
  return host instanceof HTMLElement ? host : host.$el || null
}

function getSourceNodes() {
  const node = getListNode()
  return node ? Array.from(node.querySelectorAll('[data-source-index]')) : []
}

// 行距用 offsetTop 量：它只反映布局，不带任何动画位移
function measureListStep() {
  const nodes = getSourceNodes()
  if (!nodes.length) {
    listStep.value = 0
    return
  }
  if (nodes.length === 1) {
    listStep.value = nodes[0].offsetHeight + 4
    return
  }
  const step = nodes[1].offsetTop - nodes[0].offsetTop
  listStep.value = step > 0 ? step : nodes[0].offsetHeight + 4
}

// 跟手位移只写列表容器上的一条自定义属性：不触发组件重渲染，也不进任何响应式依赖
function setDragOffset(px) {
  const node = getListNode()
  if (node) node.style.setProperty('--provider-drag-offset', `${px}px`)
}

function measureDragListRect() {
  const node = getListNode()
  dragListRect = node ? node.getBoundingClientRect() : null
  return dragListRect
}

function handleViewportResize() {
  dragListRect = null
  measureListStep()
}

// 列表自己滚不改变它在视口里的位置，那笔账记在 dragScrollTop 里；
// 外面那层容器滚了，被拖项在视口里跟着挪了同样多——锚点不跟着平移，换位判定就偏一个滚动量
function handleViewportScroll(event) {
  if (!dragState.value.dragging) return
  if (event.target === getListNode()) return
  const before = dragListRect ? dragListRect.top : null
  dragListRect = null
  const rect = measureDragListRect()
  if (before !== null && rect) dragAnchor += rect.top - before
}

// key → 槽位：换位时重算一次，渲染里只查表，不再对每一项做一次线性查找
const rankByKey = computed(() => {
  const ranks = new Map()
  orderedKeys.value.forEach((key, rank) => ranks.set(key, rank))
  return ranks
})

// 被拖的那一项：transform 冻结在起拖时的槽位，跟手那一截由容器上的自定义属性补，这里不给行内样式
function itemStyle(source, domIndex) {
  const key = sourceKey(source)
  if (dragState.value.dragging && dragState.value.key === key) return null

  const step = listStep.value
  const rank = rankByKey.value.get(key)
  if (rank === undefined || !step) {
    return { transform: 'translateY(0px)', transition: REST_TRANSITION }
  }
  return {
    transform: `translateY(${(rank - domIndex) * step}px)`,
    transition: REST_TRANSITION
  }
}

function clearPressTimer() {
  if (pressTimer !== null) {
    window.clearTimeout(pressTimer)
    pressTimer = null
  }
}

function beginDrag() {
  clearPressTimer()
  armingKey.value = null
  if (!armedKey) return
  // 记下起拖时它占的槽位和它当时的中心：拖动中判定只看指针相对这个中心走了多远
  const startRank = rankByKey.value.get(armedKey)
  dragStartRank = startRank === undefined ? 0 : startRank
  const startNode = getSourceNodes().find((node) => node.dataset.sourceKey === armedKey)
  if (startNode) {
    const rect = startNode.getBoundingClientRect()
    dragAnchor = rect.top + rect.height / 2
  }
  const domIndex = localSources.value.findIndex((source) => sourceKey(source) === armedKey)
  const dragList = getListNode()
  if (dragList) {
    dragBaseScrollTop = dragList.scrollTop
    dragScrollTop = dragBaseScrollTop
    dragListRect = dragList.getBoundingClientRect()
    // 被拖项冻结在起拖槽位上的基准位移；跟手那一截逐帧由 --provider-drag-offset 补上
    const base = (dragStartRank - domIndex) * listStep.value
    dragList.style.setProperty('--provider-drag-base', `${base}px`)
    setDragOffset(0)
  }
  dragState.value = { dragging: true, key: armedKey }
  if (pressPointerType !== 'mouse') {
    navigator.vibrate?.(10)
  }
}

// 指针可能在任何元素上抬起，事件挂在 window 上才收得住
onMounted(() => {
  window.addEventListener('pointermove', handlePointerMove)
  window.addEventListener('pointerup', handlePointerUp)
  window.addEventListener('pointercancel', handlePointerCancel)
  window.addEventListener('resize', handleViewportResize)
  window.addEventListener('scroll', handleViewportScroll, { capture: true, passive: true })
  measureListStep()
})

onBeforeUnmount(() => {
  window.removeEventListener('pointermove', handlePointerMove)
  window.removeEventListener('pointerup', handlePointerUp)
  window.removeEventListener('pointercancel', handlePointerCancel)
  window.removeEventListener('resize', handleViewportResize)
  window.removeEventListener('scroll', handleViewportScroll, { capture: true })
  clearPressTimer()
  stopAutoScroll()
  if (dragFrame !== null) window.cancelAnimationFrame(dragFrame)
  window.clearTimeout(settleTimer)
})

function handlePointerDown(event, source) {
  if (source.isPlaceholder) return
  if (event.pointerType === 'mouse' && event.button !== 0) return
  // 点在删除按钮上时不要顺手把它拖走
  if (event.target.closest('.provider-source-item__actions')) return

  clearPressTimer()
  measureListStep()
  pressPointerId = event.pointerId
  pressPointerType = event.pointerType
  pressStart = { x: event.clientX, y: event.clientY }
  armedKey = sourceKey(source)
  reordered = false
  suppressClick = false

  if (event.pointerType === 'mouse') return
  // 触屏：长按期间给条进度线，让他知道要按多久
  armingKey.value = armedKey
  pressTimer = window.setTimeout(beginDrag, HOLD_TO_DRAG_MS)
}

function handlePointerMove(event) {
  if (event.pointerId !== pressPointerId) return

  if (!dragState.value.dragging) {
    const moved = Math.hypot(event.clientX - pressStart.x, event.clientY - pressStart.y)
    if (moved <= MOVE_SLOP_PX) return
    if (event.pointerType === 'mouse') {
      beginDrag()
    } else {
      // 长按还没成立就先滑动，按滚动处理
      clearPressTimer()
      armingKey.value = null
      armedKey = null
      return
    }
  }

  lastPointerY = event.clientY
  pendingPointerY = event.clientY
  // 事件本身不干重活：指针一帧能报几十次，位移和换位判定一帧算一次就够
  if (dragFrame === null) dragFrame = window.requestAnimationFrame(flushDragFrame)
}

function flushDragFrame() {
  dragFrame = null
  if (!dragState.value.dragging) return

  const pointerY = pendingPointerY
  // 被拖的那一项跟着指针走；起拖那一下的阈值位移不补进去，免得跳一格
  const rawOffset = pointerY - pressStart.y
  setDragOffset(
    Math.abs(rawOffset) > MOVE_SLOP_PX
      ? rawOffset - Math.sign(rawOffset) * MOVE_SLOP_PX
      : 0
  )
  stepSourceToward(pointerY)
  updateAutoScroll(pointerY)
}

function stepSourceToward(pointerY) {
  const total = orderedKeys.value.length
  const step = listStep.value
  if (!total || !step) return

  const rank = rankByKey.value.get(dragState.value.key)
  if (rank === undefined) return

  // 指针跑到第几格了：只跟起拖时的锚点、行距和滚动量有关，不读任何 DOM
  const scrolled = dragScrollTop - dragBaseScrollTop
  const raw = (pointerY - dragAnchor + scrolled) / step + dragStartRank
  // 越过相邻槽位中线再多留一点余量才换位，手抖不跟着跳
  const slack = SWAP_DEAD_ZONE_PX / step

  let targetRank = rank
  while (targetRank + 1 < total && raw > targetRank + 1 + slack) targetRank += 1
  while (targetRank - 1 >= 0 && raw < targetRank - 1 - slack) targetRank -= 1
  if (targetRank === rank) return

  moveRank(rank, targetRank)
}

// 只改排列，不碰 DOM 顺序；位移全交给 transform 表达
function moveRank(fromRank, toRank) {
  const next = [...orderedKeys.value]
  const [moved] = next.splice(fromRank, 1)
  next.splice(toRank, 0, moved)
  orderedKeys.value = next
  reordered = true
}

function updateAutoScroll(pointerY) {
  // 拖动期间列表的视口位置不会自己变，量一次就够；只有缩放或外层滚动把它作废
  const rect = dragListRect || measureDragListRect()
  if (!rect) return

  let delta = 0
  if (pointerY < rect.top + AUTO_SCROLL_EDGE_PX) {
    const ratio = (rect.top + AUTO_SCROLL_EDGE_PX - pointerY) / AUTO_SCROLL_EDGE_PX
    delta = -Math.ceil(Math.min(ratio, 1) * AUTO_SCROLL_MAX_STEP)
  } else if (pointerY > rect.bottom - AUTO_SCROLL_EDGE_PX) {
    const ratio = (pointerY - (rect.bottom - AUTO_SCROLL_EDGE_PX)) / AUTO_SCROLL_EDGE_PX
    delta = Math.ceil(Math.min(ratio, 1) * AUTO_SCROLL_MAX_STEP)
  }

  autoScrollDelta = delta
  if (delta) startAutoScrollLoop()
}

function startAutoScrollLoop() {
  if (autoScrollFrame !== null) return
  const tick = () => {
    const node = getListNode()
    if (!autoScrollDelta || !node) {
      autoScrollFrame = null
      return
    }
    node.scrollTop += autoScrollDelta
    // 滚到底会被 clamp，读回来才是真值；记进账里，换位判定就不用再碰 DOM
    dragScrollTop = node.scrollTop
    stepSourceToward(lastPointerY)
    autoScrollFrame = window.requestAnimationFrame(tick)
  }
  autoScrollFrame = window.requestAnimationFrame(tick)
}

function stopAutoScroll() {
  autoScrollDelta = 0
  if (autoScrollFrame !== null) {
    window.cancelAnimationFrame(autoScrollFrame)
    autoScrollFrame = null
  }
}

function handleTouchMove(event) {
  // 长按已成立，不再让页面跟着手指滚
  if (dragState.value.dragging) {
    event.preventDefault()
  }
}

function handlePointerUp(event) {
  if (event.pointerId !== pressPointerId) return
  const wasDragging = dragState.value.dragging
  const settledKey = dragState.value.key
  const shouldEmit = wasDragging && reordered

  clearPressTimer()
  // 松手可能赶在最后一帧之前：先把挂起的那一帧落下去，最后一段位移不至于白丢
  if (dragFrame !== null) {
    window.cancelAnimationFrame(dragFrame)
    dragFrame = null
    flushDragFrame()
  }
  stopAutoScroll()
  pressPointerId = null
  armedKey = null
  armingKey.value = null
  dragState.value = { dragging: false, key: null }
  setDragOffset(0)

  if (!wasDragging) return

  // 落位这段动画里让它待在上层：滑过邻居时不该被邻居盖住
  if (settledKey) {
    settlingKey.value = settledKey
    window.clearTimeout(settleTimer)
    settleTimer = window.setTimeout(() => {
      settlingKey.value = ''
    }, SETTLE_MS)
  }

  // 拖动收尾的那一下 click 不该被当成选中
  suppressClick = true
  window.setTimeout(() => {
    suppressClick = false
  }, 400)

  if (!shouldEmit) return

  const sourceByKey = new Map(localSources.value.map((source) => [sourceKey(source), source]))
  const ordered = orderedKeys.value
    .map((key) => sourceByKey.get(key))
    .filter(Boolean)
    .filter((source) => !source.isPlaceholder)
    .map((source) => source.id)

  emit('reorder-provider-sources', ordered)
}

function handlePointerCancel(event) {
  if (event.pointerId !== pressPointerId) return
  handlePointerUp(event)
}

function handleItemClick(source, event) {
  if (suppressClick) {
    event.preventDefault()
    event.stopPropagation()
    return
  }
  emitSelectSource(source)
}

const selectedId = computed(() => props.selectedProviderSource?.id || null)
const canDeleteSelectedSource = computed(() =>
  Boolean(props.selectedProviderSource && !props.selectedProviderSource.isPlaceholder)
)

const isActive = (source) => {
  if (source.isPlaceholder) return false
  return selectedId.value !== null && selectedId.value === source.id
}

const sourceBadge = (source) => source.provider || source.templateKey || 'source'

const sourceValue = (source) => (
  source.isPlaceholder ? `template:${source.templateKey}` : `source:${source.id}`
)

const sourceOptions = computed(() =>
  props.displayedProviderSources.map((source) => ({
    title: props.getSourceDisplayName(source),
    subtitle: source.api_base || sourceBadge(source),
    value: sourceValue(source),
    source
  }))
)

const selectedSourceValue = computed(() => {
  if (!props.selectedProviderSource) return null
  return sourceValue(props.selectedProviderSource)
})

const emitAddSource = (type) => emit('add-provider-source', type)
const emitSelectSource = (source) => emit('select-provider-source', source)
const emitDeleteSource = (source) => emit('delete-provider-source', source)

const deleteSelectedSource = () => {
  if (canDeleteSelectedSource.value) {
    emitDeleteSource(props.selectedProviderSource)
  }
}

const selectSourceByValue = (value) => {
  const option = sourceOptions.value.find((item) => item.value === value)
  if (option?.source) {
    emitSelectSource(option.source)
  }
}
</script>

<style scoped>
.provider-sources-panel {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.provider-sources-head {
  display: flex;
  align-items: center;
  flex: 0 0 auto;
  justify-content: space-between;
  gap: 12px;
  padding: 20px 20px 12px;
  position: relative;
}

.provider-sources-progress {
  bottom: 0;
  left: 0;
  position: absolute;
  right: 0;
}

.provider-sources-head__copy {
  min-width: 0;
}

.provider-sources-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.provider-sources-title {
  margin: 0;
  font-size: 16px;
  font-weight: 650;
  line-height: 1.3;
}

.provider-sources-mobile {
  padding: 8px 20px 16px;
}

.provider-sources-mobile-select {
  display: none;
  min-width: 0;
  flex: 1;
}

.provider-sources-mobile-delete {
  display: none;
  flex-shrink: 0;
}

.provider-source-select-value {
  min-width: 0;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.provider-source-select-value span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.provider-sources-list {
  flex: 1;
  min-height: 0;
  overscroll-behavior: contain;
  overflow-y: auto;
  padding: 6px 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.provider-source-item {
  position: relative;
  width: 100%;
  border: 0;
  border-radius: 12px;
  background: transparent;
  color: inherit;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  cursor: pointer;
  text-align: left;
  touch-action: pan-y;
  user-select: none;
  /* 两个默认值都是数值：不写字面量 none，属性在「有位移」和「没位移」之间才插得动 */
  transform: translateY(0);
  scale: 1;
  transition:
    transform 0.24s cubic-bezier(0.2, 0.8, 0.3, 1),
    scale 0.18s ease,
    box-shadow 0.24s ease,
    background-color 0.24s ease;
}

.provider-source-item:hover,
.provider-source-item--active {
  background: rgba(var(--v-theme-on-surface), 0.05);
}

.provider-sources-list--dragging {
  cursor: grabbing;
}

.provider-source-item:hover {
  cursor: grab;
}

/* 长按计时中：底部一条进度线，满格就拉起 */
.provider-source-item--arming {
  background: rgba(var(--v-theme-on-surface), 0.05);
}

.provider-source-item--arming::after {
  content: '';
  position: absolute;
  left: 12px;
  right: 12px;
  bottom: 5px;
  height: 2px;
  border-radius: 999px;
  background: rgb(var(--v-theme-primary));
  transform: scaleX(0);
  transform-origin: left center;
  animation: provider-source-arm var(--hold-ms, 500ms) linear forwards;
}

@keyframes provider-source-arm {
  from {
    transform: scaleX(0);
    opacity: 0.4;
  }
  to {
    transform: scaleX(1);
    opacity: 1;
  }
}

/* DOM 真的重排的那一帧不做过渡：布局位移与 transform 归零会叠成两倍 */
.provider-source-item--still {
  transition: none;
}

/* 落位动画还在跑：保持在上层，滑过邻居时不被盖住 */
.provider-source-item--settling {
  z-index: 2;
}

/* 被拖起的那一项：跟手不许走过渡（这组 transition 里没有 transform），抬起交给 scale 和阴影。
   transform 与 transition 这里必须带 !important——主题／皮肤类插件会按 .provider-source-item
   这个类名写下特异度更高的规则，给这一项挂上含 transform 的 180ms 过渡，又在 :hover 上写
   translateY(-1px)。两样都跟脚本每帧写进去的跟手位移打架：前者把它缓动成漂移，后者把跟手值
   直接顶回 -1px。拖拽期间这一项的位移由组件独占，别让主题层插手。 */
.provider-source-item--dragging {
  z-index: 3;
  opacity: 0.96;
  background: rgba(var(--v-theme-primary), 0.16);
  box-shadow: 0 12px 26px rgba(0, 0, 0, 0.22);
  scale: 1.02;
  /* 跟手位移走容器上的变量：Vue 只负责加这个类，每帧的位移由脚本直接写属性 */
  transform: translateY(calc(var(--provider-drag-base) + var(--provider-drag-offset))) !important;
  /* 只有拖起来的这几秒提合成层，落地就还回去 */
  will-change: transform;
  transition:
    box-shadow 0.24s ease,
    background-color 0.24s ease,
    scale 0.18s ease !important;
}

.provider-source-item--dragging,
.provider-source-item--dragging:hover {
  cursor: grabbing;
}


.provider-source-item--locked,
.provider-source-item--locked:hover {
  cursor: default;
}

@media (prefers-reduced-motion: reduce) {
  .provider-source-item--arming::after {
    animation: none;
  }

  .provider-source-item {
    transition: none;
  }
}

.provider-source-avatar {
  background: transparent !important;
}

.provider-source-item__content {
  min-width: 0;
  flex: 1;
}

.provider-source-item__title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
  font-weight: 600;
}

.provider-source-item__subtitle {
  margin-top: 4px;
  color: rgba(var(--v-theme-on-surface), 0.54);
  font-size: 12px;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.provider-source-item__actions {
  opacity: 0;
}

.provider-source-item:hover .provider-source-item__actions,
.provider-source-item--active .provider-source-item__actions {
  opacity: 1;
}

.provider-sources-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 24px;
  text-align: center;
}

.provider-sources-empty__text {
  margin: 0;
  color: rgba(var(--v-theme-on-surface), 0.56);
  font-size: 13px;
}

@media (max-width: 960px) {
  .provider-sources-panel {
    height: auto;
  }

  .provider-sources-head {
    padding: 16px 16px 8px;
    align-items: stretch;
    flex-direction: column;
    gap: 10px;
  }

  .provider-sources-mobile-select {
    display: block;
  }

  .provider-sources-mobile-delete {
    display: inline-flex;
  }

  .provider-sources-controls {
    width: 100%;
  }

  .provider-sources-list {
    display: none;
  }

  .provider-sources-empty {
    min-height: 160px;
  }
}

@media (max-width: 600px) {
  .provider-sources-controls :deep(.v-btn) {
    min-width: max-content;
  }
}
</style>
