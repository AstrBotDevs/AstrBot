// Author: elecvoid243, 2026-07-09
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { mount } from '@vue/test-utils'

// Reusable mock factory
function mockStatuses(codegraph: any, project: any) {
  vi.doMock('@/composables/useSpcodeCodegraphStatus', () => ({
    useSpcodeCodegraphStatus: () => ({
      status: ref(codegraph),
      refresh: vi.fn(),
    }),
  }))
  vi.doMock('@/composables/useSpcodeProjectStatus', () => ({
    useSpcodeProjectStatus: () => ({
      status: ref(project),
      refresh: vi.fn(),
    }),
  }))
}

describe('SpcodeCodegraphChip (status badge, 4 states)', () => {
  // Required to invalidate the module cache so vi.doMock below takes effect
  // on each subsequent dynamic `await import('./SpcodeCodegraphChip.vue')`.
  // Without this, only the first test in the suite sees its own mock state.
  beforeEach(() => {
    vi.resetModules()
  })

  it('renders status badge class for the matched state', async () => {
    mockStatuses(
      { mcpRunning: true, activeProject: '/proj' },
      { loaded: true, directory: '/proj', loadedAt: null },
    )
    const { default: SpcodeCodegraphChip } = await import('./SpcodeCodegraphChip.vue')
    const wrapper = mount(SpcodeCodegraphChip, { global: { mocks: { $t: (k: string) => k } } })
    expect(wrapper.find('.sp-status-badge').exists()).toBe(true)
    expect(wrapper.find('.sp-status-badge__dot--success').exists()).toBe(true)
    expect(wrapper.text()).toContain('Codegraph 已连接')
  })

  it('shows warning dot + path when paths mismatch', async () => {
    mockStatuses(
      { mcpRunning: true, activeProject: '/other' },
      { loaded: true, directory: '/proj', loadedAt: null },
    )
    const { default: SpcodeCodegraphChip } = await import('./SpcodeCodegraphChip.vue')
    const wrapper = mount(SpcodeCodegraphChip, { global: { mocks: { $t: (k: string) => k } } })
    expect(wrapper.find('.sp-status-badge__dot--warning').exists()).toBe(true)
    expect(wrapper.text()).toContain('Codegraph 路径不匹配')
    expect(wrapper.find('.sp-status-badge__path').exists()).toBe(true)
  })

  it('shows neutral empty dot (NOT red) when MCP is not running', async () => {
    mockStatuses(
      { mcpRunning: false, activeProject: '' },
      { loaded: false, directory: null, loadedAt: null },
    )
    const { default: SpcodeCodegraphChip } = await import('./SpcodeCodegraphChip.vue')
    const wrapper = mount(SpcodeCodegraphChip, { global: { mocks: { $t: (k: string) => k } } })
    expect(wrapper.find('.sp-status-badge--empty').exists()).toBe(true)
    expect(wrapper.find('.sp-status-badge__dot--neutral').exists()).toBe(true)
    expect(wrapper.find('.sp-status-badge__dot--error').exists()).toBe(false) // no red
    expect(wrapper.text()).toContain('Codegraph 未启动')
  })

  it('shows neutral empty dot when MCP running but no project set', async () => {
    mockStatuses(
      { mcpRunning: true, activeProject: '' },
      { loaded: false, directory: null, loadedAt: null },
    )
    const { default: SpcodeCodegraphChip } = await import('./SpcodeCodegraphChip.vue')
    const wrapper = mount(SpcodeCodegraphChip, { global: { mocks: { $t: (k: string) => k } } })
    expect(wrapper.find('.sp-status-badge--empty').exists()).toBe(true)
    expect(wrapper.find('.sp-status-badge__dot--error').exists()).toBe(false) // no red
    expect(wrapper.text()).toContain('Codegraph 未加载')
  })

  it('emits open-codegraph-dialog on click', async () => {
    mockStatuses(
      { mcpRunning: true, activeProject: '/proj' },
      { loaded: true, directory: '/proj', loadedAt: null },
    )
    const { default: SpcodeCodegraphChip } = await import('./SpcodeCodegraphChip.vue')
    const wrapper = mount(SpcodeCodegraphChip, { global: { mocks: { $t: (k: string) => k } } })
    await wrapper.find('.sp-status-badge').trigger('click')
    expect(wrapper.emitted('open-codegraph-dialog')).toBeTruthy()
  })
})
