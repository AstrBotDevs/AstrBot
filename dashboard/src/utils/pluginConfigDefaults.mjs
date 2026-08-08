const CONFIG_TYPE_DEFAULTS = Object.freeze({
  int: 0,
  float: 0.0,
  bool: false,
  string: '',
  text: '',
  list: [],
  file: [],
  object: {},
  template_list: [],
  dict: {},
});

function cloneDefault(value) {
  return structuredClone(value);
}

function resolveDefaultValue(itemMeta) {
  if (!itemMeta || typeof itemMeta !== 'object') {
    return undefined;
  }

  if (itemMeta.type === 'object') {
    if (!itemMeta.items || typeof itemMeta.items !== 'object') {
      return undefined;
    }
    const nested = {};
    for (const [key, nestedMeta] of Object.entries(itemMeta.items)) {
      const nestedDefault = resolveDefaultValue(nestedMeta);
      if (nestedDefault === undefined) {
        return undefined;
      }
      nested[key] = nestedDefault;
    }
    return nested;
  }

  if (!Object.hasOwn(CONFIG_TYPE_DEFAULTS, itemMeta.type)) {
    return undefined;
  }
  if (Object.hasOwn(itemMeta, 'default')) {
    return itemMeta.default;
  }
  return CONFIG_TYPE_DEFAULTS[itemMeta.type];
}

function configValuesEqual(currentValue, defaultValue) {
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
    typeof currentValue === 'object' &&
    typeof defaultValue === 'object'
  ) {
    const currentKeys = Object.keys(currentValue);
    const defaultKeys = Object.keys(defaultValue);
    return (
      currentKeys.length === defaultKeys.length &&
      currentKeys.every(
        (key) =>
          Object.hasOwn(defaultValue, key) &&
          configValuesEqual(currentValue[key], defaultValue[key]),
      )
    );
  }
  return false;
}

export function getPluginConfigDefaultValue(itemMeta) {
  const defaultValue = resolveDefaultValue(itemMeta);
  return defaultValue === undefined ? undefined : cloneDefault(defaultValue);
}

export function isPluginConfigValueModified(value, itemMeta) {
  const defaultValue = resolveDefaultValue(itemMeta);
  return defaultValue !== undefined && !configValuesEqual(value, defaultValue);
}

export function canRestorePluginConfigDefault(value, itemMeta) {
  return (
    itemMeta?.readonly !== true && isPluginConfigValueModified(value, itemMeta)
  );
}
