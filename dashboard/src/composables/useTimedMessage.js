import { reactive, ref } from "vue";

export const useTimedMessage = (initialType = "success") => {
  const state = reactive({
    message: "",
    type: initialType,
  });

  const timer = ref(null);

  const clearTimer = () => {
    if (timer.value) {
      clearTimeout(timer.value);
      timer.value = null;
    }
  };

  const clearMessage = () => {
    state.message = "";
    clearTimer();
  };

  const setMessage = (message, type = initialType, duration = 4000) => {
    state.message = message || "";
    state.type = type;
    clearTimer();
    if (duration > 0 && state.message) {
      timer.value = setTimeout(() => {
        state.message = "";
      }, duration);
    }
  };

  return {
    state,
    setMessage,
    clearMessage,
    clearTimer,
  };
};
