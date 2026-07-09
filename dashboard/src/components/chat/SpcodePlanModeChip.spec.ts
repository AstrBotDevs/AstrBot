// Author: elecvoid243, 2026-07-09
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { mount } from '@vue/test-utils'

function mockPlanMode(active: boolean, allActiveCount = 1) {
  vi.doMock('@/composables/useSpcodePlanMode', () => ({
    useSpcodePlanMode: () => ({
      status: ref({ active, allActiveCount }),
      refresh: vi.fn(),
      setActive: vi.fn(),
    }),
  }))
}

describe('SpcodePlanModeChip (segmented control)', () => {
  // Same pattern as Task 5's spec: vi.doMock + dynamic import needs a
  // module-cache reset between tests so each test sees its own mock state.
  beforeEach(() => {
    vi.resetModules()
  })

  it('renders Plan as active when status.active=true', async () => {
    mockPlanMode(true)
    const { default: SpcodePlanModeChip } = await import('./SpcodePlanModeChip.vue')
    const wrapper = mount(SpcodePlanModeChip, { global: { mocks: { $t: (k: string) => k } } })
    const buttons = wrapper.findAll('button[role="tab"]')
    expect(buttons[0].attributes('aria-selected')).toBe('true')  // Plan
    expect(buttons[1].attributes('aria-selected')).toBe('false') // Build
  })

  it('renders Build as active when status.active=false', async () => {
    mockPlanMode(false)
    const { default: SpcodePlanModeChip } = await import('./SpcodePlanModeChip.vue')
    const wrapper = mount(SpcodePlanModeChip, { global: { mocks: { $t: (k: string) => k } } })
    const buttons = wrapper.findAll('button[role="tab"]')
    expect(buttons[0].attributes('aria-selected')).toBe('false')
    expect(buttons[1].attributes('aria-selected')).toBe('true')
  })

  it('emits toggle when clicking the inactive segment', async () => {
    mockPlanMode(true)
    const { default: SpcodePlanModeChip } = await import('./SpcodePlanModeChip.vue')
    const wrapper = mount(SpcodePlanModeChip, { global: { mocks: { $t: (k: string) => k } } })
    const buildButton = wrapper.findAll('button[role="tab"]')[1]
    await buildButton.trigger('click')
    expect(wrapper.emitted('toggle')).toBeTruthy()
  })

  it('emits no toggle when clicking the already-active segment', async () => {
    mockPlanMode(true)
    const { default: SpcodePlanModeChip } = await import('./SpcodePlanModeChip.vue')
    const wrapper = mount(SpcodePlanModeChip, { global: { mocks: { $t: (k: string) => k } } })
    const planButton = wrapper.findAll('button[role="tab"]')[0]
    await planButton.trigger('click')
    expect(wrapper.emitted('toggle')).toBeFalsy()
  })

  it('uses SpSegmentedControl under the hood (role="tablist" exists)', async () => {
    mockPlanMode(true)
    const { default: SpcodePlanModeChip } = await import('./SpcodePlanModeChip.vue')
    const wrapper = mount(SpcodePlanModeChip, { global: { mocks: { $t: (k: string) => k } } })
    expect(wrapper.find('[role="tablist"]').exists()).toBe(true)
  })
})
