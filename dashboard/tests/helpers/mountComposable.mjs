import { mount } from "@vue/test-utils";
import { defineComponent, h } from "vue";

export function mountComposable(create, { childSetup, ...options } = {}) {
  let result;
  let child;
  const Child = defineComponent({
    setup() {
      child = childSetup?.();
      return () => null;
    },
  });
  const wrapper = mount(
    defineComponent({
      setup() {
        result = create();
        return () => h(Child);
      },
    }),
    options,
  );
  let mounted = true;
  const unmount = () => {
    if (!mounted) return;
    mounted = false;
    wrapper.unmount();
  };
  return { result, child, wrapper, unmount };
}
