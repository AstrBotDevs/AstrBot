import { isRecord } from "./typeGuards";

export interface ConfigProfileInfo extends Record<string, unknown> {
  id: string;
  name: string;
}

export function readConfigInfoList(value: unknown): ConfigProfileInfo[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) =>
    isRecord(item) && typeof item.id === "string"
      ? [{ ...item, id: item.id, name: typeof item.name === "string" ? item.name : item.id }]
      : [],
  );
}

export function requireConfigProfile(value: unknown) {
  if (!isRecord(value) || !isRecord(value.config) || !isRecord(value.metadata)) {
    throw new TypeError("Configuration response must contain config and metadata objects");
  }
  return { ...value, config: value.config, metadata: value.metadata };
}
