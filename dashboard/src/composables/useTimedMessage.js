import { reactive } from "vue";

export const useTimedMessage = (initialType = "success") => {
  const state = reactive({
    message: "",
    type: initialType,
  });

  let timer = null;

  const clearTimer = () => {
    if (timer) {
      clearTimeout(timer);
      timer = null;
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
      timer = setTimeout(() => {
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
