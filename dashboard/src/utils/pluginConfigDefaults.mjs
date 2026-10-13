const CONFIG_TYPE_DEFAULTS = Object.freeze({
  int: 0,
  float: 0,
  bool: false,
  string: "",
  text: "",
  list: [],
  file: [],
  object: {},
  template_list: [],
  dict: {},
});

const resolveDefaultValue = (itemMeta) => {
  if (!itemMeta || typeof itemMeta !== "object") {
    return undefined;
  }
  if (Object.prototype.hasOwnProperty.call(itemMeta, "default")) {
    return itemMeta.default;
  }
  return CONFIG_TYPE_DEFAULTS[itemMeta.type];
};

const configValuesEqual = (currentValue, defaultValue) => {
  if (Object.is(currentValue, defaultValue)) {
    return true;
  }
  if (Array.isArray(currentValue) || Array.isArray(defaultValue)) {
    return (
      Array.isArray(currentValue) &&
      Array.isArray(defaultValue) &&
      currentValue.length === defaultValue.length &&
      currentValue.every((value, index) =>
        configValuesEqual(value, defaultValue[index]),
      )
    );
  }
  if (
    currentValue &&
    defaultValue &&
    typeof currentValue === "object" &&
    typeof defaultValue === "object"
  ) {
    const currentKeys = Object.keys(currentValue);
    const defaultKeys = Object.keys(defaultValue);
    return (
      currentKeys.length === defaultKeys.length &&
      currentKeys.every(
        (key) =>
          Object.prototype.hasOwnProperty.call(defaultValue, key) &&
          configValuesEqual(currentValue[key], defaultValue[key]),
      )
    );
  }
  return false;
};

export const isPluginConfigValueModified = (value, itemMeta) => {
  const defaultValue = resolveDefaultValue(itemMeta);
  return defaultValue !== undefined && !configValuesEqual(value, defaultValue);
};

export const getPluginConfigDefaultValue = (itemMeta) => {
  const defaultValue = resolveDefaultValue(itemMeta);
  return defaultValue === undefined
    ? undefined
    : JSON.parse(JSON.stringify(defaultValue));
};
