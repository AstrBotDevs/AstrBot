export function getConfigTemplateValue(value, template) {
  if (value !== undefined && value !== null) return value;
  if (template?.default !== undefined) return template.default;
  switch (template?.type || "string") {
    case "int":
    case "float":
    case "number":
      return 0;
    case "bool":
    case "boolean":
      return false;
    case "json":
      return "{}";
    default:
      return "";
  }
}

export function normalizeConfigValue(value, metadata) {
  let result = value;
  switch (metadata?.type) {
    case "int": {
      const numericValue = Number(value);
      result = Number.isFinite(numericValue) ? Math.trunc(numericValue) : 0;
      break;
    }
    case "float":
    case "number":
      result = Number(value);
      break;
    case "json":
      result = JSON.parse(value);
      break;
    case "string":
      result = String(value);
      break;
    case "bool":
    case "boolean":
      break;
    default:
      result = String(value);
  }
  if (metadata?.slider && ["int", "float", "number"].includes(metadata.type)) {
    result = Math.max(
      metadata.slider.min ?? 0,
      Math.min(metadata.slider.max ?? 100, result),
    );
  }
  return result;
}
