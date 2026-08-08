type PluginConfigMeta = {
  type?: string;
  default?: unknown;
  items?: Record<string, PluginConfigMeta>;
  readonly?: boolean;
};

const CONFIG_TYPE_DEFAULTS: Readonly<Record<string, unknown>> = Object.freeze({
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

function cloneDefault<T>(value: T): T {
  return structuredClone(value);
}

function resolveDefaultValue(
  itemMeta: PluginConfigMeta | null | undefined,
): unknown | undefined {
  if (!itemMeta || typeof itemMeta !== 'object') {
    return undefined;
  }

  if (itemMeta.type === 'object') {
    if (!itemMeta.items || typeof itemMeta.items !== 'object') {
      return undefined;
    }
    const nested: Record<string, unknown> = {};
    for (const [key, nestedMeta] of Object.entries(itemMeta.items)) {
      const nestedDefault = resolveDefaultValue(nestedMeta);
      if (nestedDefault === undefined) {
        return undefined;
      }
      nested[key] = nestedDefault;
    }
    return nested;
  }

  if (!itemMeta.type || !Object.hasOwn(CONFIG_TYPE_DEFAULTS, itemMeta.type)) {
    return undefined;
  }
  if (Object.hasOwn(itemMeta, 'default')) {
    return itemMeta.default;
  }
  return CONFIG_TYPE_DEFAULTS[itemMeta.type];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function configValuesEqual(
  currentValue: unknown,
  defaultValue: unknown,
): boolean {
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
  if (isRecord(currentValue) && isRecord(defaultValue)) {
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

export function getPluginConfigDefaultValue(
  itemMeta: PluginConfigMeta | null | undefined,
): unknown | undefined {
  const defaultValue = resolveDefaultValue(itemMeta);
  return defaultValue === undefined ? undefined : cloneDefault(defaultValue);
}

export function isPluginConfigValueModified(
  value: unknown,
  itemMeta: PluginConfigMeta | null | undefined,
): boolean {
  const defaultValue = resolveDefaultValue(itemMeta);
  return defaultValue !== undefined && !configValuesEqual(value, defaultValue);
}

export function canRestorePluginConfigDefault(
  value: unknown,
  itemMeta: PluginConfigMeta | null | undefined,
): boolean {
  return (
    itemMeta?.readonly !== true && isPluginConfigValueModified(value, itemMeta)
  );
}
