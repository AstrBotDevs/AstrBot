import { config } from '@vue/test-utils'
import { defineComponent, h, type Slot } from 'vue'

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
}
