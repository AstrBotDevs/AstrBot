import { computed, ref } from "vue";

export const useShareSelection = () => {
  const isActive = ref(false);
  const selected = ref(new Set());

  const clear = () => {
    isActive.value = false;
    selected.value = new Set();
  };

  const toggleMode = () => {
    if (isActive.value) {
      clear();
      return;
    }
    isActive.value = true;
    selected.value = new Set();
  };

  const normalizeNames = (names = []) =>
    names.filter((name) => typeof name === "string" && name.length > 0);

  const toggleItem = (name) => {
    if (!isActive.value || !name) return;

    const next = new Set(selected.value);
    if (next.has(name)) {
      next.delete(name);
    } else {
      next.add(name);
    }
    selected.value = next;
  };

  const toggleAll = (names = []) => {
    if (!isActive.value) return;

    const normalizedNames = normalizeNames(names);
    if (normalizedNames.length === 0) return;

    const allSelected = normalizedNames.every((name) => selected.value.has(name));
    const next = new Set(selected.value);
    normalizedNames.forEach((name) => {
      if (allSelected) {
        next.delete(name);
      } else {
        next.add(name);
      }
    });
    selected.value = next;
  };

  const isSelected = (name) => !!name && selected.value.has(name);

  const areAllSelected = (names = []) => {
    const normalizedNames = normalizeNames(names);
    if (normalizedNames.length === 0) return false;
    return normalizedNames.every((name) => selected.value.has(name));
  };

  const count = computed(() => selected.value.size);

  return {
    isActive,
    selected,
    clear,
    toggleMode,
    toggleItem,
    toggleAll,
    isSelected,
    areAllSelected,
    count,
  };
};
