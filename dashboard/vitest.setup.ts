import { config } from '@vue/test-utils'
import { defineComponent, h, type Slot } from 'vue'

// Initialize i18n with zh-CN translations so `tm()` / `t()` return real
// strings (e.g. "未加载项目") during tests instead of the
// "[MISSING: ...]" placeholder the custom composable emits.
import { initI18n } from '@/i18n/composables'
await initI18n('zh-CN')

// Minimal v-icon stub for tests. Production code uses Vuetify's full v-icon
// (registered globally via app.use(vuetify) in src/main.ts). Under test we
// avoid pulling in all of Vuetify and instead render an <i> with the MDI
// class — which is exactly what the spec asserts on.
const VIconStub = defineComponent({
  name: 'VIcon',
  props: {
    size: { type: [String, Number], default: undefined },
  },
  setup(props, { slots }: { slots: { default?: Slot } }) {
    return () => {
      const slotNodes = slots.default?.() ?? []
      // Vuetify's v-icon passes the icon name through its default slot;
      // when rendered it becomes the trailing class token (e.g. mdi-hammer-wrench).
      let iconName = ''
      for (const node of slotNodes) {
        if (typeof node.children === 'string') {
          iconName = node.children
          break
        }
      }
      const classes = ['v-icon', 'notranslate', 'mdi', iconName]
      const styleParts: string[] = []
      if (props.size !== undefined) {
        const sizeVal =
          typeof props.size === 'number' ? `${props.size}px` : props.size
        if (sizeVal && !sizeVal.endsWith('px')) {
          styleParts.push(`font-size: ${sizeVal}`)
        } else if (sizeVal) {
          styleParts.push(`font-size: ${sizeVal}`)
        }
      }
      return h('i', {
        class: classes.filter((c) => c !== '').join(' '),
        style: styleParts.join('; '),
        'aria-hidden': 'true',
      })
    }
  },
})

config.global.components = {
  ...config.global.components,
  'v-icon': VIconStub,
  // v-tooltip wraps the trigger via a named #activator slot and the
  // tooltip body via the default slot. Vuetify's real v-tooltip portals
  // the default slot into an overlay at runtime — under test we just need
  // both slots present in the DOM tree so `.find('.sp-status-badge')` can
  // locate the inner button. We pass an empty props object on the activator
  // scope because the component template destructures `{ props: tipProps }`.
  'v-tooltip': defineComponent({
    name: 'VTooltip',
    setup(_props, { slots }) {
      return () =>
        h('div', { class: 'v-tooltip' }, [
          slots.activator?.({ props: {} }),
          slots.default?.(),
        ])
    },
  }),
}
