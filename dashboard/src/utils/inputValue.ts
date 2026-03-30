export const normalizeTextInput = (value: unknown): string =>
  typeof value === "string" ? value : "";
