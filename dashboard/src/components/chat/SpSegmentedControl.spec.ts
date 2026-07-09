// Author: elecvoid243, 2026-07-09
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import SpSegmentedControl from './SpSegmentedControl.vue'

const segments = [
  { value: 'plan', label: 'Plan', icon: 'mdi-clipboard-list-outline' },
  { value: 'build', label: 'Build', icon: 'mdi-hammer-wrench' },
]

describe('SpSegmentedControl', () => {
  beforeEach(() => {
    // Reset focus state between tests
    document.body.innerHTML = ''
  })

  it('renders one button per segment', () => {
    const wrapper = mount(SpSegmentedControl, {
      props: { segments, modelValue: 'plan' },
    })
    const buttons = wrapper.findAll('button[role="tab"]')
    expect(buttons).toHaveLength(2)
    expect(buttons[0].text()).toContain('Plan')
    expect(buttons[1].text()).toContain('Build')
  })

  it('marks the active segment with aria-selected=true', () => {
    const wrapper = mount(SpSegmentedControl, {
      props: { segments, modelValue: 'build' },
    })
    const buttons = wrapper.findAll('button[role="tab"]')
    expect(buttons[0].attributes('aria-selected')).toBe('false')
    expect(buttons[1].attributes('aria-selected')).toBe('true')
  })

  it('emits update:modelValue and change when clicking the inactive segment', async () => {
    const wrapper = mount(SpSegmentedControl, {
      props: { segments, modelValue: 'plan' },
    })
    const buildButton = wrapper.findAll('button[role="tab"]')[1]
    await buildButton.trigger('click')
    expect(wrapper.emitted('update:modelValue')).toEqual([['build']])
    expect(wrapper.emitted('change')).toEqual([['build']])
  })

  it('emits no events when clicking the already-active segment (no-op contract)', async () => {
    const wrapper = mount(SpSegmentedControl, {
      props: { segments, modelValue: 'plan' },
    })
    const planButton = wrapper.findAll('button[role="tab"]')[0]
    await planButton.trigger('click')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    expect(wrapper.emitted('change')).toBeUndefined()
  })

  it('moves to next segment on ArrowRight', async () => {
    const wrapper = mount(SpSegmentedControl, {
      props: { segments, modelValue: 'plan' },
      attachTo: document.body,
    })
    const planButton = wrapper.findAll('button[role="tab"]')[0]
    await planButton.trigger('focus')
    await planButton.trigger('keydown', { key: 'ArrowRight' })
    expect(wrapper.emitted('update:modelValue')).toEqual([['build']])
  })

  it('wraps around on ArrowLeft from first segment', async () => {
    const wrapper = mount(SpSegmentedControl, {
      props: { segments, modelValue: 'plan' },
      attachTo: document.body,
    })
    const planButton = wrapper.findAll('button[role="tab"]')[0]
    await planButton.trigger('focus')
    await planButton.trigger('keydown', { key: 'ArrowLeft' })
    expect(wrapper.emitted('update:modelValue')).toEqual([['build']])
  })

  it('renders the role="tablist" container', () => {
    const wrapper = mount(SpSegmentedControl, {
      props: { segments, modelValue: 'plan' },
    })
    expect(wrapper.find('[role="tablist"]').exists()).toBe(true)
  })

  it('does not emit any event when disabled', async () => {
    const wrapper = mount(SpSegmentedControl, {
      props: { segments, modelValue: 'plan', disabled: true },
    })
    const buildButton = wrapper.findAll('button[role="tab"]')[1]
    await buildButton.trigger('click')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    expect(wrapper.emitted('change')).toBeUndefined()
  })

  it('renders the segment icon when provided', () => {
    const wrapper = mount(SpSegmentedControl, {
      props: { segments, modelValue: 'plan' },
    })
    // v-icon renders as <i class="mdi mdi-clipboard-list-outline"> in Vuetify
    expect(wrapper.find('.mdi-clipboard-list-outline').exists()).toBe(true)
    expect(wrapper.find('.mdi-hammer-wrench').exists()).toBe(true)
  })
})