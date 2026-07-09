// Author: elecvoid243, 2026-07-09
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import GitDiffChip from './GitDiffChip.vue'

describe('GitDiffChip (ghost button)', () => {
  it('renders the sp-ghost-btn class (no chip border)', () => {
    const wrapper = mount(GitDiffChip, {
      global: { mocks: { $t: (k: string) => k } },
    })
    expect(wrapper.find('.sp-ghost-btn').exists()).toBe(true)
    // The old v-chip class should NOT be present
    expect(wrapper.find('.git-diff-chip').exists()).toBe(false)
  })

  it('uses mdi-folder-open-outline (lighter icon than the old mdi-folder-open)', () => {
    const wrapper = mount(GitDiffChip, {
      global: { mocks: { $t: (k: string) => k } },
    })
    expect(wrapper.find('.mdi-folder-open-outline').exists()).toBe(true)
  })

  it('emits open-diff-sidebar on click', async () => {
    const wrapper = mount(GitDiffChip, {
      global: { mocks: { $t: (k: string) => k } },
    })
    await wrapper.find('.sp-ghost-btn').trigger('click')
    expect(wrapper.emitted('open-diff-sidebar')).toBeTruthy()
  })

  it('renders the 查看工作区 label from i18n', () => {
    const wrapper = mount(GitDiffChip, {
      global: { mocks: { $t: (k: string) => k } },
    })
    expect(wrapper.text()).toContain('查看工作区')
  })
})
